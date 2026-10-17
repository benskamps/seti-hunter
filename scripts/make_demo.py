"""Build the /listen/ page's demo data from the real six-target pilot (2026-10-16).

Before the survey's first publish, the page shows this instead of the live
snapshot, behind a DEMO badge that names the difference in numbers. Every
signal in it is real: the pilot's 24 flagged signals with their real figures,
verdicts and six-scan SNRs, mapped onto the frozen ladder's vocabulary
(ONE-OFF -> eliminated at rung 2, RFI -> eliminated at rung 1). Only the
heartbeat's download speeds are representative, drawn from the measured
1.2-1.4 MB/s range (spec §3); the page says so on the panel.

It runs the same code the live run uses: the pilot is loaded into a SQLite file
with Plan A Task 7's schema (the copy in tests/fixtures/make_fixture_db.py),
then survey.snapshot and survey.figures_export write

    site/listen/demo-snapshot.json
    site/listen/demo/figures.json + site/listen/demo/figures/*.webp

    python scripts/make_demo.py [--report survey_report.json]
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))

from make_fixture_db import SCHEMA  # noqa: E402  (the one copy of Plan A Task 7's schema)
from survey.figures_export import export  # noqa: E402
from survey.snapshot import build_snapshot, load_sample_names, serialize  # noqa: E402

SHORT = {
    "tabbys_star_sband": "Tabby's Star",
    "oumuamua_interstellar": "'Oumuamua",
    "trappist1_exoplanets": "TRAPPIST-1",
    "galactic_center_sgrb2": "Sgr B2",
    "nearby_exoplanet_hosts": "Epsilon Eridani",
    "kepler_transit_pair": "Kepler-992b",
}
VERDICT = {"ONE-OFF": ("ELIMINATED", 2), "RFI": ("ELIMINATED", 1),
           "UNTESTED": ("UNTESTED", None), "NOT-RECOVERED": ("NOT-RECOVERED", None)}


def reason(verdict: str, detail: str) -> str:
    if verdict == "ONE-OFF":
        return f"missing from an ON scan: {detail}"
    if verdict == "RFI":
        return f"present in an OFF scan: {detail}"
    if verdict == "UNTESTED":
        return f"untested: {detail}"
    return f"not re-found on re-check: {detail}"


def load_pilot(db: sqlite3.Connection, report: dict) -> int:
    stamp = report["generated_at"]
    n = 0
    for c in report["cadences"]:
        star = SHORT.get(c["cadence_id"], c["target_name"])
        db.execute("INSERT INTO cadences VALUES (?,?,?,?,?,?,?,?,?)",
                   (c["cadence_id"], star, "S" if c["candidates"][0]["peak_freq_mhz"] > 1800 else "L", "scored", 1,
                    None, int(c["raw_bytes_processed_mb"] * 1e6), stamp, stamp))
        for k in c["candidates"]:
            verdict, rung = VERDICT[k["cadence_verdict"]]
            sid = f"{c['cadence_id']}_weird_t{k['tile_idx']:04d}"
            scans = [{"role": s["role"], "snr": s["snr"], "present": s["present"]} for s in k["cadence_scans"]]
            db.execute(
                "INSERT INTO signals(id,cadence_id,star,band,shape,peak_freq_mhz,drift_rate_hz_s,snr,weirdness,verdict,"
                "rung,reason,figure,scans_json,planted,created_utc,decided_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
                (sid, c["cadence_id"], star, "S" if k["peak_freq_mhz"] > 1800 else "L", "weird", k["peak_freq_mhz"],
                 k["drift_rate_hz_s"], k["drift_snr"], k["total_weirdness_score"], verdict, rung,
                 reason(k["cadence_verdict"], k["cadence_detail"]), k.get("plot_path"), json.dumps(scans), stamp, stamp))
            n += 1
    last = report["cadences"][-1]
    db.execute("INSERT INTO heartbeat VALUES (1,?,?,?,?,?,?)",
               (SHORT.get(last["cadence_id"]), last["cadence_id"], 5,
                int(sum(c["raw_bytes_processed_mb"] for c in report["cadences"]) * 1e6), 1.31, stamp))
    rng = random.Random(20261016)  # representative speeds inside the measured 1.2-1.4 MB/s range
    v = 1.3
    for i in range(60):
        v = min(1.4, max(1.2, v + rng.uniform(-0.035, 0.035)))
        db.execute("INSERT INTO speed_log VALUES (?,?)", (f"2026-10-17T02:{i:02d}:00Z", round(v, 3)))
    db.commit()
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the /listen/ demo data from the pilot")
    ap.add_argument("--report", default=str(ROOT / "survey_report.json"))
    ap.add_argument("--out", default=str(ROOT / "site" / "listen"))
    ap.add_argument("--csv", default=str(ROOT / "tests" / "fixtures" / "gbt_sample_price2020.csv"))
    a = ap.parse_args(argv)
    report = json.loads(Path(a.report).read_text(encoding="utf-8"))
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    n = load_pilot(db, report)
    now = datetime.fromisoformat(report["generated_at"].replace("Z", "+00:00"))
    snap = build_snapshot(db, now, sample_names=load_sample_names(a.csv))
    snap["mode"] = "DEMO"
    out = Path(a.out)
    (out / "demo-snapshot.json").write_bytes(serialize(snap) + b"\n")
    counts = export(db, out_dir=str(out / "demo" / "figures"), now_utc=now)
    print(f"pilot signals {n}; funnel {snap['funnel']}; figures {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
