# VIN Parts Finder

A small hackathon demo: type a VIN, decode it with the free **NHTSA vPIC** API, see
the vehicle details, a **visual position-by-position VIN breakdown**, and a list of
compatible parts from a mock catalog.

Backend logic lives in Python; the frontend is plain HTML/CSS/JS served by Python's
standard-library `http.server` — no build step, no JS framework.

## Run

Requires network access (to reach the NHTSA API) and Python 3.13 (per the repo).

```bash
uv run main.py
# or, with a plain interpreter:
python main.py
```

### Behind a proxy (Windows / PowerShell)

If outbound HTTPS must go through a local proxy (e.g. Squid on port 3128), set
`HTTPS_PROXY` for the run. `requests` picks it up automatically:

```powershell
& { $env:HTTPS_PROXY="http://127.0.0.1:3128"; uv run main.py }
```

Then open <http://localhost:8000>. Set `PORT` to change the port.

Only one dependency is needed: `requests` (declared in `pyproject.toml`).

## How it works

1. The browser sends the VIN to our backend: `GET /api/decode?vin=...`
2. `decode_vin()` in [`main.py`](main.py) calls the NHTSA `DecodeVinValues` endpoint
   and reads `Make`, `Model`, `ModelYear`, `BodyClass`.
3. [`vin_logic.filter_parts()`](vin_logic.py) selects catalog parts whose fitment
   matches (make + model case-insensitive, year within `yearMin..yearMax`).
4. [`vin_logic.vin_breakdown()`](vin_logic.py) splits the 17 characters into their
   ISO 3779 sections (WMI, VDS, check digit, model year, plant, serial) with a short
   explanation of each, disambiguating the model-year letter code with the decoded year.
5. The page renders the vehicle card, the color-coded VIN breakdown, and the parts.
   Invalid VINs and empty results show friendly messages.

## Project layout

| File | Purpose |
|---|---|
| `main.py` | Entrypoint: stdlib HTTP server, routes, `decode_vin()` (NHTSA call) |
| `vin_logic.py` | Pure, offline-testable logic: `filter_parts`, `vin_breakdown`, year codes |
| `vin_decoder.py` | Standalone CLI VIN decoder (stdlib only, batch support) |
| `parts_catalog.json` | ~12 mock parts with fitment rules |
| `templates/index.html` | Page markup |
| `static/style.css`, `static/app.js` | Styling and frontend logic |

## Verified sample VINs

These decode cleanly against the live NHTSA API (Error Code 0):

| VIN | Vehicle | Result |
|---|---|---|
| `2HGFC2F5XHH500000` | 2017 Honda Civic | matching parts + breakdown |
| `4T1BF1FK2CU500000` | 2012 Toyota Camry | matching parts |
| `1FTFW1E57MF500000` | 2021 Ford F-150 | matching parts |
| `1HGCM82633A004352` | 2003 Honda Accord | "no matching parts" (before catalog year range) |

## Tests

```bash
python vin_logic.py
```

Runs an offline self-test of the parts filtering and VIN breakdown (no network needed).

## CLI decoder (`vin_decoder.py`)

A standalone command-line VIN decoder that uses only the Python standard library
(no dependencies).

Decode a single VIN:

```bash
python vin_decoder.py 5UXWX7C5XBA --year 2011
```

Decode a partial VIN (use `*` for the check digit):

```bash
python vin_decoder.py "5UXWX7C5*BA" --year 2011
```

Decode multiple VINs in one batch (up to 50):

```bash
python vin_decoder.py 5UXWX7C5XBA 5YJSA3DS9EF
```

Raw JSON output:

```bash
python vin_decoder.py 5UXWX7C5XBA --year 2011 --json
```

### Note on part numbers

The vPIC API decodes vehicle *specifications* (make, model, year, engine,
body class, plant, etc.). It does **not** return orderable replacement part
numbers for a VIN. Its `GetParts` endpoint only lists manufacturer regulatory
compliance documents (565/566 submittals) by date range — not mechanical parts.
For VIN-to-parts lookups you need an OEM/third-party parts catalog.

## Notes

- **The parts catalog is synthetic demo data** — prices, descriptions, and fitment
  ranges are illustrative, not real fitment data.
- The code is kept compatible with Python 3.9+ so the offline logic/tests run on older
  interpreters too, though the project targets 3.13.
