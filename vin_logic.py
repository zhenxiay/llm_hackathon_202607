"""Pure, offline-testable VIN logic for VIN Parts Finder.

Nothing in this module touches the network, so it runs and tests identically on
the local Python 3.9 and the team's Python 3.13. Kept 3.9-compatible on purpose
(no match-statements, no PEP 604 runtime unions).
"""

import json
import os

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parts_catalog.json")

# Letters never valid anywhere in a VIN (avoid confusion with 0/1).
INVALID_VIN_LETTERS = {"I", "O", "Q"}

# Model-year code -> year. The letter code repeats on a 30-year cycle, so a code
# can mean e.g. 1990 or 2020; we disambiguate with the NHTSA-decoded year when we
# have it. 0, I, O, Q, U, Z are excluded from year codes.
# Base cycle starting 1980; we build 1980-2039 so both cycles are represented.
_YEAR_CODE_SEQUENCE = [
    "A", "B", "C", "D", "E", "F", "G", "H", "J", "K",
    "L", "M", "N", "P", "R", "S", "T", "V", "W", "X",
    "Y", "1", "2", "3", "4", "5", "6", "7", "8", "9",
]


def _build_year_code_map():
    """code -> [possible years] across the 1980-2039 range."""
    mapping = {}
    for cycle_start in (1980, 2010):
        for offset, code in enumerate(_YEAR_CODE_SEQUENCE):
            year = cycle_start + offset
            mapping.setdefault(code, []).append(year)
    return mapping


MODEL_YEAR_CODES = _build_year_code_map()


def load_catalog(path=CATALOG_PATH):
    """Load the parts catalog JSON and return the list of parts."""
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data.get("parts", [])


def filter_parts(make, model, year, catalog=None):
    """Return catalog parts whose fitment matches the vehicle.

    Match rules: make and model compared case-insensitively; year must fall
    within [yearMin, yearMax] inclusive. Unknown/blank inputs match nothing.
    """
    if catalog is None:
        catalog = load_catalog()

    if not make or not model:
        return []

    make_l = str(make).strip().lower()
    model_l = str(model).strip().lower()

    try:
        year_i = int(year)
    except (TypeError, ValueError):
        return []

    matches = []
    for part in catalog:
        fitment = part.get("fitment", {})
        makes = [m.lower() for m in fitment.get("makes", [])]
        models = [m.lower() for m in fitment.get("models", [])]
        if make_l not in makes:
            continue
        if model_l not in models:
            continue
        year_min = fitment.get("yearMin")
        year_max = fitment.get("yearMax")
        if year_min is not None and year_i < year_min:
            continue
        if year_max is not None and year_i > year_max:
            continue
        matches.append(part)
    return matches


def _resolve_year(code, decoded_year):
    """Pick the actual model year for a code, disambiguating the 30-year cycle."""
    candidates = MODEL_YEAR_CODES.get(code.upper())
    if not candidates:
        return None
    if decoded_year:
        try:
            decoded_year = int(decoded_year)
        except (TypeError, ValueError):
            decoded_year = None
    if decoded_year and decoded_year in candidates:
        return decoded_year
    # No authoritative year: prefer the most recent plausible cycle (<= 2039).
    return candidates[-1]


