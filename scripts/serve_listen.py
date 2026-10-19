"""Serve /listen/ locally the way brokenbranch.dev will, for driving the page in a browser.

    python scripts/serve_listen.py --site ../brokenbranchdevwebsite [--port 8765]

  /listen/*            site/listen/ from this repo
  /css /fonts /assets  from the site checkout (the page links /css/tokens.css first)
  /api/listen          a stand-in for the site's proxy; switch what it answers at runtime:
      /__mode?m=empty      {"empty": true, "reason": "not-configured"}   (the default)
      /__mode?m=fixture    the B1 fixture database's snapshot as of now (has a pending and a survivor)
      /__mode?m=stale      the same snapshot as of three hours ago
      /__mode?m=notstarted a valid snapshot of a run with no cadence scored (what the gist holds pre-run)
      /__mode?m=error      HTTP 502
The fixture snapshot is built with survey.snapshot exactly as the publisher builds it.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))

import make_fixture_db  # noqa: E402
from survey.snapshot import build_snapshot, load_sample_names, serialize  # noqa: E402

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("font/woff2", ".woff2")

STATE = {"mode": "empty"}


def fixture_snapshot(age: timedelta) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        db = make_fixture_db.make_fixture_db(str(Path(tmp) / "f.sqlite"))
        try:
            now = datetime.now(timezone.utc) - age
            sample = load_sample_names(ROOT / "tests" / "fixtures" / "gbt_sample_price2020.csv")
            return serialize(build_snapshot(db, now, sample_names=sample))
        finally:
            db.close()


def empty_run_snapshot() -> bytes:
    db = sqlite3.connect(":memory:")
    db.executescript(make_fixture_db.SCHEMA)
    sample = load_sample_names(ROOT / "tests" / "fixtures" / "gbt_sample_price2020.csv")
    return serialize(build_snapshot(db, datetime.now(timezone.utc) - timedelta(hours=4), sample_names=sample))


class Handler(BaseHTTPRequestHandler):
    site: Path = Path(".")

    def log_message(self, fmt, *args):  # quiet
        pass

    def send(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        path = url.path
        if path == "/__mode":
            STATE["mode"] = parse_qs(url.query).get("m", ["empty"])[0]
            return self.send(200, json.dumps(STATE).encode())
        if path == "/api/listen":
            m = STATE["mode"]
            if m == "fixture":
                return self.send(200, fixture_snapshot(timedelta(0)))
            if m == "notstarted":
                return self.send(200, empty_run_snapshot())
            if m == "stale":
                return self.send(200, fixture_snapshot(timedelta(hours=3)))
            if m == "error":
                return self.send(502, b'{"error":"bad gateway"}')
            return self.send(200, b'{"empty":true,"reason":"not-configured"}')
        if path in ("/listen", "/"):
            self.send_response(302)
            self.send_header("Location", "/listen/")
            self.end_headers()
            return
        if path.startswith("/listen/"):
            rel = path[len("/listen/"):] or "index.html"
            base = ROOT / "site" / "listen"
        elif path.startswith("/__og/"):  # the og.png template (scripts/make_og.mjs)
            rel = path[len("/__og/"):]
            base = ROOT / "scripts" / "og"
        else:
            rel = path.lstrip("/")
            base = self.site
        target = (base / rel).resolve()
        if target.is_dir():
            target = target / "index.html"
        if not str(target).startswith(str(base.resolve())) or not target.is_file():
            return self.send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return self.send(200, target.read_bytes(), ctype)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Serve /listen/ locally")
    ap.add_argument("--site", required=True, help="path to a brokenbranchdevwebsite checkout")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    Handler.site = Path(a.site).resolve()
    print(f"http://127.0.0.1:{a.port}/listen/  (api mode: {STATE['mode']}; switch with /__mode?m=fixture)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
