#!/usr/bin/env python3
"""Analyze SUMO surrogate safety measure outputs for Task 4 scenarios."""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/sumo-besafe-matplotlib")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


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


def vehicle_class(vehicle_id: str) -> str:
    vehicle_id = str(vehicle_id).lower()
    if vehicle_id.startswith("bike"):
        return "bicycle"
    if vehicle_id.startswith("car"):
        return "car"
    return "other"


def to_float(value: str | None) -> float:
    if value is None or str(value).strip().upper() == "NA":
        return np.nan
    return float(value)


def interaction(ego_class: str, foe_class: str) -> str:
    classes = sorted([ego_class, foe_class])
    if classes == ["bicycle", "car"]:
        return "car-bicycle"
    if classes == ["bicycle", "bicycle"]:
        return "bicycle-bicycle"
    if classes == ["car", "car"]:
        return "car-car"
    return "other"


def is_crossing_type(type_code: str | None) -> bool:
    return type_code in {"6", "7", "10", "11", "12", "13", "17"}


def load_ssm(prefix: str, scenario: str) -> pd.DataFrame:
    """Load and flatten one SUMO SSM XML file."""
    path = RESULTS_DIR / f"{prefix}_ssm.xml"
    if not path.exists():
        sys.exit(f"[ERROR] Missing SSM file: {path}")

    root = ET.parse(path).getroot()
    rows = []
    for idx, conflict in enumerate(root.findall("conflict")):
        ego = conflict.attrib.get("ego", "")
        foe = conflict.attrib.get("foe", "")
        ego_class = vehicle_class(ego)
        foe_class = vehicle_class(foe)

        min_ttc = conflict.find("minTTC")
        max_drac = conflict.find("maxDRAC")
        pet = conflict.find("PET")

        min_ttc_type = min_ttc.attrib.get("type") if min_ttc is not None else None
        max_drac_type = max_drac.attrib.get("type") if max_drac is not None else None
        pet_type = pet.attrib.get("type") if pet is not None else None
        pet_value = to_float(pet.attrib.get("value") if pet is not None else None)
        pair = tuple(sorted([ego, foe]))

        crossing_conflict = (
            not np.isnan(pet_value)
            or is_crossing_type(min_ttc_type)
            or is_crossing_type(max_drac_type)
            or is_crossing_type(pet_type)
        )

        rows.append(
            {
                "scenario": scenario,
                "conflict_index": idx,
                "pair_id": "|".join(pair),
                "begin": to_float(conflict.attrib.get("begin")),
                "end": to_float(conflict.attrib.get("end")),
                "ego": ego,
                "foe": foe,
                "ego_class": ego_class,
                "foe_class": foe_class,
                "interaction": interaction(ego_class, foe_class),
                "bike_involved": ego_class == "bicycle" or foe_class == "bicycle",
                "crossing_conflict": crossing_conflict,
                "min_ttc": to_float(min_ttc.attrib.get("value") if min_ttc is not None else None),
                "min_ttc_time": to_float(min_ttc.attrib.get("time") if min_ttc is not None else None),
                "min_ttc_type": min_ttc_type,
                "max_drac": to_float(max_drac.attrib.get("value") if max_drac is not None else None),
                "max_drac_time": to_float(max_drac.attrib.get("time") if max_drac is not None else None),
                "max_drac_type": max_drac_type,
                "pet": pet_value,
                "pet_time": to_float(pet.attrib.get("time") if pet is not None else None),
                "pet_type": pet_type,
            }
        )

    return pd.DataFrame(rows)