def vin_breakdown(vin, decoded_year=None):
    """Break a 17-char VIN into its ISO 3779 sections with labels and notes.

    Returns a dict with the normalized VIN, a validity flag, and a list of
    segment dicts: {positions, chars, key, label, note}. Segments follow the
    Wikipedia/ISO layout: 1-3 WMI, 4-8 VDS, 9 check digit, 10 model year,
    11 plant, 12-17 serial.
    """
    vin = (vin or "").strip().upper()

    result = {"vin": vin, "valid_length": len(vin) == 17, "segments": []}

    if len(vin) != 17:
        result["error"] = "A VIN must be exactly 17 characters."
        return result

    bad_letters = sorted({c for c in vin if c in INVALID_VIN_LETTERS})
    if bad_letters:
        result["warning"] = (
            "The letters " + ", ".join(bad_letters) + " are never used in a VIN "
            "(they look like 0/1)."
        )

    year_char = vin[9]
    resolved_year = _resolve_year(year_char, decoded_year)
    year_note = "Model year"
    if resolved_year:
        year_note = "Model year -> {} (code '{}')".format(resolved_year, year_char)

    segments = [
        {
            "positions": "1-3",
            "chars": vin[0:3],
            "key": "wmi",
            "label": "WMI",
            "note": "World Manufacturer Identifier (position 1 = region/country)",
        },
        {
            "positions": "4-8",
            "chars": vin[3:8],
            "key": "vds",
            "label": "VDS",
            "note": "Vehicle Descriptor Section (body, engine, model attributes)",
        },
        {
            "positions": "9",
            "chars": vin[8],
            "key": "check",
            "label": "Check digit",
            "note": "Validates the VIN (0-9 or X)",
        },
        {
            "positions": "10",
            "chars": vin[9],
            "key": "year",
            "label": "Model year",
            "note": year_note,
        },
        {
            "positions": "11",
            "chars": vin[10],
            "key": "plant",
            "label": "Plant",
            "note": "Assembly plant code",
        },
        {
            "positions": "12-17",
            "chars": vin[11:17],
            "key": "serial",
            "label": "Serial",
            "note": "Sequential production number",
        },
    ]
    result["segments"] = segments
    result["model_year"] = resolved_year
    return result


def _selftest():
    """Offline self-test covering the plan's assertions."""
    catalog = load_catalog()
    assert len(catalog) >= 12, "expected ~12 parts, got {}".format(len(catalog))

    # In-range vehicles should yield matches.
    civic = filter_parts("HONDA", "Civic", 2017, catalog)
    camry = filter_parts("TOYOTA", "Camry", 2012, catalog)
    f150 = filter_parts("FORD", "F-150", 2021, catalog)
    assert civic, "Civic 2017 should match parts"
    assert camry, "Camry 2012 should match parts"
    assert f150, "F-150 2021 should match parts"

    # Case-insensitivity.
    assert filter_parts("honda", "civic", 2017, catalog), "match should be case-insensitive"

    # 2003 Accord is out of range (catalog starts 2010) -> no matches.
    accord_2003 = filter_parts("HONDA", "Accord", 2003, catalog)
    assert accord_2003 == [], "2003 Accord should match no parts, got {}".format(len(accord_2003))

    # Unknown / blank inputs match nothing.
    assert filter_parts("", "Civic", 2017, catalog) == []
    assert filter_parts("Honda", "", 2017, catalog) == []

    # VIN breakdown assertions for a verified VIN.
    bd = vin_breakdown("2HGFC2F5XHH500000", 2017)
    assert bd["valid_length"] is True
    seg = {s["key"]: s for s in bd["segments"]}
    assert seg["wmi"]["chars"] == "2HG", seg["wmi"]["chars"]
    assert seg["check"]["chars"] == "X", seg["check"]["chars"]
    assert seg["year"]["chars"] == "H", seg["year"]["chars"]
    assert bd["model_year"] == 2017, bd["model_year"]
    assert seg["plant"]["chars"] == "H", seg["plant"]["chars"]
    assert seg["serial"]["chars"] == "500000", seg["serial"]["chars"]

    # Short VIN is reported, not crashed on.
    short = vin_breakdown("12345")
    assert short["valid_length"] is False and "error" in short

    # Year-code disambiguation: 'H' -> 2017 when told, else newest cycle (2017).
    assert _resolve_year("H", None) == 2017
    assert _resolve_year("H", 1987) == 1987

    print("vin_logic self-test: OK ({} parts)".format(len(catalog)))


if __name__ == "__main__":
    _selftest()
