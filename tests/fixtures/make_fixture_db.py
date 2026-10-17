"""Fixture SQLite database with Plan A Task 7's schema, for Plan B's tests.

The schema below is copied verbatim from Plan A Task 7
(docs/superpowers/plans/2026-10-17-plan-a-survey-pipeline.md). Plan B reads
that database read-only; if Plan A renames a column, this file and the
Plan B modules must change with it.

Seeded story (now = 2026-10-17T11:55Z, so the pending batch is 2026-10-17T00:00Z):

- STAR_PUBLIC (GJ411): two scored cadences; one signal eliminated at each
  rung 1-5, plus one UNTESTED, one NOT-RECOVERED and one INCOMPLETE.
- STAR_PENDING (HIP4436): one scored cadence; one signal eliminated at rung 2
  and one PENDING_R5. Its whole Ledger list must stay hidden.
- STAR_SURVIVOR (HIP17147): one scored cadence; one signal eliminated at
  rung 4 and one SURVIVOR. Only the under-review count may show it.
- STAR_EMPTY (GJ1111): one parked cadence and one incomplete cadence, no signals.
- STAR_LIVE (GJ1245AC): one queued cadence; the heartbeat is on it.

Run as a script to write a fixture database to a path:
    python tests/fixtures/make_fixture_db.py out.sqlite
"""
from __future__ import annotations

import json
import sqlite3
import sys

SCHEMA = """
CREATE TABLE cadences(id TEXT PRIMARY KEY, star TEXT, band TEXT, status TEXT, attempts INT,
                      reason TEXT, bytes INT, started_utc TEXT, finished_utc TEXT);
CREATE TABLE signals(id TEXT PRIMARY KEY, cadence_id TEXT, star TEXT, band TEXT, shape TEXT,
                     peak_freq_mhz REAL, drift_rate_hz_s REAL, snr REAL, weirdness REAL,
                     verdict TEXT, rung INT, reason TEXT, figure TEXT, scans_json TEXT,
                     planted INT DEFAULT 0, created_utc TEXT, decided_utc TEXT);
CREATE TABLE heartbeat(id INT PRIMARY KEY CHECK (id=1), star TEXT, cadence_id TEXT, scan_idx INT,
                       bytes_total INT, speed_mb_s REAL, updated_utc TEXT);
CREATE TABLE speed_log(utc TEXT, mb_s REAL);
CREATE TABLE events(utc TEXT, kind TEXT, detail TEXT);
"""

STAR_PUBLIC = "GJ411"
STAR_PENDING = "HIP4436"
STAR_SURVIVOR = "HIP17147"
STAR_EMPTY = "GJ1111"
STAR_LIVE = "GJ1245AC"
SAMPLE = [STAR_PUBLIC, STAR_PENDING, STAR_SURVIVOR, STAR_EMPTY, STAR_LIVE]

PENDING_ID = "HIP4436_S_57803.9344_weird_t0412"
PENDING_FREQ = 2017.418273
SURVIVOR_ID = "HIP17147_L_57523.8029_chirp_t0088"
SURVIVOR_FREQ = 1388.264519

# A local figure path, as the runner writes it. It must never reach the public.
LOCAL_FIG = r"E:\seti_staging\results\figures\{}.webp"

REASONS = {
    1: "present in OFF 2 (SNR 14.1)",
    2: "in 1/3 ON",
    3: "on a coarse-channel centre (DC spike)",
    4: "inside iridium 1616.0-1626.5 MHz",
    5: "also seen at HIP65721 on MJD 57611",
}


def scans(on_present=(True, True, True), off_present=(False, False, False)) -> str:
    rows = []
    for i in range(3):
        rows.append({"role": "ON", "snr": 18.0 if on_present[i] else 2.1, "present": on_present[i]})
        rows.append({"role": "OFF", "snr": 15.0 if off_present[i] else 1.4, "present": off_present[i]})
    return json.dumps(rows)


def add_signal(db, sid, cadence_id, star, band, shape, f, drift, verdict, rung=None, reason="",
               weirdness=0.5, created="2026-10-16T20:00:00Z", decided="2026-10-16T20:00:00Z",
               planted=0, figure=True):
    db.execute(
        "INSERT OR REPLACE INTO signals(id,cadence_id,star,band,shape,peak_freq_mhz,drift_rate_hz_s,snr,"
        "weirdness,verdict,rung,reason,figure,scans_json,planted,created_utc,decided_utc) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sid, cadence_id, star, band, shape, f, drift, 17.5, weirdness, verdict, rung, reason,
         LOCAL_FIG.format(sid) if figure else None, scans(), planted, created, decided),
    )


