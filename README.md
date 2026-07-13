# VIN Decoder (NHTSA vPIC)

Decode vehicle specification data from a VIN using the free NHTSA vPIC API
(no API key required). Uses only the Python standard library — nothing to install.

## Usage

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

## Note on part numbers

The vPIC API decodes vehicle *specifications* (make, model, year, engine,
body class, plant, etc.). It does **not** return orderable replacement part
numbers for a VIN. Its `GetParts` endpoint only lists manufacturer regulatory
compliance documents (565/566 submittals) by date range — not mechanical parts.
For VIN-to-parts lookups you need an OEM/third-party parts catalog.
