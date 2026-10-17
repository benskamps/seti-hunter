"""Publish the public snapshot to the run's public gist (spec §9, Plan B Task B3).

The runner calls maybe_publish() after each cadence. It publishes at most once
per `min_interval_s` (the last successful publish time lives in the `events`
table), and it never raises: any failure is written to `events` as
`publish_failed` and the survey keeps running. The gist id is read from
E:\\seti_staging\\state\\gist_id.txt; creating the gist is Ben's call (Task B7).

    python -m survey.publish            # publish now if the interval allows
    python -m survey.publish --force    # publish now regardless
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from survey.snapshot import build_snapshot, serialize

GIST_ID_FILE = Path(r"E:\seti_staging\state\gist_id.txt")
DEFAULT_DB = Path(r"E:\seti_staging\state\survey.sqlite")
GH_TIMEOUT_S = 120
GIST_ID = re.compile(r"^[0-9a-f]{20,40}$")


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(db: sqlite3.Connection, now_utc: datetime, kind: str, detail: str) -> None:
    db.execute("INSERT INTO events(utc, kind, detail) VALUES (?,?,?)", (_iso(now_utc), kind, detail[:500]))
    db.commit()


def read_gist_id(path=GIST_ID_FILE) -> str | None:
    """The gist id, or None if the gist hasn't been created yet. Rejects anything that isn't a gist id."""
    p = Path(path)
    if not p.is_file():
        return None
    gid = p.read_text(encoding="utf-8").strip()
    if not GIST_ID.match(gid):
        raise ValueError(f"{p} does not hold a gist id")
    return gid


def _last_publish(db: sqlite3.Connection) -> datetime | None:
    row = db.execute("SELECT MAX(utc) FROM events WHERE kind='publish'").fetchone()
    if not row or not row[0]:
        return None
    return datetime.fromisoformat(row[0].replace("Z", "+00:00"))


def maybe_publish(db: sqlite3.Connection, gist_id: str, now_utc: datetime, min_interval_s: int = 900,
                  runner=subprocess.run, **snapshot_kw) -> bool:
    """Publish the snapshot if `min_interval_s` has passed since the last publish. True iff published."""
    last = _last_publish(db)
    if last is not None:
        elapsed = (now_utc - last).total_seconds()
        if 0 <= elapsed < min_interval_s:  # a last-publish in the future (clock jump) doesn't block forever
            return False
    try:
        payload = serialize(build_snapshot(db, now_utc, **snapshot_kw))
    except Exception as exc:  # the survey must keep running whatever the snapshot does
        _log(db, now_utc, "publish_failed", f"snapshot: {type(exc).__name__}: {exc}")
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="listen-") as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_bytes(payload)
            proc = runner(["gh", "gist", "edit", gist_id, "-f", "snapshot.json", str(path)],
                          capture_output=True, text=True, timeout=GH_TIMEOUT_S)
    except Exception as exc:
        _log(db, now_utc, "publish_failed", f"gh: {type(exc).__name__}: {exc}")
        return False
    if proc.returncode != 0:
        _log(db, now_utc, "publish_failed", f"gh exit {proc.returncode}: {(proc.stderr or '').strip()}")
        return False
    _log(db, now_utc, "publish", f"{len(payload)} bytes")
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Publish the public snapshot to the gist.")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--force", action="store_true", help="ignore the 15-minute interval")
    a = ap.parse_args(argv)
    gid = read_gist_id()
    if gid is None:
        print(f"no gist yet ({GIST_ID_FILE} missing); B7 creates it with Ben's OK")
        return 1
    db = sqlite3.connect(a.db)
    try:
        ok = maybe_publish(db, gid, datetime.now(timezone.utc), min_interval_s=0 if a.force else 900)
    finally:
        db.close()
    print("published" if ok else "not published (interval, or see events: publish_failed)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
