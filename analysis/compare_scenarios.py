#!/usr/bin/env python3
"""
compare_scenarios.py
--------------------
Compare trip-level and aggregate SUMO outputs for the Task 4 intersection
scenarios:

  - safety        : 100% safety-oriented cyclists
  - safe70risky30 : 70% safety-oriented cyclists and 30% high-risk cyclists
  - risky         : 100% high-risk cyclists

Outputs in analysis/plots/:
  distributions_car.pdf      - violin plots for car trip metrics
  distributions_bicycle.pdf  - violin plots for bicycle trip metrics
  ecdf_bikes.pdf             - ECDFs for bicycle trip metrics
  safety_indicators.pdf      - collision diagnostics and emergency braking
  aggregate_stats.pdf        - aggregate means from SUMO statistics XML
  ks_tests.csv               - two-sample KS tests for bicycle trip metrics

Dependencies:
  pip install pandas matplotlib scipy
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", "/tmp/sumo-besafe-matplotlib")
import matplotlib.pyplot as plt
from scipy import stats


ROOT = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "results"
PLOTS_DIR = Path(__file__).parent / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

SCENARIOS = {
    "safety": "car5vpm_bike3vpm_safety",
    "safe70risky30": "car5vpm_bike3vpm_safe70risky30",
    "risky": "car5vpm_bike3vpm_risky",
}

LABELS = {
    "safety": "Safety\n(100% cautious)",
    "safe70risky30": "Mixed\n(70% cautious / 30% high-risk)",
    "risky": "Risky\n(100% high-risk)",
}

COLORS = {
    "safety": "#2196F3",
    "safe70risky30": "#FF9800",
    "risky": "#F44336",
}

SCENARIO_KEYS = list(SCENARIOS.keys())


def save_figure(fig: plt.Figure, filename: str) -> Path:
    out = PLOTS_DIR / filename
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.relative_to(ROOT)}")
    return out


def load_tripinfo(prefix: str) -> pd.DataFrame:
    """Load one tripinfo CSV file for a scenario prefix."""
    path = RESULTS_DIR / f"{prefix}_tripinfo.csv"
    if not path.exists():
        sys.exit(f"[ERROR] Missing file: {path}")

    df = pd.read_csv(path, sep=";")
    df.columns = df.columns.str.strip()

    # Remove vehicles that did not depart or were still vaporized in tripinfo.
    if "vaporized" in df.columns:
        df = df[df["vaporized"].isna() | (df["vaporized"].astype(str).str.strip() == "")]

    # Avoid division by zero and unfinished rows with invalid duration.
    df = df[df["duration"] > 0].copy()

    df["speed_ms"] = df["routeLength"] / df["duration"]
    df["vClass"] = df["vType"].apply(
        lambda t: "bicycle" if "bike" in str(t).lower() else "car"
    )

    return df


def parse_stats(prefix: str) -> dict:
    """Extract aggregate sections from SUMO statistic-output XML."""
    path = RESULTS_DIR / f"{prefix}_stats.xml"
    if not path.exists():
        sys.exit(f"[ERROR] Missing file: {path}")

    root = ET.parse(path).getroot()

    def attrs(tag: str) -> dict:
        el = root.find(tag)
        return dict(el.attrib) if el is not None else {}

    return {
        "safety": attrs("safety"),
        "vehicles": attrs("vehicleTripStatistics"),
        "bikes": attrs("bikeTripStatistics"),
        "teleports": attrs("teleports"),
    }


def empty_collision_counts() -> dict:
    return {
        "total": 0,
        "bike_involved": 0,
        "car_car": 0,
        "bike_bike": 0,
        "other": 0,
    }


def load_collision_counts(prefix: str) -> dict:
    """Count collisions from collision-output, separating bicycle-involved events."""
    path = RESULTS_DIR / f"{prefix}_collision.csv"
    if not path.exists():
        return empty_collision_counts()

    df = pd.read_csv(path, sep=";")
    if df.empty:
        return empty_collision_counts()

    collider = df["colliderType"].astype(str).str.lower()
    victim = df["victimType"].astype(str).str.lower()
    has_bicycle = collider.str.contains("bike|bicycle") | victim.str.contains("bike|bicycle")
    car_car = (collider == "car") & (victim == "car")
    bike_bike = collider.str.contains("bike|bicycle") & victim.str.contains("bike|bicycle")

    return {
        "total": int(len(df)),
        "bike_involved": int(has_bicycle.sum()),
        "car_car": int(car_car.sum()),
        "bike_bike": int(bike_bike.sum()),
        "other": int((~has_bicycle & ~car_car).sum()),
    }


def style_axis(ax, ylabel: str, title: str) -> None:
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def annotate_stats(ax, positions: list[int], data_by_scenario: dict) -> None:
    """Show mean and median under each violin."""
    ylim = ax.get_ylim()
    span = ylim[1] - ylim[0]
    for pos, sc in zip(positions, SCENARIO_KEYS):
        arr = data_by_scenario[sc]
        if len(arr) == 0:
            continue
        mean = np.mean(arr)
        median = np.median(arr)
        ax.text(
            pos,
            ylim[0] - span * 0.12,
            f"mean={mean:.1f}\nmedian={median:.1f}",
            ha="center",
            va="top",
            fontsize=7.5,
            color="dimgray",
        )


METRICS_CONFIG = {
    "car": [
        ("duration", "Trip duration (s)", "Trip duration"),
        ("waitingTime", "Waiting time (s)", "Waiting time"),
        ("timeLoss", "Time loss (s)", "Time loss"),
        ("speed_ms", "Average speed (m/s)", "Average speed"),
    ],
    "bicycle": [
        ("duration", "Trip duration (s)", "Trip duration"),
        ("waitingTime", "Waiting time (s)", "Waiting time"),
        ("timeLoss", "Time loss (s)", "Time loss"),
        ("speed_ms", "Average speed (m/s)", "Average speed"),
    ],
}

VCLASS_TITLES = {"car": "Cars", "bicycle": "Bicycles"}


def plot_distributions(dfs: dict) -> None:
    for vclass, metrics in METRICS_CONFIG.items():
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(
            f"Trip metric distributions - {VCLASS_TITLES[vclass]}\n"
            "Scenario comparison",
            fontsize=13,
            fontweight="bold",
            y=1.01,
        )
        axes = axes.flatten()

        for ax, (col, ylabel, title) in zip(axes, metrics):
            data_by_scenario = {
                sc: dfs[sc][dfs[sc]["vClass"] == vclass][col].dropna().values
                for sc in SCENARIO_KEYS
            }

            positions = list(range(len(SCENARIO_KEYS)))
            arrays = [data_by_scenario[sc] for sc in SCENARIO_KEYS]
            arrays = [a if len(a) > 0 else np.array([0]) for a in arrays]

            violin = ax.violinplot(
                arrays,
                positions=positions,
                showmedians=True,
                showextrema=True,
                widths=0.6,
            )
            for body, sc in zip(violin["bodies"], SCENARIO_KEYS):
                body.set_facecolor(COLORS[sc])
                body.set_alpha(0.65)
                body.set_edgecolor("white")
            violin["cmedians"].set_color("white")
            violin["cmedians"].set_linewidth(2)
            for part in ("cmaxes", "cmins", "cbars"):
                violin[part].set_color("gray")
                violin[part].set_linewidth(1)

            for pos, sc in zip(positions, SCENARIO_KEYS):
                arr = data_by_scenario[sc]
                if len(arr) == 0:
                    continue
                jitter = np.random.default_rng(42).uniform(-0.12, 0.12, size=len(arr))
                ax.scatter(
                    pos + jitter,
                    arr,
                    color=COLORS[sc],
                    alpha=0.25,
                    s=4,
                    zorder=2,
                )

            ax.set_xticks(positions)
            ax.set_xticklabels([LABELS[sc] for sc in SCENARIO_KEYS], fontsize=8)
            style_axis(ax, ylabel, title)

            y0, y1 = ax.get_ylim()
            ax.set_ylim(y0 - (y1 - y0) * 0.18, y1)
            annotate_stats(ax, positions, data_by_scenario)

        plt.tight_layout()
        save_figure(fig, f"distributions_{vclass}.pdf")


def plot_ecdf(dfs: dict) -> None:
    metrics = [
        ("duration", "Trip duration (s)"),
        ("waitingTime", "Waiting time (s)"),
        ("timeLoss", "Time loss (s)"),
        ("speed_ms", "Average speed (m/s)"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle("ECDF - Bicycles by scenario", fontsize=13, fontweight="bold")
    axes = axes.flatten()

    for ax, (col, xlabel) in zip(axes, metrics):
        for sc in SCENARIO_KEYS:
            vals = np.sort(
                dfs[sc][dfs[sc]["vClass"] == "bicycle"][col].dropna().values
            )
            if len(vals) == 0:
                continue
            ecdf = np.arange(1, len(vals) + 1) / len(vals)
            ax.plot(
                vals,
                ecdf,
                color=COLORS[sc],
                label=LABELS[sc].replace("\n", " "),
                linewidth=2,
            )

        ax.set_xlabel(xlabel, fontsize=9)
        ax.set_ylabel("F(x)", fontsize=9)
        ax.set_title(xlabel, fontsize=10, fontweight="bold")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, linestyle="--")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    plt.tight_layout()
    save_figure(fig, "ecdf_bikes.pdf")


def plot_safety_indicators(stats_dict: dict, collision_counts: dict) -> None:
    indicators = [
        ("bike_involved", "Bicycle-involved collisions", "collisions"),
        ("car_car", "Car-car collisions", "collisions"),
        ("emergencyBraking", "Emergency braking events", "safety"),
        ("total", "Teleports", "teleports"),
    ]

    indicator_labels = [label for _, label, _ in indicators]
    x = np.arange(len(indicator_labels))
    width = 0.25

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.suptitle("Safety indicators and collision diagnostics", fontsize=13, fontweight="bold")

    for i, sc in enumerate(SCENARIO_KEYS):
        values = []
        for key, _, section in indicators:
            if section == "collisions":
                values.append(int(collision_counts[sc].get(key, 0)))
            else:
                values.append(int(stats_dict[sc][section].get(key, 0)))

        bars = ax.bar(
            x + i * width,
            values,
            width,
            label=LABELS[sc].replace("\n", " "),
            color=COLORS[sc],
            alpha=0.85,
            edgecolor="white",
        )
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.8,
                str(val),
                ha="center",
                va="bottom",
                fontsize=9,
            )

    ax.set_xticks(x + width)
    ax.set_xticklabels(indicator_labels, fontsize=10)
    ax.set_ylabel("Count", fontsize=10)
    ax.legend(fontsize=9)
    ax.text(
        0.0,
        -0.18,
        "Note: bicycle-involved collisions are counted from SUMO collision-output. "
        "Emergency braking is the aggregate SUMO safety counter across all vehicles.",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8,
        color="dimgray",
    )
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    save_figure(fig, "safety_indicators.pdf")


def plot_aggregate_stats(stats_dict: dict) -> None:
    aggregate_metrics = [
        ("speed", "Average speed (m/s)"),
        ("duration", "Average duration (s)"),
        ("waitingTime", "Average waiting time (s)"),
        ("timeLoss", "Average time loss (s)"),
    ]

    fig, axes = plt.subplots(2, 4, figsize=(18, 8))
    fig.suptitle(
        "Aggregate metrics from SUMO statistics XML\nCars (top row) and bicycles (bottom row)",
        fontsize=12,
        fontweight="bold",
    )

    rows_config = [
        ("vehicles", "Cars"),
        ("bikes", "Bicycles"),
    ]

    x = np.arange(len(SCENARIO_KEYS))
    for row_idx, (section, row_title) in enumerate(rows_config):
        for col_idx, (key, ylabel) in enumerate(aggregate_metrics):
            ax = axes[row_idx, col_idx]
            values = [
                float(stats_dict[sc][section].get(key, 0))
                for sc in SCENARIO_KEYS
            ]
            bars = ax.bar(
                x,
                values,
                color=[COLORS[sc] for sc in SCENARIO_KEYS],
                alpha=0.85,
                edgecolor="white",
            )
            for bar, val in zip(bars, values):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height(),
                    f"{val:.1f}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )
            ax.set_title(f"{row_title} - {ylabel}", fontsize=9, fontweight="bold")
            ax.set_xticks(x)
            ax.set_xticklabels(
                [sc for sc in SCENARIO_KEYS],
                rotation=20,
                fontsize=8,
                ha="right",
            )
            ax.grid(axis="y", alpha=0.3, linestyle="--")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)

    plt.tight_layout()
    save_figure(fig, "aggregate_stats.pdf")


def statistical_tests(dfs: dict) -> pd.DataFrame:
    """Run two-sample KS tests between all scenario pairs for bicycle metrics."""
    print("\n-- Two-sample Kolmogorov-Smirnov tests (bicycles) --")
    metrics = ["duration", "waitingTime", "timeLoss", "speed_ms"]

    rows = []
    for metric in metrics:
        for i in range(len(SCENARIO_KEYS)):
            for j in range(i + 1, len(SCENARIO_KEYS)):
                sc1, sc2 = SCENARIO_KEYS[i], SCENARIO_KEYS[j]
                a = dfs[sc1][dfs[sc1]["vClass"] == "bicycle"][metric].dropna()
                b = dfs[sc2][dfs[sc2]["vClass"] == "bicycle"][metric].dropna()
                ks_stat, p_value = stats.ks_2samp(a, b)
                rows.append(
                    {
                        "metric": metric,
                        "scenario_1": sc1,
                        "scenario_2": sc2,
                        "KS_stat": round(ks_stat, 4),
                        "p_value": round(p_value, 6),
                        "significant_alpha_0_05": "YES" if p_value < 0.05 else "NO",
                    }
                )

    ks_df = pd.DataFrame(rows)
    print(ks_df.to_string(index=False))
    out = PLOTS_DIR / "ks_tests.csv"
    ks_df.to_csv(out, index=False)
    print(f"\n  Saved: {out.relative_to(ROOT)}")
    return ks_df


def print_summary(dfs: dict, stats_dict: dict, collision_counts: dict) -> None:
    print("\n-- Scenario summary --")
    headers = [
        "Scenario",
        "Cars",
        "Bikes",
        "Car speed",
        "Bike speed",
        "Bike wait",
        "Bike coll.",
        "Car coll.",
        "Braking",
        "Teleports",
    ]
    rows = []
    for sc in SCENARIO_KEYS:
        df = dfs[sc]
        scenario_stats = stats_dict[sc]
        rows.append(
            [
                sc,
                (df["vClass"] == "car").sum(),
                (df["vClass"] == "bicycle").sum(),
                f"{float(scenario_stats['vehicles'].get('speed', 0)):.2f}",
                f"{float(scenario_stats['bikes'].get('speed', 0)):.2f}",
                f"{float(scenario_stats['bikes'].get('waitingTime', 0)):.1f}",
                collision_counts[sc].get("bike_involved", "?"),
                collision_counts[sc].get("car_car", "?"),
                scenario_stats["safety"].get("emergencyBraking", "?"),
                scenario_stats["teleports"].get("total", "?"),
            ]
        )

    header_str = (
        "  {:20s} {:>7s} {:>7s} {:>10s} {:>11s} {:>10s} "
        "{:>11s} {:>10s} {:>9s} {:>10s}"
    ).format(*headers)
    print(header_str)
    print("  " + "-" * (len(header_str) - 2))
    for row in rows:
        print(
            (
                "  {:20s} {:>7} {:>7} {:>10} {:>11} {:>10} "
                "{:>11} {:>10} {:>9} {:>10}"
            ).format(*row)
        )


def main() -> None:
    print("=" * 70)
    print("  BeSafe SUMO - Scenario comparison")
    print("=" * 70)

    print("\n[1/6] Loading tripinfo CSV files...")
    dfs = {sc: load_tripinfo(prefix) for sc, prefix in SCENARIOS.items()}

    print("[2/6] Loading statistics XML files...")
    stats_dict = {sc: parse_stats(prefix) for sc, prefix in SCENARIOS.items()}

    print("[2b/6] Loading collision-output files...")
    collision_counts = {
        sc: load_collision_counts(prefix) for sc, prefix in SCENARIOS.items()
    }

    print_summary(dfs, stats_dict, collision_counts)

    print("\n[3/6] Plotting trip metric distributions...")
    plot_distributions(dfs)

    print("[4/6] Plotting bicycle ECDFs...")
    plot_ecdf(dfs)

    print("[5/6] Plotting safety indicators...")
    plot_safety_indicators(stats_dict, collision_counts)

    print("[6/6] Plotting aggregate statistics...")
    plot_aggregate_stats(stats_dict)

    statistical_tests(dfs)

    print(f"\nDone. Figures and tables written to: {PLOTS_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