def pair_level(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse duplicated ego/foe SSM logs into one row per pair-time conflict."""
    if df.empty:
        return df.copy()

    return (
        df.groupby(["scenario", "pair_id", "begin", "end"], dropna=False)
        .agg(
            interaction=("interaction", "first"),
            bike_involved=("bike_involved", "max"),
            crossing_conflict=("crossing_conflict", "max"),
            min_ttc=("min_ttc", "min"),
            max_drac=("max_drac", "max"),
            pet=("pet", "min"),
        )
        .reset_index()
    )


def count_true(series: pd.Series) -> int:
    return int(series.fillna(False).sum())


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    pair_df = pair_level(df)
    rows = []
    for scenario in SCENARIO_KEYS:
        sc = pair_df[pair_df["scenario"] == scenario]
        bicycle = sc[sc["bike_involved"]]
        bicycle_crossing = bicycle[bicycle["crossing_conflict"]]

        rows.append(
            {
                "scenario": scenario,
                "pair_conflicts": int(len(sc)),
                "bike_involved_conflicts": int(len(bicycle)),
                "bike_crossing_conflicts": int(len(bicycle_crossing)),
                "car_bicycle_conflicts": int((sc["interaction"] == "car-bicycle").sum()),
                "bicycle_bicycle_conflicts": int((sc["interaction"] == "bicycle-bicycle").sum()),
                "car_car_conflicts": int((sc["interaction"] == "car-car").sum()),
                "bike_ttc_le_1_5": count_true(bicycle["min_ttc"] <= 1.5),
                "bike_ttc_le_3_0": count_true(bicycle["min_ttc"] <= 3.0),
                "bike_drac_ge_3_0": count_true(bicycle["max_drac"] >= 3.0),
                "bike_pet_le_2_0": count_true(bicycle["pet"] <= 2.0),
                "bike_crossing_ttc_le_1_5": count_true(bicycle_crossing["min_ttc"] <= 1.5),
                "bike_crossing_drac_ge_3_0": count_true(bicycle_crossing["max_drac"] >= 3.0),
                "bike_crossing_pet_le_2_0": count_true(bicycle_crossing["pet"] <= 2.0),
                "bike_min_ttc_median": round(float(bicycle["min_ttc"].median()), 3)
                if bicycle["min_ttc"].notna().any()
                else np.nan,
                "bike_crossing_min_ttc_median": round(float(bicycle_crossing["min_ttc"].median()), 3)
                if bicycle_crossing["min_ttc"].notna().any()
                else np.nan,
                "bike_max_drac_p95": round(float(bicycle["max_drac"].quantile(0.95)), 3)
                if bicycle["max_drac"].notna().any()
                else np.nan,
                "bike_crossing_max_drac_p95": round(float(bicycle_crossing["max_drac"].quantile(0.95)), 3)
                if bicycle_crossing["max_drac"].notna().any()
                else np.nan,
                "bike_pet_median": round(float(bicycle["pet"].median()), 3)
                if bicycle["pet"].notna().any()
                else np.nan,
            }
        )

    return pd.DataFrame(rows)


def plot_counts(summary: pd.DataFrame) -> None:
    metrics = [
        ("bike_crossing_conflicts", "Bicycle crossing conflicts"),
        ("bike_crossing_ttc_le_1_5", "Crossing TTC <= 1.5 s"),
        ("bike_crossing_drac_ge_3_0", "Crossing DRAC >= 3 m/s^2"),
        ("bike_crossing_pet_le_2_0", "Crossing PET <= 2 s"),
    ]

    x = np.arange(len(metrics))
    width = 0.25
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.suptitle(
        "SSM indicators for bicycle-involved crossing conflicts",
        fontsize=13,
        fontweight="bold",
    )

    for i, scenario in enumerate(SCENARIO_KEYS):
        row = summary[summary["scenario"] == scenario].iloc[0]
        values = [int(row[key]) for key, _ in metrics]
        bars = ax.bar(
            x + i * width,
            values,
            width,
            label=LABELS[scenario].replace("\n", " "),
            color=COLORS[scenario],
            alpha=0.85,
            edgecolor="white",
        )
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.8,
                str(value),
                ha="center",
                va="bottom",
                fontsize=8,
            )

    ax.set_xticks(x + width)
    ax.set_xticklabels([label for _, label in metrics], fontsize=10)
    ax.set_ylabel("Pair-level count")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    save_figure(fig, "ssm_bike_conflicts.pdf")


def plot_ttc_distribution(df: pd.DataFrame) -> None:
    pair_df = pair_level(df)
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle(
        "Minimum TTC distribution for bicycle-involved crossing conflicts",
        fontsize=13,
        fontweight="bold",
    )

    data = []
    positions = []
    colors = []
    for pos, scenario in enumerate(SCENARIO_KEYS):
        vals = pair_df[
            (pair_df["scenario"] == scenario)
            & (pair_df["bike_involved"])
            & (pair_df["crossing_conflict"])
            & pair_df["min_ttc"].notna()
        ]["min_ttc"].clip(upper=5)
        if len(vals) == 0:
            vals = pd.Series([np.nan])
        data.append(vals.dropna().values if vals.notna().any() else np.array([0]))
        positions.append(pos)
        colors.append(COLORS[scenario])

    violin = ax.violinplot(
        data,
        positions=positions,
        showmedians=True,
        showextrema=True,
        widths=0.6,
    )
    for body, color in zip(violin["bodies"], colors):
        body.set_facecolor(color)
        body.set_alpha(0.65)
        body.set_edgecolor("white")
    violin["cmedians"].set_color("white")
    for part in ("cmaxes", "cmins", "cbars"):
        violin[part].set_color("gray")

    ax.axhline(1.5, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax.text(2.35, 1.52, "1.5 s", va="bottom", ha="right", fontsize=8, color="dimgray")
    ax.set_xticks(positions)
    ax.set_xticklabels([LABELS[sc] for sc in SCENARIO_KEYS], fontsize=9)
    ax.set_ylabel("Minimum TTC (s), clipped at 5 s")
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    save_figure(fig, "ssm_min_ttc_bikes.pdf")


def main() -> int:
    print("=" * 70)
    print("  BeSafe SUMO - SSM analysis")
    print("=" * 70)

    frames = [load_ssm(prefix, scenario) for scenario, prefix in SCENARIOS.items()]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    pair_df = pair_level(df)
    summary = summarize(df)

    details_out = PLOTS_DIR / "ssm_conflicts_detail.csv"
    pair_out = PLOTS_DIR / "ssm_conflicts_pair_level.csv"
    summary_out = PLOTS_DIR / "ssm_summary.csv"

    df.to_csv(details_out, index=False)
    pair_df.to_csv(pair_out, index=False)
    summary.to_csv(summary_out, index=False)

    print("\n-- Pair-level SSM summary --")
    print(summary.to_string(index=False))
    print(f"\n  Saved: {details_out.relative_to(ROOT)}")
    print(f"  Saved: {pair_out.relative_to(ROOT)}")
    print(f"  Saved: {summary_out.relative_to(ROOT)}")

    plot_counts(summary)
    plot_ttc_distribution(df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
