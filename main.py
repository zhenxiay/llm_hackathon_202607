"""VIN Parts Finder - Python web app (stdlib http.server).

Run:  python main.py   (or: uv run main.py)   then open http://localhost:8000

The only outbound network call is decode_vin(), which hits the free NHTSA API
via `requests` (same endpoint the team's original main.py used). Everything else
- serving the page, filtering the catalog, building the VIN breakdown - is local.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


def _ensure_windows_ssl_dlls():
    """Make Python's SSL usable when launched outside an activated conda env.

    Anaconda/Miniconda ship the OpenSSL DLLs that `_ssl` needs under the env's
    Library dirs. If Python is started without `conda activate` (e.g. from Git
    Bash, PowerShell, or a bare `python main.py`), those dirs aren't on PATH and
    `import ssl` fails with "DLL load failed while importing _ssl", which surfaces
    as "the SSL module is not available" when `requests` makes an HTTPS call.

    Prepending the conda Library dirs to PATH (what `conda activate` does) fixes
    it. No-op on non-conda interpreters, where these dirs don't exist and SSL
    already works.
    """
    if sys.platform != "win32":
        return
    base = os.path.dirname(sys.executable)
    candidates = [
        base,
        os.path.join(base, "Library", "mingw-w64", "bin"),
        os.path.join(base, "Library", "usr", "bin"),
        os.path.join(base, "Library", "bin"),
        os.path.join(base, "Scripts"),
    ]
    existing = [d for d in candidates if os.path.isdir(d)]
    if not existing:
        return
    os.environ["PATH"] = os.pathsep.join(existing) + os.pathsep + os.environ.get("PATH", "")
    for d in existing:
        try:
            os.add_dll_directory(d)
        except (OSError, AttributeError):
            pass


_ensure_windows_ssl_dlls()

import vin_logic
import llm

try:
    import requests
except ImportError:  # pragma: no cover - requests is declared in pyproject
    requests = None

MAX_CHAT_BODY = 256 * 1024  # cap request body size for /api/chat

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


def fetch_vehicle_image(make, model):
    """Best-effort thumbnail URL for the vehicle from Wikipedia (no API key).

    Tries "{Make} {Model}" then "{Make}". Returns None on any failure so the UI
    simply hides the image. Uses `requests`; the proxy is picked up from the env.
    """
    if requests is None or not make:
        return None
    from urllib.parse import quote

    candidates = []
    if model:
        candidates.append("{} {}".format(make, model))
    candidates.append(make)
    headers = {"User-Agent": "VINPartsFinder/1.0 (hackathon demo)"}
    for title in candidates:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(title.replace(" ", "_"))
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code != 200:
                continue
            data = resp.json()
            thumb = (data.get("thumbnail") or {}).get("source")
            if thumb:
                return thumb
        except Exception:
            continue
    return None


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
    parts = vin_logic.with_pricing(parts)
    breakdown = vin_logic.vin_breakdown(vin, year_int)
    image = fetch_vehicle_image(make, model)

    return {
        "vehicle": {
            "make": make,
            "model": model,
            "modelYear": model_year,
            "bodyClass": body_class or "Unknown",
            "image": image,
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

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/chat":
            self._send(404, "Not found", "text/plain; charset=utf-8")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_CHAT_BODY:
            self._send_json({"error": "Invalid request size."}, status=400)
            return

        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json({"error": "Invalid JSON."}, status=400)
            return

        vehicle = body.get("vehicle") or {}
        messages = body.get("messages") or []
        try:
            reply = llm.chat(vehicle, messages)
            self._send_json({"reply": reply})
        except llm.NotConfigured as exc:
            self._send_json({"error": str(exc)}, status=200)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json(
                {
                    "error": "The AI assistant is temporarily unavailable. "
                             "Please try again.",
                    "detail": "{}: {}".format(type(exc).__name__, exc),
                },
                status=200,
            )


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
