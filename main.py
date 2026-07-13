"""VIN Parts Finder - Python web app (stdlib http.server).

Run:  python main.py   (or: uv run main.py)   then open http://localhost:8000

The only outbound network call is decode_vin(), which hits the free NHTSA API
via `requests` (same endpoint the team's original main.py used). Everything else
- serving the page, filtering the catalog, building the VIN breakdown - is local.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import vin_logic

try:
    import requests
except ImportError:  # pragma: no cover - requests is declared in pyproject
    requests = None

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
    BodyClass, ErrorCode, ErrorText, ...). Mirrors the team's original helper.
    """
    if requests is None:
        raise RuntimeError("The 'requests' package is required (see pyproject.toml).")
    url = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{}".format(vin)
    params = {"format": "json"}
    if model_year:
        params["modelyear"] = model_year
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()["Results"][0]


def build_decode_payload(vin):
    """Decode + filter + breakdown for a VIN. Returns the JSON-able response dict.

    Any error (bad input, network failure, NHTSA error code) is returned as a
    friendly {"error": ...} rather than raising, so the UI can show a message.
    """
    vin = (vin or "").strip().upper()

    if len(vin) != 17:
        return {"error": "Please enter a valid 17-character VIN."}

    try:
        decoded = decode_vin(vin)
    except Exception as exc:  # network/SSL/HTTP problems land here
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

    # ErrorCode "0" is a clean decode; anything else with no Make/Model is unusable.
    clean = error_code.split(",")[0].strip() in ("", "0")
    if not make or not model:
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

    return {
        "vehicle": {
            "make": make,
            "model": model,
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

    def log_message(self, fmt, *args):  # keep the console tidy for a live demo
        pass

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
