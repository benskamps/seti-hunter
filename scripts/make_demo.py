"""Build the /listen/ page's demo from the six-target pilot (Plan A's pilot regression).

Before the survey's first real publish the page shows this, behind a DEMO badge
that says plainly what it is: the six-target pilot scored on a ladder that is
not frozen yet, not survey results. Every number in it comes from data:

  verdicts, rungs, reasons,   data/pilot_expected.json (Plan A, written by
  per-scan SNRs, survivors    scripts/pilot_regression.py export). The only source
                              of truth; re-run this script whenever it changes.
  weirdness                   read-only from the regression database, by signal id
                              (only the weird channel carries one)
  cutouts                     the figures the pilot run rendered from the cached raw
                              files (read, never moved)
  bytes streamed              the cached raw files' real sizes
  download speeds             representative, inside the measured 1.2-1.4 MB/s range
                              (spec §3); the page's heartbeat badge says so

It runs the same code the live run uses: the pilot is loaded into a SQLite file
with Plan A Task 7's schema, then survey.snapshot and survey.figures_export write

    site/listen/demo-snapshot.json
    site/listen/demo/figures.json, demo/figures/*.webp, demo/ledger/*.json

The redaction is the live run's: a SURVIVOR shows only as the under-review count
(never its star, frequency, date, row or figure), and no image is published near it.

    python scripts/make_demo.py --pilot ../seti-hunter-plan-a/data/pilot_expected.json
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))

from make_fixture_db import SCHEMA  # noqa: E402  (the one copy of Plan A Task 7's schema)
from survey.figures_export import export  # noqa: E402
from survey.snapshot import build_snapshot, load_sample_names, serialize  # noqa: E402
from targets_catalog import STAGE1_CADENCES  # noqa: E402

DEFAULT_PILOT = ROOT / "data" / "pilot_expected.json"
DEFAULT_FIGURES = Path(r"E:\seti_staging\regression\figures")
DEFAULT_CACHE = Path(r"E:\seti_staging\regression\cache")
DEFAULT_WEIRD_DB = Path(r"E:\seti_staging\state\regression.sqlite")
DEMO_MAX_FIGURES = 120  # the Wall pages 36 at a time; the live run's cap is 400

SHORT = {
    "tabbys_star_sband": "Tabby's Star",
    "oumuamua_interstellar": "'Oumuamua",
    "trappist1_exoplanets": "TRAPPIST-1",
    "galactic_center_sgrb2": "Sgr B2",
    "nearby_exoplanet_hosts": "Epsilon Eridani",
    "kepler_transit_pair": "Kepler-992b",
}


def target_key(cadence: str) -> str:
    """'pilot-tabbys_star_sband-AGBT17A_999_68' -> 'tabbys_star_sband'."""
    for key in SHORT:
        if cadence.startswith(f"pilot-{key}-"):
            return key
    raise ValueError(f"unknown pilot cadence {cadence!r}")


def as_of_for(pilot: Path) -> datetime:
    """The pilot file's commit time (its own repo), else its modification time."""
    try:
        out = subprocess.run(["git", "-C", str(pilot.parent), "log", "-1", "--format=%cI", "--", pilot.name],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        if out:
            return datetime.fromisoformat(out).astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        pass
    return datetime.fromtimestamp(pilot.stat().st_mtime, timezone.utc)


def weirdness_by_id(path: Path) -> dict:
    if not path.is_file():
        return {}
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {sid: w for sid, w in db.execute("SELECT id, weirdness FROM signals WHERE weirdness IS NOT NULL")}
    finally:
        db.close()


def load_pilot(db: sqlite3.Connection, pilot: dict, stamp: str, figures: Path, cache: Path, weird: dict) -> dict:
    cadences = sorted({s["cadence"] for s in pilot["signals"]})
    catalog = {e["cadence_id"]: e for e in STAGE1_CADENCES}
    total_bytes = 0
    for cad in cadences:
        key = target_key(cad)
        files = [cache / s["url"].split("/")[-1] for s in catalog[key]["scans"]]
        nbytes = sum(p.stat().st_size for p in files if p.is_file())
        total_bytes += nbytes
        db.execute("INSERT INTO cadences VALUES (?,?,?,?,?,?,?,?,?)",
                   (cad, SHORT[key], "L" if key == "kepler_transit_pair" else "S", "scored", 1, None, nbytes,
                    stamp, stamp))
    counts = {}
    for s in pilot["signals"]:
        key = target_key(s["cadence"])
        scans = [{"role": r["role"], "snr": r.get("snr"), "present": r.get("present")} for r in s["scans_json"]]
        on_snr = [r["snr"] for r in scans if r["role"] == "ON" and isinstance(r["snr"], (int, float))]
        fig = figures / f"{s['id']}.webp"
        db.execute(
            "INSERT INTO signals(id,cadence_id,star,band,shape,peak_freq_mhz,drift_rate_hz_s,snr,weirdness,verdict,"
            "rung,reason,figure,scans_json,planted,created_utc,decided_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
            (s["id"], s["cadence"], SHORT[key], "L" if key == "kepler_transit_pair" else "S", s["shape"],
             s["peak_freq_mhz"], s["drift"], max(on_snr) if on_snr else None, weird.get(s["id"]), s["verdict"],
             s["rung"], s["reason"], str(fig) if fig.is_file() else None, json.dumps(scans), stamp, stamp))
        counts[s["verdict"]] = counts.get(s["verdict"], 0) + 1
    last = max(cadences)
    db.execute("INSERT INTO heartbeat VALUES (1,?,?,?,?,?,?)",
               (SHORT[target_key(last)], last, len(catalog[target_key(last)]["scans"]) - 1, total_bytes, 1.31, stamp))
    rng = random.Random(20261016)  # representative speeds inside the measured 1.2-1.4 MB/s range
    v = 1.3
    for i in range(60):
        v = min(1.4, max(1.2, v + rng.uniform(-0.035, 0.035)))
        db.execute("INSERT INTO speed_log VALUES (?,?)", (f"{stamp[:11]}00:{i:02d}:00Z", round(v, 3)))
    db.commit()
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the /listen/ demo from the six-target pilot")
    ap.add_argument("--pilot", default=str(DEFAULT_PILOT))
    ap.add_argument("--figures", default=str(DEFAULT_FIGURES))
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--weird-db", default=str(DEFAULT_WEIRD_DB))
    ap.add_argument("--out", default=str(ROOT / "site" / "listen"))
    ap.add_argument("--csv", default=str(ROOT / "tests" / "fixtures" / "gbt_sample_price2020.csv"))
    ap.add_argument("--max-figures", type=int, default=DEMO_MAX_FIGURES)
    a = ap.parse_args(argv)
    pilot_path = Path(a.pilot)
    pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
    if len(pilot["signals"]) != pilot.get("n_signals", len(pilot["signals"])):
        raise SystemExit(f"{pilot_path}: n_signals says {pilot['n_signals']}, the file holds {len(pilot['signals'])}")
    now = as_of_for(pilot_path)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    counts = load_pilot(db, pilot, stamp, Path(a.figures), Path(a.cache), weirdness_by_id(Path(a.weird_db)))
    snap = build_snapshot(db, now, sample_names=load_sample_names(a.csv))
    snap["mode"] = "DEMO"
    out = Path(a.out)
    (out / "demo-snapshot.json").write_bytes(serialize(snap) + b"\n")
    figs = export(db, out_dir=str(out / "demo" / "figures"), now_utc=now, src_dir=Path(a.figures),
                  max_figures=a.max_figures)
    print(json.dumps({"as_of": stamp, "verdicts": counts, "funnel": snap["funnel"], "figures": figs}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
