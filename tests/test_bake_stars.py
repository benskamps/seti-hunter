"""Plan B Task B5: scripts/bake_stars.py bakes the sample and the ribbon bands into site/listen/stars.js."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import bake_stars  # noqa: E402
from survey.snapshot import load_sample_names  # noqa: E402

CSV = ROOT / "tests" / "fixtures" / "gbt_sample_price2020.csv"


def payload(js: str) -> dict:
    m = re.search(r"window\.LISTEN_STARS = (\{.*\});\s*$", js, re.S)
    assert m, "stars.js must assign window.LISTEN_STARS"
    return json.loads(m.group(1))


def test_bake_preserves_sample_order_for_the_searched_bitmap(tmp_path):
    data = payload(bake_stars.bake(CSV, tmp_path / "no-ladder.yaml"))
    assert data["count"] == 1133 == len(data["stars"])
    # The snapshot's `searched` bit i means star i of this exact order.
    assert [s[0] for s in data["stars"]] == load_sample_names(CSV)
    name, ra, dec, bands, mjd = data["stars"][0]
    assert (name, bands) == ("GJ1002", "LS") and abs(ra - 1.675) < 1e-9 and abs(dec + 7.5475) < 1e-9
    assert abs(mjd - 57550.4703) < 1e-3


def test_bands_come_from_ladder_yaml_when_present(tmp_path):
    ladder = tmp_path / "ladder.yaml"
    ladder.write_text("version: 1\nrung4:\n  bands_mhz:\n    iridium: [1616.0, 1626.5]\n    test_band: [2000.0, 2010.0]\n",
                      encoding="utf-8")
    data = payload(bake_stars.bake(CSV, ladder))
    assert data["bands"] == [["iridium", 1616.0, 1626.5], ["test_band", 2000.0, 2010.0]]
    assert data["bands_source"] == "ladder.yaml"


def test_fallback_bands_are_labelled(tmp_path):
    data = payload(bake_stars.bake(CSV, tmp_path / "missing.yaml"))
    assert data["bands_source"].startswith("plan-a-task4-initial")
    assert ["iridium", 1616.0, 1626.5] in data["bands"]
    assert data["notches"] == [[1200.0, 1341.0], [2300.0, 2360.0]]


def test_bake_is_deterministic(tmp_path):
    assert bake_stars.bake(CSV, tmp_path / "x.yaml") == bake_stars.bake(CSV, tmp_path / "x.yaml")
