"""VIN Parts Finder - Python web app (stdlib http.server).

Run:  python main.py   (or: uv run main.py)   then open http://localhost:8000

The only outbound network call is decode_vin(), which hits the free NHTSA API
via `requests` (same endpoint the team's original main.py used). Everything else
- serving the page, filtering the catalog, building the VIN breakdown - is local.
"""

import json
import logging
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import vin_logic

try:
    import requests
except ImportError:  # requests is optional; we fall back to urllib (stdlib)
    requests = None

# Debug logging. On by default; set DEBUG=0 to quiet it down.
DEBUG = os.environ.get("DEBUG", "1").lower() not in ("0", "false", "no", "")
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vin")

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates")
STATIC = os.path.join(HERE, "static")
PORT = int(os.environ.get("PORT", "8000"))

_STATIC_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".html": "text/html; charset=utf-8",
}


def decode_vin(vin, model_year=None):
    """Decode a VIN via the NHTSA DecodeVinValues endpoint.

    Returns Results[0]: a flat dict of decoded fields (Make, Model, ModelYear,
    BodyClass, ErrorCode, ErrorText, ...). Uses `requests` when available and
    otherwise falls back to the standard library, so no install is required.
    """
    params = {"format": "json"}
    if model_year:
        params["modelyear"] = model_year

    backend = "requests" if requests is not None else "urllib"
    log.debug("decode_vin: vin=%s year=%s backend=%s", vin, model_year, backend)

    if requests is not None:
        url = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{}".format(vin)
        resp = requests.get(url, params=params, timeout=30)
        log.debug("decode_vin: GET %s -> HTTP %s", resp.url, resp.status_code)
        resp.raise_for_status()
        return resp.json()["Results"][0]

    # stdlib fallback (no external dependencies needed)
    url = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{}?{}".format(
        urllib.parse.quote(vin), urllib.parse.urlencode(params)
    )
    with urllib.request.urlopen(url, timeout=30) as handle:
        log.debug("decode_vin: GET %s -> HTTP %s", url, handle.status)
        data = json.loads(handle.read().decode("utf-8"))
    return data["Results"][0]


def build_decode_payload(vin):
    """Decode + filter + breakdown for a VIN. Returns the JSON-able response dict.

    Any error (bad input, network failure, NHTSA error code) is returned as a
    friendly {"error": ...} rather than raising, so the UI can show a message.
    """
    vin = (vin or "").strip().upper()
    log.info("build_decode_payload: vin=%r", vin)

    if len(vin) != 17:
        log.warning("rejecting vin %r: length %d != 17", vin, len(vin))
        return {"error": "Please enter a valid 17-character VIN."}

    try:
        decoded = decode_vin(vin)
    except Exception as exc:  # network/SSL/HTTP problems land here
        log.exception("decode_vin failed for %s", vin)
        return {
            "error": "Could not reach the VIN decoding service. "
                     "Check your connection and try again.",
            "detail": "{}: {}".format(type(exc).__name__, exc),
        }

    make = (decoded.get("Make") or "").strip()
    model = (decoded.get("Model") or "").strip()
    model_year = (decoded.get("ModelYear") or "").strip()
    body_class = (decoded.get("BodyClass") or "").strip()
    error_code = (decoded.get("ErrorCode") or "").strip()
    log.debug(
        "decoded: make=%r model=%r year=%r body=%r errorCode=%r",
        make, model, model_year, body_class, error_code,
    )

    # ErrorCode "0" is a clean decode; anything else with no Make/Model is unusable.
    clean = error_code.split(",")[0].strip() in ("", "0")
    if not make:
        log.warning("vin %s decoded but no Make; returning error", vin)
        return {
            "error": "That VIN could not be decoded. Please double-check it and try again.",
            "error_text": (decoded.get("ErrorText") or "").strip(),
        }

    year_int = None
    try:
        year_int = int(model_year)
    except (TypeError, ValueError):
        year_int = None

    parts = vin_logic.filter_parts(make, model, year_int, vin_logic.load_catalog())
    breakdown = vin_logic.vin_breakdown(vin, year_int)
    log.info(
        "vin %s -> %s %s %s | %d part(s) | clean=%s",
        vin, make, model or "Unknown", model_year or "?", len(parts), clean,
    )

    return {
        "vehicle": {
            "make": make,
            "model": model or "Unknown",
            "modelYear": model_year,
            "bodyClass": body_class or "Unknown",
        },
        "breakdown": breakdown,
        "parts": parts,
        "clean": clean,
        "errorText": (decoded.get("ErrorText") or "").strip(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "VINPartsFinder/1.0"

    def log_message(self, format, *args):  # route stdlib access logs through our logger
        log.debug("http: %s", format % args)

    def _send(self, status, body, content_type):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, status=200):
        self._send(status, json.dumps(obj), "application/json; charset=utf-8")

    def _serve_file(self, path, content_type):
        try:
            with open(path, "rb") as handle:
                self._send(200, handle.read(), content_type)
        except FileNotFoundError:
            self._send(404, "Not found", "text/plain; charset=utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path

        if route == "/" or route == "/index.html":
            self._serve_file(os.path.join(TEMPLATES, "index.html"),
                             "text/html; charset=utf-8")
            return

        if route == "/api/decode":
            vin = (parse_qs(parsed.query).get("vin", [""])[0])
            self._send_json(build_decode_payload(vin))
            return

        if route.startswith("/static/"):
            rel = route[len("/static/"):]
            # prevent path traversal
            safe = os.path.normpath(rel).replace("\\", "/")
            if safe.startswith("..") or safe.startswith("/"):
                self._send(403, "Forbidden", "text/plain; charset=utf-8")
                return
            full = os.path.join(STATIC, safe)
            ext = os.path.splitext(full)[1].lower()
            self._serve_file(full, _STATIC_TYPES.get(ext, "application/octet-stream"))
            return

        self._send(404, "Not found", "text/plain; charset=utf-8")


def main():
    proxies = {k: v for k, v in os.environ.items() if k.lower().endswith("_proxy")}
    log.info("HTTP backend: %s", "requests" if requests is not None else "urllib (stdlib)")
    log.info("proxy env: %s", proxies or "none")
    log.info("debug logging: %s", "on" if DEBUG else "off (set DEBUG=1 to enable)")

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("VIN Parts Finder running at http://localhost:{}".format(PORT))
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
