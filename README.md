# VIN Parts Finder

A small hackathon demo: type a VIN, decode it with the free **NHTSA vPIC** API, then see:

- the vehicle details, with a photo pulled from **Wikipedia**;
- a **visual position-by-position VIN breakdown**;
- compatible parts from a mock catalog, each with a **lowest-price vendor comparison**;
- an **AI chat** to ask about the vehicle, powered by **Claude Sonnet 4.5 on the Bosch
  LLM Farm**.

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

Dependencies (declared in `pyproject.toml`): `requests` and `anthropic[vertex]` (the
latter only for the AI chat).

### Enabling the AI chat (Bosch LLM Farm)

The chat calls **Claude Sonnet 4.5** through the Bosch LLM Farm. Set your farm
subscription key and run behind the proxy:

```powershell
& { $env:GENAIPLATFORM_FARM_SUBSCRIPTION_KEY="<your-farm-key>"; $env:HTTPS_PROXY="http://127.0.0.1:3128"; uv run main.py }
```

Without the key, everything else still works and the chat shows a friendly
"not configured" message. The key env var may also be `FARM_API_KEY` or
`MODEL_FARM_SUBSCRIPTION_KEY`. The chat and the vehicle image both route through
`HTTPS_PROXY` automatically (same proxy as the NHTSA call).

### Troubleshooting: "Could not reach the VIN decoding service"

If the API call fails with a `detail` mentioning *"the SSL module is not available"*
or *"DLL load failed while importing _ssl"*, Python can't find its OpenSSL DLLs. This
happens with **Anaconda on Windows when the conda env isn't activated** (the DLLs live
in `…\Anaconda3\Library\bin`, which isn't on `PATH`). `main.py` auto-adds those dirs at
startup, so this normally fixes itself; if you still hit it, run from an **Anaconda
Prompt** or `conda activate base` first, or use a non-conda Python (uv-managed CPython
includes SSL). Confirmed working: with the proxy set, the live decode returns
`HONDA Civic 2017` for VIN `2HGFC2F5XHH500000`.

## How it works

1. The browser sends the VIN to our backend: `GET /api/decode?vin=...`
2. `decode_vin()` in [`main.py`](main.py) calls the NHTSA `DecodeVinValues` endpoint
   and reads `Make`, `Model`, `ModelYear`, `BodyClass`.
3. [`vin_logic.filter_parts()`](vin_logic.py) selects catalog parts whose fitment
   matches (make + model case-insensitive, year within `yearMin..yearMax`).
4. [`vin_logic.vin_breakdown()`](vin_logic.py) splits the 17 characters into their
   ISO 3779 sections (WMI, VDS, check digit, model year, plant, serial) with a short
   explanation of each, disambiguating the model-year letter code with the decoded year.
5. [`main.fetch_vehicle_image()`](main.py) fetches a thumbnail from Wikipedia, and
   [`vin_logic.with_pricing()`](vin_logic.py) attaches a synthetic multi-vendor price
   comparison to each part.
6. The page renders the vehicle card (with photo), the color-coded VIN breakdown, the
   parts (with lowest-price vendor), and the AI chat panel. Invalid VINs and empty
   results show friendly messages.
7. Chat: the browser POSTs the conversation + vehicle context to `/api/chat`;
   [`llm.chat()`](llm.py) sends it to Claude Sonnet 4.5 on the farm via `AnthropicVertex`.

## Project layout

| File | Purpose |
|---|---|
| `main.py` | Entrypoint: stdlib HTTP server, routes, `decode_vin()` (NHTSA), Wikipedia image, `/api/chat` |
| `llm.py` | Bosch LLM Farm chat client (`AnthropicVertex`, Claude Sonnet 4.5) |
| `vin_logic.py` | Pure, offline-testable logic: `filter_parts`, `vin_breakdown`, vendor pricing, year codes |
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

## Notes

- **The parts catalog is synthetic demo data** — prices, descriptions, and fitment
  ranges are illustrative, not real fitment data.
- **Vendor prices are simulated**, derived deterministically from each part's list price
  — not live retailer data. (Real web-search pricing isn't available through the farm's
  Vertex-hosted Claude; it would require Gemini grounding, which we didn't use here.)
- The vehicle photo comes from Wikipedia and may not match the exact trim/year.
- The code is kept compatible with Python 3.9+ so the offline logic/tests run on older
  interpreters too, though the project targets 3.13.
