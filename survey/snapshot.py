"""The public snapshot of the run: what brokenbranch.dev/listen/ may show (spec §9).

build_snapshot() reads the run's SQLite state (Plan A Task 7 schema) read-only and
returns schema 1. Redaction is a whitelist: every section copies named columns
from named rows, so a column that isn't listed here can't reach the public.

Who is public, and when (spec §9 "What the public sees mid-run"):

- A star is *settled* when every cadence it has is finished (scored / parked /
  incomplete) and it holds no PENDING_R5 or SURVIVOR signal. A settled star's
  signals count live and its eliminations are listed.
- Every other signal (its star still has a cadence to run, or something pending
  or under review) counts only from the 00:00 UTC batch: it is counted iff it
  was created before the latest 00:00 UTC boundary at or before `now`. Its row
  is never listed.

So the pending count, and anything about a star with a pending signal, moves
once per UTC day and never mid-day. That holds as long as the runner registers
every cadence as queued before it scores any (Plan A's runner takes the whole
cadence list up front); a cadence added to an already-settled star would make
that star's same-day rows step back out of the counts.

Planted signals (planted=1, set at unblinding) are test signals, not sky: they
are left out everywhere.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA_VERSION = 1
MAX_BYTES = 256 * 1024
RECENT_MAX = 200
SPEED_POINTS = 60
DEFAULT_SAMPLE = Path(__file__).resolve().parent.parent / "data" / "gbt_sample_price2020.csv"

FINISHED = ("scored", "parked", "incomplete")
HELD_VERDICTS = ("PENDING_R5", "SURVIVOR")
# verdict -> funnel bucket; ELIMINATED is split by rung.
BUCKETS = {
    "UNTESTED": "untested",
    "NOT-RECOVERED": "not_recovered",
    "INCOMPLETE": "incomplete",
    "PENDING_R5": "pending_final_check",
    "SURVIVOR": "under_review",
    "CANDIDATE": "public_candidates",  # released after private review (Plan C adds the verdict)
}

# The only columns a listed elimination may carry.
RECENT_COLUMNS = ("id", "star", "band", "shape", "peak_freq_mhz", "drift_rate_hz_s", "rung", "reason",
                  "weirdness", "figure", "decided_utc")


class SnapshotTooLarge(ValueError):
    """The snapshot is over MAX_BYTES even with an empty recent_eliminated list."""


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s: str | None) -> datetime | None:
    if not s:
        return None
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _round(x, nd):
    return None if x is None else round(float(x), nd)


def load_sample_names(path=DEFAULT_SAMPLE) -> list[str]:
    """Star names in sample order, from the provenance-headed sample CSV."""
    with open(path, encoding="utf-8") as fh:
        rows = csv.DictReader(line for line in fh if not line.startswith("#"))
        return [r["star"] for r in rows]


def batch_boundary(now_utc: datetime) -> datetime:
    """The latest 00:00 UTC at or before now."""
    now_utc = now_utc.astimezone(timezone.utc)
    return now_utc.replace(hour=0, minute=0, second=0, microsecond=0)


def _settled_stars(db: sqlite3.Connection) -> tuple[set[str], set[str]]:
    """(stars with every cadence finished, stars that are also free of held signals)."""
    finished = set()
    marks = ",".join("?" * len(FINISHED))
    for star, n_all, n_done in db.execute(
            f"SELECT star, COUNT(*), SUM(status IN ({marks})) FROM cadences GROUP BY star", FINISHED):
        if n_all and n_done == n_all:
            finished.add(star)
    held = {r[0] for r in db.execute(
        f"SELECT DISTINCT star FROM signals WHERE COALESCE(planted,0)=0 AND verdict IN ({','.join('?' * len(HELD_VERDICTS))})",
        HELD_VERDICTS)}
    return finished, finished - held


def _counted(row_star, created, settled, boundary) -> bool:
    if row_star in settled:
        return True
    t = _parse(created)
    return t is not None and t < boundary


def _funnel(db, settled, boundary) -> dict:
    f = {"flagged": 0, "eliminated_by_rung": {str(r): 0 for r in range(1, 6)},
         "untested": 0, "not_recovered": 0, "incomplete": 0, "pending_final_check": 0,
         "under_review": 0, "public_candidates": 0}
    for sid, star, verdict, rung, created in db.execute(
            "SELECT id, star, verdict, rung, created_utc FROM signals WHERE COALESCE(planted,0)=0"):
        if not _counted(star, created, settled, boundary):
            continue
        if verdict == "ELIMINATED":
            if rung not in (1, 2, 3, 4, 5):
                raise ValueError(f"signal {sid}: ELIMINATED without a rung 1-5 ({rung!r})")
            f["eliminated_by_rung"][str(rung)] += 1
        elif verdict in BUCKETS:
            f[BUCKETS[verdict]] += 1
        else:
            raise ValueError(f"signal {sid}: unknown verdict {verdict!r}")
        f["flagged"] += 1
    return f


def _recent(db, settled) -> list[dict]:
    if not settled:
        return []
    marks = ",".join("?" * len(settled))
    rows = db.execute(
        "SELECT id, star, band, shape, peak_freq_mhz, drift_rate_hz_s, rung, reason, weirdness, figure, decided_utc "
        f"FROM signals WHERE COALESCE(planted,0)=0 AND verdict='ELIMINATED' AND star IN ({marks}) "
        "ORDER BY decided_utc DESC, id DESC LIMIT ?", (*sorted(settled), RECENT_MAX)).fetchall()
    out = []
    for r in rows:
        d = dict(zip(RECENT_COLUMNS, r))
        d["peak_freq_mhz"] = _round(d["peak_freq_mhz"], 6)
        d["drift_rate_hz_s"] = _round(d["drift_rate_hz_s"], 3)
        d["weirdness"] = _round(d["weirdness"], 3)
        d["rung"] = int(d["rung"])
        # The local path stays local; the public figure is served beside the page.
        d["figure"] = f"figures/{d['id']}.webp" if d["figure"] else None
        out.append(d)
    return out


def _progress(db, finished, sample) -> dict:
    status = dict(db.execute("SELECT status, COUNT(*) FROM cadences GROUP BY status").fetchall())
    hb = db.execute("SELECT bytes_total FROM heartbeat WHERE id=1").fetchone()
    nbytes = hb[0] if hb and hb[0] is not None else (
        db.execute("SELECT COALESCE(SUM(bytes),0) FROM cadences WHERE status='scored'").fetchone()[0])
    bits = 0
    for i, name in enumerate(sample):
        if name in finished:
            bits |= 1 << i
    return {
        "stars_total": len(sample),
        "stars_done": len(finished),
        "cadences_total": sum(status.values()),
        "cadences_done": status.get("scored", 0),
        "cadences_parked": status.get("parked", 0),
        "cadences_incomplete": status.get("incomplete", 0),
        "bytes_streamed": int(nbytes or 0),
        # bit i set = star i of the sample (CSV order) has every cadence finished
        "searched": format(bits, "x"),
    }


def _heartbeat(db) -> dict | None:
    r = db.execute("SELECT star, scan_idx, speed_mb_s, updated_utc FROM heartbeat WHERE id=1").fetchone()
    if r is None:
        return None
    return {"star": r[0], "scan_idx": r[1], "speed_mb_s": _round(r[2], 3), "updated_utc": r[3]}


def build_snapshot(db: sqlite3.Connection, now_utc: datetime, *, sample_names: list[str] | None = None,
                   sample_path=DEFAULT_SAMPLE) -> dict:
    """Schema-1 public snapshot of the run as of `now_utc` (tz-aware; the clock is never read)."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    sample = sample_names if sample_names is not None else load_sample_names(sample_path)
    boundary = batch_boundary(now_utc)
    finished, settled = _settled_stars(db)
    scored = db.execute("SELECT COUNT(*) FROM cadences WHERE status='scored'").fetchone()[0]
    speeds = [r[0] for r in db.execute(
        "SELECT mb_s FROM (SELECT rowid, mb_s FROM speed_log ORDER BY utc DESC, rowid DESC LIMIT ?) "
        "ORDER BY rowid ASC", (SPEED_POINTS,))]
    return {
        "schema": SCHEMA_VERSION,
        "as_of_utc": _iso(now_utc),
        "mode": "MEASURED" if scored else "DEMO",
        "progress": _progress(db, finished, sample),
        "funnel": _funnel(db, settled, boundary),
        "pending_batch_utc": _iso(boundary),
        "recent_eliminated": _recent(db, settled),
        "heartbeat": _heartbeat(db),
        "speed_series": [_round(v, 3) for v in speeds],
    }


def _dump(snap: dict) -> bytes:
    return json.dumps(snap, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def serialize(snap: dict) -> bytes:
    """Compact JSON, at most MAX_BYTES. Drops the oldest listed eliminations to fit; raises if it can't."""
    raw = _dump(snap)
    if len(raw) <= MAX_BYTES:
        return raw
    items = snap.get("recent_eliminated") or []
    lo, hi, best = 0, len(items), None
    while lo <= hi:  # largest prefix (newest first) that fits
        mid = (lo + hi) // 2
        candidate = _dump({**snap, "recent_eliminated": items[:mid]})
        if len(candidate) <= MAX_BYTES:
            best, lo = candidate, mid + 1
        else:
            hi = mid - 1
    if best is None:
        raise SnapshotTooLarge(f"snapshot is {len(raw)} bytes with no listed eliminations; cap {MAX_BYTES}")
    return best
