"""No committed file under scripts/ or site/ may name a survivor (Ben's survivor policy, spec §9).

seti-hunter is a public repo. A survivor's id and frequency live only in the
private pilot file (Plan A's pilot_expected.json); this reads them from there at
run time, so the strings it guards against are never written into the repo. If
the private file can't be found the test FAILS: a guard that can't see what it
guards proves nothing.

    LISTEN_PILOT=<path to pilot_expected.json> python -m pytest tests/test_no_survivor_strings.py
"""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
import sys  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from survivor_strings import forbidden_strings, pilot_path  # noqa: E402


def committed_files(*dirs: str) -> list[Path]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", *dirs],
                         capture_output=True, check=True).stdout
    return [ROOT / p for p in out.decode("utf-8").split("\0") if p]


def test_the_private_pilot_file_is_reachable():
    path = pilot_path()
    assert path is not None, ("the survivor guard needs the private pilot file: set LISTEN_PILOT to "
                              "Plan A's data/pilot_expected.json (it is never committed here)")


def test_no_committed_file_under_scripts_or_site_names_a_survivor():
    path = pilot_path()
    if path is None:
        pytest.fail("LISTEN_PILOT is not set and no pilot_expected.json was found: the guard cannot see")
    needles = forbidden_strings(path)
    assert needles, f"{path} names no survivor: nothing to guard, which is itself suspicious"
    hits = []
    for f in committed_files("scripts", "site"):
        rel = f.relative_to(ROOT).as_posix()
        for n in needles:
            if n in rel:
                hits.append(f"{rel} (path)")
        if not f.is_file():
            continue
        data = f.read_bytes()
        for n in needles:
            if n.encode("utf-8") in data:
                hits.append(rel)
                break
    assert not hits, f"committed files name a survivor (id or frequency): {sorted(set(hits))}"


def test_the_guard_can_fail(tmp_path):
    """A planted file carrying a survivor's frequency is caught (the check is not 'return True')."""
    path = pilot_path()
    if path is None:
        pytest.fail("no pilot file: see test_the_private_pilot_file_is_reachable")
    needles = forbidden_strings(path)
    planted = tmp_path / "planted.txt"
    planted.write_text(f"leak: {sorted(needles)[0]}", encoding="utf-8")
    assert any(n.encode() in planted.read_bytes() for n in needles)
