"""Decode VIN data using the NHTSA vPIC API.

The vPIC API is a vehicle *specification* decoder. It returns make, model,
year, body class, engine info, plant info, etc. It does NOT return orderable
replacement part numbers for a VIN.

Uses only the Python standard library (no external dependencies).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from typing import Iterable

BASE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles"
TIMEOUT = 30


def decode_vin(vin: str, model_year: int | None = None) -> dict:
    """Decode a single VIN into a flat dictionary of specification fields."""
    params = {"format": "json"}
    if model_year:
        params["modelyear"] = str(model_year)

    url = f"{BASE_URL}/DecodeVinValues/{urllib.parse.quote(vin)}?" + \
        urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["Results"][0]


def decode_vin_batch(vin_year_pairs: Iterable[tuple[str, int | None]]) -> list[dict]:
    """Decode up to 50 VINs in a single request.

    Each item is a (vin, model_year) pair; model_year may be None.
    """
    payload = ";".join(
        f"{vin},{year}" if year else vin for vin, year in vin_year_pairs
    )
    body = urllib.parse.urlencode({"format": "json", "data": payload}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/DecodeVINValuesBatch/",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["Results"]


def print_populated(data: dict) -> None:
    """Print only the fields that have a value."""
    for key, value in data.items():
        if value not in ("", None):
            print(f"{key}: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Decode VIN specification data via the NHTSA vPIC API."
    )
    parser.add_argument("vin", nargs="+", help="One or more VINs to decode.")
    parser.add_argument(
        "--year", type=int, default=None, help="Model year (improves accuracy)."
    )
    parser.add_argument(
        "--json", action="store_true", help="Output raw JSON instead of key: value."
    )
    args = parser.parse_args(argv)

    if len(args.vin) == 1:
        result = decode_vin(args.vin[0], args.year)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_populated(result)
    else:
        results = decode_vin_batch((vin, args.year) for vin in args.vin)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                print(f"{r.get('VIN')}: {r.get('ModelYear')} "
                      f"{r.get('Make')} {r.get('Model')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
