#!/usr/bin/env python3
"""Generate deterministic mixed car/bicycle demand for the Task 4 intersection."""

from __future__ import annotations

import argparse
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


SIM_DURATION_S = 3600.0
ROUTE_PATTERN = ("straight", "right", "straight", "left")

ARMS = {
    "N": {
        "right": ("N2C", "C2W"),
        "straight": ("N2C", "C2S"),
        "left": ("N2C", "C2E"),
    },
    "E": {
        "right": ("E2C", "C2N"),
        "straight": ("E2C", "C2W"),
        "left": ("E2C", "C2S"),
    },
    "S": {
        "right": ("S2C", "C2E"),
        "straight": ("S2C", "C2N"),
        "left": ("S2C", "C2W"),
    },
    "W": {
        "right": ("W2C", "C2S"),
        "straight": ("W2C", "C2E"),
        "left": ("W2C", "C2N"),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a SUMO route file for the four-arm Task 4 intersection. "
            "carpm and bikepm are vehicles per minute injected from each arm."
        )
    )
    parser.add_argument(
        "--carpm",
        required=True,
        type=float,
        help="cars per minute injected from each arm",
    )
    parser.add_argument(
        "--bikepm",
        required=True,
        type=float,
        help="bicycles per minute injected from each arm",
    )
    parser.add_argument(
        "--safefraction",
        required=True,
        type=float,
        help="fraction of bicycles using the safety-oriented profile, in [0, 1]",
    )
    parser.add_argument(
        "--outname",
        required=True,
        help="output route filename or base name, written under sumocfg/",
    )
    return parser.parse_args()


def clean_outname(outname: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", outname.strip())
    cleaned = cleaned.strip("._-") or "demand"
    if cleaned.endswith(".rou.xml"):
        cleaned = cleaned[: -len(".rou.xml")]
    return cleaned or "demand"


def validate_rate(name: str, value: float) -> None:
    if math.isnan(value) or math.isinf(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")


def validate_fraction(name: str, value: float) -> None:
    if math.isnan(value) or math.isinf(value) or value < 0 or value > 1:
        raise ValueError(f"{name} must be a finite number in [0, 1]")


def add_routes(root: ET.Element) -> None:
    for arm, movements in ARMS.items():
        for movement, edges in movements.items():
            ET.SubElement(
                root,
                "route",
                {
                    "id": f"{arm}_{movement}",
                    "edges": " ".join(edges),
                },
            )


def iter_departures(rate_per_minute: float, arm_index: int) -> list[float]:
    if rate_per_minute == 0:
        return []

    interval = 60.0 / rate_per_minute
    offset = arm_index * interval / len(ARMS)
    departures = []
    depart = offset
    while depart < SIM_DURATION_S:
        departures.append(depart)
        depart += interval
    return departures


def bike_type_for(safefraction: float, index: int) -> str:
    previous_safety_count = math.floor(index * safefraction)
    current_safety_count = math.floor((index + 1) * safefraction)
    if current_safety_count > previous_safety_count:
        return "bike_safety_oriented"
    return "bike_high_risk"


def add_flow_vehicles(
    root: ET.Element,
    mode: str,
    vehicle_type: str,
    rate_per_minute: float,
    safefraction: float,
) -> tuple[int, int, int]:
    count = 0
    safety_count = 0
    high_risk_count = 0
    for arm_index, arm in enumerate(ARMS):
        departures = iter_departures(rate_per_minute, arm_index)
        for local_index, depart in enumerate(departures):
            movement = ROUTE_PATTERN[local_index % len(ROUTE_PATTERN)]
            route_id = f"{arm}_{movement}"
            current_type = bike_type_for(safefraction, count) if mode == "bike" else vehicle_type
            if current_type == "bike_safety_oriented":
                safety_count += 1
            elif current_type == "bike_high_risk":
                high_risk_count += 1
            ET.SubElement(
                root,
                "vehicle",
                {
                    "id": f"{mode}_{arm}_{local_index:04d}",
                    "type": current_type,
                    "route": route_id,
                    "depart": f"{depart:.2f}",
                    "departLane": "best",
                    "departSpeed": "max",
                },
            )
            count += 1
    return count, safety_count, high_risk_count


def indent(element: ET.Element, level: int = 0) -> None:
    spaces = "\n" + level * "    "
    if len(element):
        if not element.text or not element.text.strip():
            element.text = spaces + "    "
        for child in element:
            indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = spaces
    if level and (not element.tail or not element.tail.strip()):
        element.tail = spaces


def sort_vehicles_by_depart(root: ET.Element) -> None:
    definitions = [child for child in root if child.tag != "vehicle"]
    vehicles = [child for child in root if child.tag == "vehicle"]
    vehicles.sort(key=lambda vehicle: (float(vehicle.attrib["depart"]), vehicle.attrib["id"]))
    root[:] = definitions + vehicles


def main() -> int:
    args = parse_args()
    try:
        validate_rate("carpm", args.carpm)
        validate_rate("bikepm", args.bikepm)
        validate_fraction("safefraction", args.safefraction)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    outname = clean_outname(args.outname)

    root = ET.Element(
        "routes",
        {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:noNamespaceSchemaLocation": "http://sumo.dlr.de/xsd/routes_file.xsd",
        },
    )
    add_routes(root)
    car_count, _, _ = add_flow_vehicles(root, "car", "car", args.carpm, args.safefraction)
    bike_count, safety_count, high_risk_count = add_flow_vehicles(
        root,
        "bike",
        "bike_safety_oriented",
        args.bikepm,
        args.safefraction,
    )
    sort_vehicles_by_depart(root)
    indent(root)

    outdir = Path(__file__).resolve().parents[1] / "sumocfg"
    outfile = outdir / f"{outname}.rou.xml"
    tree = ET.ElementTree(root)
    tree.write(outfile, encoding="UTF-8", xml_declaration=True)

    print(f"Wrote {outfile}")
    print(f"Safe fraction: {args.safefraction:.3f}")
    print(f"Cars: {car_count}")
    print(f"Bicycles: {bike_count}")
    print(f"  Safety-oriented bicycles: {safety_count}")
    print(f"  High-risk bicycles: {high_risk_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
