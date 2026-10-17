"""Plan B Task B2: daily figure export for the Weird Wall and the Ledger."""
import json
from datetime import datetime, timezone

import numpy as np
import pytest
from PIL import Image

import make_fixture_db as fx
from survey.figures_export import FULL_MAX_BYTES, TILE_MAX_BYTES, TILE_SIZE, export

NOW = datetime(2026, 10, 17, 6, 0, tzinfo=timezone.utc)


def write_source_figure(path, seed, noise=False):
    """A 1620x504 three-panel-sized image. noise=True is pure noise: the hardest case for the size caps."""
    rng = np.random.default_rng(seed)
    if noise:
        arr = rng.integers(0, 256, size=(504, 1620, 3), dtype=np.uint8)
    else:
        ramp = np.linspace(0, 200, 1620, dtype=np.float32)[None, :, None]
        arr = np.clip(ramp + rng.normal(0, 6, size=(504, 1620, 3)), 0, 255).astype(np.uint8)
    Image.fromarray(arr).save(path, format="PNG")


@pytest.fixture
def env(tmp_path):
    db = fx.make_fixture_db(str(tmp_path / "survey.sqlite"))
    src = tmp_path / "src"
    src.mkdir()
    for i, (sid,) in enumerate(db.execute("SELECT id FROM signals").fetchall()):
        p = src / f"{sid}.png"
        write_source_figure(p, i)
        db.execute("UPDATE signals SET figure=? WHERE id=?", (str(p), sid))
    db.commit()
    out = tmp_path / "site" / "listen" / "figures"
    yield db, out
    db.close()


def run(db, out):
    return export(db, out_dir=str(out), now_utc=NOW)


def test_only_settled_eliminations_are_written(env):
    db, out = env
    counts = run(db, out)
    items = json.loads((out.parent / "figures.json").read_text(encoding="utf-8"))
    stars = {it["star"] for it in items}
    assert stars == {fx.STAR_PUBLIC}
    assert len(items) == counts["signals"] == 5  # GJ411's five eliminations; untested etc. are not eliminations


def test_star_with_pending_is_withheld(env):
    db, out = env
    run(db, out)
    names = [p.name for p in out.iterdir()]
    raw = (out.parent / "figures.json").read_text(encoding="utf-8")
    for star in (fx.STAR_PENDING, fx.STAR_SURVIVOR):
        assert star not in raw
        assert not any(n.startswith(star) for n in names)
    assert f"{fx.PENDING_FREQ:.3f}" not in raw and f"{fx.SURVIVOR_FREQ:.3f}" not in raw


def test_sizes_capped(env):
    db, out = env
    for i, (path,) in enumerate(db.execute("SELECT figure FROM signals WHERE star=?", (fx.STAR_PUBLIC,))):
        write_source_figure(path, 100 + i, noise=True)
    run(db, out)
    fulls = [p for p in out.glob("*.webp") if not p.name.endswith("_on.webp")]
    tiles = list(out.glob("*_on.webp"))
    assert len(fulls) == len(tiles) == 5
    for p in fulls:
        assert p.stat().st_size <= FULL_MAX_BYTES, p
    for p in tiles:
        assert p.stat().st_size <= TILE_MAX_BYTES, p
        assert Image.open(p).size == TILE_SIZE


def test_items_carry_whitelisted_fields(env):
    db, out = env
    run(db, out)
    it = json.loads((out.parent / "figures.json").read_text(encoding="utf-8"))[0]
    assert set(it) == {"id", "star", "band", "shape", "peak_freq_mhz", "drift_rate_hz_s", "rung", "reason",
                       "weirdness", "scans", "decided_utc", "figure", "tile"}
    assert it["figure"] == f"figures/{it['id']}.webp" and it["tile"] == f"figures/{it['id']}_on.webp"
    assert len(it["scans"]) == 6 and set(it["scans"][0]) == {"role", "snr", "present"}
    assert "seti_staging" not in json.dumps(it) and "src" not in it["figure"]


def test_missing_source_listed_without_figure(env):
    db, out = env
    db.execute("UPDATE signals SET figure=NULL WHERE id='GJ411_L_57542.9764_chirp_t0002'")
    db.commit()
    counts = run(db, out)
    items = {it["id"]: it for it in json.loads((out.parent / "figures.json").read_text(encoding="utf-8"))}
    assert items["GJ411_L_57542.9764_chirp_t0002"]["figure"] is None
    assert items["GJ411_L_57542.9764_chirp_t0002"]["tile"] is None
    assert counts["missing"] == 1


def test_export_is_deterministic(env):
    db, out = env
    run(db, out)
    first = (out.parent / "figures.json").read_bytes()
    tiles1 = {p.name: p.read_bytes() for p in out.iterdir()}
    run(db, out)
    assert (out.parent / "figures.json").read_bytes() == first
    assert {p.name: p.read_bytes() for p in out.iterdir()} == tiles1
    items = json.loads(first)
    keys = [(it["star"], it["peak_freq_mhz"]) for it in items]
    assert keys == sorted(keys)


def test_stale_files_removed(env):
    db, out = env
    run(db, out)
    gone = "GJ411_L_57542.9764_comb_t0004"
    assert (out / f"{gone}.webp").exists()
    # The star gains a pending signal: its whole list is withheld again.
    fx.add_signal(db, "GJ411_S_57543.0102_weird_t0999", "GJ411_S_57543.0102", fx.STAR_PUBLIC, "S", "weird",
                  2100.0, 1.0, "PENDING_R5")
    db.commit()
    counts = run(db, out)
    assert not (out / f"{gone}.webp").exists() and not (out / f"{gone}_on.webp").exists()
    assert counts["removed"] == 10
    assert json.loads((out.parent / "figures.json").read_text(encoding="utf-8")) == []
    (out / "notes.txt").write_text("keep me")  # only our own .webp files are ever deleted
    run(db, out)
    assert (out / "notes.txt").exists()