def add_cadence(db, cid, star, band, status, reason=None, nbytes=1_450_000_000,
                started="2026-10-16T19:00:00Z", finished="2026-10-16T19:40:00Z"):
    db.execute("INSERT OR REPLACE INTO cadences VALUES (?,?,?,?,?,?,?,?,?)",
               (cid, star, band, status, 1, reason, nbytes, started, finished))


def make_fixture_db(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)

    add_cadence(db, "GJ411_L_57542.9764", STAR_PUBLIC, "L", "scored")
    add_cadence(db, "GJ411_S_57543.0102", STAR_PUBLIC, "S", "scored")
    add_cadence(db, "HIP4436_S_57803.9344", STAR_PENDING, "S", "scored")
    add_cadence(db, "HIP17147_L_57523.8029", STAR_SURVIVOR, "L", "scored")
    add_cadence(db, "GJ1111_L_57635.5511", STAR_EMPTY, "L", "parked", reason="size mismatch", nbytes=0)
    add_cadence(db, "GJ1111_S_57635.5803", STAR_EMPTY, "S", "incomplete", reason="5 of 6 scans", nbytes=0)
    add_cadence(db, "GJ1245AC_L_57587.1893", STAR_LIVE, "L", "queued", nbytes=0, started=None, finished=None)

    shapes = ["wide_drift", "chirp", "intermittent", "comb", "weird"]
    freqs = [1617.881204, 1420.402113, 2244.010442, 1542.775180, 2193.565812]
    for rung in range(1, 6):
        add_signal(db, f"GJ411_L_57542.9764_{shapes[rung - 1]}_t{rung:04d}", "GJ411_L_57542.9764",
                   STAR_PUBLIC, "L" if freqs[rung - 1] < 1800 else "S", shapes[rung - 1], freqs[rung - 1],
                   -12.5 * rung, "ELIMINATED", rung, REASONS[rung], weirdness=0.1 * rung,
                   decided=f"2026-10-16T20:0{rung}:00Z")
    add_signal(db, "GJ411_S_57543.0102_weird_t0101", "GJ411_S_57543.0102", STAR_PUBLIC, "S", "weird",
               2405.112233, 0.0, "UNTESTED", reason="no OFF scans")
    add_signal(db, "GJ411_S_57543.0102_comb_t0102", "GJ411_S_57543.0102", STAR_PUBLIC, "S", "comb",
               2501.000111, 3.0, "NOT-RECOVERED", reason="not re-found on recheck")
    add_signal(db, "GJ411_S_57543.0102_chirp_t0103", "GJ411_S_57543.0102", STAR_PUBLIC, "S", "chirp",
               2602.987654, 41.0, "INCOMPLETE", reason="track leaves the band")

    add_signal(db, "HIP4436_S_57803.9344_wide_drift_t0007", "HIP4436_S_57803.9344", STAR_PENDING, "S",
               "wide_drift", 2311.555123, 8.0, "ELIMINATED", 2, REASONS[2],
               created="2026-10-16T21:00:00Z", decided="2026-10-16T21:00:00Z")
    add_signal(db, PENDING_ID, "HIP4436_S_57803.9344", STAR_PENDING, "S", "weird", PENDING_FREQ, 22.5,
               "PENDING_R5", reason="passed rungs 1-4", weirdness=0.97,
               created="2026-10-16T21:00:00Z", decided="2026-10-16T21:00:00Z")

    add_signal(db, "HIP17147_L_57523.8029_comb_t0050", "HIP17147_L_57523.8029", STAR_SURVIVOR, "L",
               "comb", 1620.010101, -4.0, "ELIMINATED", 4, REASONS[4],
               created="2026-10-16T22:00:00Z", decided="2026-10-16T22:00:00Z")
    add_signal(db, SURVIVOR_ID, "HIP17147_L_57523.8029", STAR_SURVIVOR, "L", "chirp", SURVIVOR_FREQ, 61.0,
               "SURVIVOR", reason="passed all five rungs", weirdness=0.99,
               created="2026-10-16T22:00:00Z", decided="2026-10-16T22:00:00Z")

    db.execute("INSERT INTO heartbeat VALUES (1,?,?,?,?,?,?)",
               (STAR_LIVE, "GJ1245AC_L_57587.1893", 3, 5_812_000_000, 1.31, "2026-10-17T11:50:00Z"))
    for i in range(70):
        db.execute("INSERT INTO speed_log VALUES (?,?)",
                   (f"2026-10-17T{i // 6:02d}:{(i % 6) * 10:02d}:00Z", round(1.2 + 0.002 * i, 3)))
    db.commit()
    return db


if __name__ == "__main__":
    make_fixture_db(sys.argv[1]).close()
    print("wrote", sys.argv[1])
