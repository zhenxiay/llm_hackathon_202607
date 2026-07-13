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
BATCH_LIMIT = 50  # Max VINs the vPIC batch endpoint accepts per request.


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


def decode_vins(
    vin_year_pairs: Iterable[tuple[str, int | None]]
) -> list[dict]:
    """Decode any number of VINs, chunking into batches of BATCH_LIMIT."""
    pairs = list(vin_year_pairs)
    results: list[dict] = []
    for start in range(0, len(pairs), BATCH_LIMIT):
        results.extend(decode_vin_batch(pairs[start:start + BATCH_LIMIT]))
    return results


def read_vins_from_file(path: str) -> list[str]:
    """Read VINs from a file, one per line, ignoring blanks and comments."""
    vins: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            vin = line.strip()
            if vin and not vin.startswith("#"):
                vins.append(vin)
    return vins


def print_populated(data: dict) -> None:
    """Print only the fields that have a value."""
    for key, value in data.items():
        if value not in ("", None):
            print(f"{key}: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Decode VIN specification data via the NHTSA vPIC API."
    )
    parser.add_argument(
        "vin", nargs="*", help="One or more VINs to decode."
    )
    parser.add_argument(
        "--file", "-f",
        help="Read VINs from a file (one per line; # lines ignored).",
    )
    parser.add_argument(
        "--limit", "-n", type=int, default=None,
        help="Decode only the first N VINs from the input.",
    )
    parser.add_argument(
        "--year", type=int, default=None, help="Model year (improves accuracy)."
    )
    parser.add_argument(
        "--json", action="store_true", help="Output raw JSON instead of key: value."
    )
    args = parser.parse_args(argv)

    vins = list(args.vin)
    if args.file:
        vins.extend(read_vins_from_file(args.file))
    if not vins:
        parser.error("no VINs provided; pass them as arguments or via --file")
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be a positive integer")
        vins = vins[: args.limit]

    if len(vins) == 1:
        result = decode_vin(vins[0], args.year)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_populated(result)
    else:
        results = decode_vins((vin, args.year) for vin in vins)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                print(f"{r.get('VIN')}: {r.get('ModelYear')} "
                      f"{r.get('Make')} {r.get('Model')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
