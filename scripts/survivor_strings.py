"""The strings that must never appear in anything published about the survey: survivors' ids and frequencies.

They are read at run time from the private pilot file (Plan A's pilot_expected.json),
never written into this public repo. Used by tests/test_no_survivor_strings.py and,
through `python scripts/survivor_strings.py <pilot>`, by scripts/drive_listen.mjs.

    python scripts/survivor_strings.py [--pilot PATH]   # prints one forbidden string per line
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FREQ_TOL_MHZ = 0.006  # rung 5's tolerance, as pilot_regression.py matches pinned survivors


def pilot_path(explicit: str | None = None) -> Path | None:
    """LISTEN_PILOT (or an explicit path), else data/pilot_expected.json, else Plan A's worktree copy."""
    for cand in (explicit, os.environ.get("LISTEN_PILOT"), ROOT / "data" / "pilot_expected.json",
                 ROOT.parent / "seti-hunter-plan-a" / "data" / "pilot_expected.json"):
        if cand and Path(cand).is_file():
            return Path(cand)
    return None


def _freq_forms(f: float) -> set[str]:
    """2- and 3-decimal renderings, rounded down and up, as a page or a figure might print them."""
    out = set()
    for nd in (2, 3):
        k = 10 ** nd
        for v in (math.floor(f * k) / k, math.ceil(f * k) / k, round(f, nd)):
            out.add(f"{v:.{nd}f}")
    return out


def forbidden_strings(path: Path) -> set[str]:
    pilot = json.loads(Path(path).read_text(encoding="utf-8"))
    signals = pilot.get("signals", [])
    survivors = [s for s in signals if s.get("verdict") == "SURVIVOR"]
    for p in pilot.get("pinned_survivors", []):
        match = [s for s in signals if s.get("cadence") == p.get("cadence") and s.get("shape") == p.get("shape")
                 and abs(float(s.get("peak_freq_mhz", 0)) - float(p["peak_freq_mhz"])) <= FREQ_TOL_MHZ]
        survivors.extend(match or [{"id": None, "cadence": p.get("cadence"), "shape": p.get("shape"),
                                    "peak_freq_mhz": p["peak_freq_mhz"]}])
    out: set[str] = set()
    for s in survivors:
        if s.get("id"):
            out.add(s["id"])
            out.add(s["id"].split("-", 1)[1] if s["id"].startswith("pilot-") else s["id"])
        out |= _freq_forms(float(s["peak_freq_mhz"]))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Print the survivors' forbidden strings, one per line")
    ap.add_argument("--pilot")
    a = ap.parse_args(argv)
    path = pilot_path(a.pilot)
    if path is None:
        print("no pilot_expected.json: set LISTEN_PILOT", file=sys.stderr)
        return 2
    strings = forbidden_strings(path)
    if not strings:
        print(f"{path} names no survivor", file=sys.stderr)
        return 3
    sys.stdout.write("\n".join(sorted(strings)) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
