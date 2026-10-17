"""Plan B Task B1: the public snapshot and its redaction rules (spec §9)."""
import json
from datetime import datetime, timezone

import pytest

from survey import snapshot as snapmod
from survey.snapshot import SnapshotTooLarge, build_snapshot, serialize
import make_fixture_db as fx

NOW = datetime(2026, 10, 17, 11, 55, tzinfo=timezone.utc)


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    conn = fx.make_fixture_db(str(tmp_path / "survey.sqlite"))
    yield conn
    conn.close()


def snap(db, now=NOW):
    return build_snapshot(db, now, sample_names=fx.SAMPLE)


def funnel_total(f):
    return (sum(f["eliminated_by_rung"].values()) + f["untested"] + f["not_recovered"] + f["incomplete"]
            + f["pending_final_check"] + f["under_review"] + f["public_candidates"])


def test_pending_and_survivor_details_never_serialized(db):
    raw = serialize(snap(db)).decode("utf-8")
    for needle in (fx.PENDING_ID, f"{fx.PENDING_FREQ:.3f}", fx.STAR_PENDING,
                   fx.SURVIVOR_ID, f"{fx.SURVIVOR_FREQ:.3f}", fx.STAR_SURVIVOR):
        assert needle not in raw, needle
    # The counts still carry them.
    s = json.loads(raw)
    assert s["funnel"]["pending_final_check"] == 1
    assert s["funnel"]["under_review"] == 1


def test_local_paths_never_serialized(db):
    raw = serialize(snap(db)).decode("utf-8")
    assert "seti_staging" not in raw and "E:\\" not in raw
    item = json.loads(raw)["recent_eliminated"][0]
    assert item["figure"] == f"figures/{item['id']}.webp"


def test_pending_count_changes_only_at_utc_midnight(db):
    before = snap(db, utc(2026, 10, 17, 11, 55))
    fx.add_signal(db, "HIP4436_S_57803.9344_comb_t0900", "HIP4436_S_57803.9344", fx.STAR_PENDING, "S",
                  "comb", 2050.5, 3.0, "PENDING_R5", created="2026-10-17T12:00:00Z",
                  decided="2026-10-17T12:00:00Z")
    db.commit()
    midday = snap(db, utc(2026, 10, 17, 12, 5))
    late = snap(db, utc(2026, 10, 17, 23, 59))
    nextday = snap(db, utc(2026, 10, 18, 0, 1))
    assert before["funnel"]["pending_final_check"] == 1
    assert midday["funnel"]["pending_final_check"] == 1
    assert late["funnel"]["pending_final_check"] == 1
    assert nextday["funnel"]["pending_final_check"] == 2
    assert midday["pending_batch_utc"] == "2026-10-17T00:00:00Z"
    assert nextday["pending_batch_utc"] == "2026-10-18T00:00:00Z"


def test_funnel_sums_to_flagged(db):
    s = snap(db)
    f = s["funnel"]
    assert f["flagged"] == 12
    assert funnel_total(f) == f["flagged"]
    assert f["eliminated_by_rung"] == {"1": 1, "2": 2, "3": 1, "4": 2, "5": 1}
    assert {r["star"] for r in s["recent_eliminated"]} == {fx.STAR_PUBLIC}

    # Review Focus 3: finalize eliminates the pending signal at rung 5.
    db.execute("UPDATE signals SET verdict='ELIMINATED', rung=5, reason='also seen at GJ411', "
               "decided_utc='2026-10-17T12:30:00Z' WHERE id=?", (fx.PENDING_ID,))
    db.commit()
    s2 = snap(db, utc(2026, 10, 17, 12, 35))
    f2 = s2["funnel"]
    assert funnel_total(f2) == f2["flagged"] == 12
    assert f2["pending_final_check"] == 0
    assert f2["eliminated_by_rung"]["5"] == 2
    pending_star_rows = [r for r in s2["recent_eliminated"] if r["star"] == fx.STAR_PENDING]
    assert {r["id"] for r in pending_star_rows} == {fx.PENDING_ID, "HIP4436_S_57803.9344_wide_drift_t0007"}
    assert s2["recent_eliminated"][0]["id"] == fx.PENDING_ID  # newest first


def test_counts_never_drop_mid_day_while_a_star_is_scored(db):
    """A two-band star is scored mid-day: L eliminates a signal, then S finds a pending one.

    Nothing about it may move the public counts until the star is finished, and
    once it holds a pending signal its rows wait for the next 00:00 UTC batch.
    So no snapshot during the day can drop a count or show-then-hide a row
    (either would point at the star in the heartbeat). This relies on the
    runner registering every cadence as queued before scoring starts.
    """
    fx.add_cadence(db, "GJ1245AC_S_57587.2100", fx.STAR_LIVE, "S", "queued", started=None, finished=None)
    db.commit()
    seen = [snap(db, utc(2026, 10, 17, 7, 0))]
    db.execute("UPDATE cadences SET status='scored' WHERE id='GJ1245AC_L_57587.1893'")
    fx.add_signal(db, "GJ1245AC_L_57587.1893_comb_t0001", "GJ1245AC_L_57587.1893", fx.STAR_LIVE, "L",
                  "comb", 1500.25, 1.0, "ELIMINATED", 1, fx.REASONS[1],
                  created="2026-10-17T08:40:00Z", decided="2026-10-17T08:40:00Z")
    db.commit()
    seen.append(snap(db, utc(2026, 10, 17, 9, 0)))
    db.execute("UPDATE cadences SET status='scored' WHERE id='GJ1245AC_S_57587.2100'")
    fx.add_signal(db, "GJ1245AC_S_57587.2100_weird_t0002", "GJ1245AC_S_57587.2100", fx.STAR_LIVE, "S",
                  "weird", 2222.5, 4.0, "PENDING_R5", created="2026-10-17T10:40:00Z",
                  decided="2026-10-17T10:40:00Z")
    db.commit()
    seen.append(snap(db, utc(2026, 10, 17, 11, 0)))
    seen.append(snap(db, utc(2026, 10, 17, 23, 59)))
    for s in seen:
        assert s["funnel"] == seen[0]["funnel"]
        assert not any(r["star"] == fx.STAR_LIVE for r in s["recent_eliminated"])
    nextday = snap(db, utc(2026, 10, 18, 0, 1))
    assert nextday["funnel"]["flagged"] == seen[0]["funnel"]["flagged"] + 2
    assert nextday["funnel"]["pending_final_check"] == seen[0]["funnel"]["pending_final_check"] + 1
    assert funnel_total(nextday["funnel"]) == nextday["funnel"]["flagged"]
    assert not any(r["star"] == fx.STAR_LIVE for r in nextday["recent_eliminated"])


def test_unfinished_star_held_until_its_cadences_finish(db):
    fx.add_cadence(db, "GJ1245AC_S_57587.2100", fx.STAR_LIVE, "S", "scored",
                   started="2026-10-17T10:00:00Z", finished="2026-10-17T10:40:00Z")
    fx.add_signal(db, "GJ1245AC_S_57587.2100_comb_t0003", "GJ1245AC_S_57587.2100", fx.STAR_LIVE, "S",
                  "comb", 2100.75, 1.0, "ELIMINATED", 3, fx.REASONS[3],
                  created="2026-10-17T10:40:00Z", decided="2026-10-17T10:40:00Z")
    db.commit()
    held = snap(db)  # the L cadence is still queued
    assert held["funnel"]["flagged"] == 12
    assert not any(r["star"] == fx.STAR_LIVE for r in held["recent_eliminated"])
    db.execute("UPDATE cadences SET status='scored' WHERE id='GJ1245AC_L_57587.1893'")
    db.commit()
    done = snap(db)
    assert done["funnel"]["flagged"] == 13
    assert any(r["star"] == fx.STAR_LIVE for r in done["recent_eliminated"])


def test_planted_signals_excluded(db):
    db.execute("UPDATE signals SET planted=1 WHERE id='GJ411_L_57542.9764_wide_drift_t0001'")
    db.commit()
    s = snap(db)
    assert s["funnel"]["flagged"] == 11
    assert all(r["id"] != "GJ411_L_57542.9764_wide_drift_t0001" for r in s["recent_eliminated"])


def test_truncates_recent_list_to_fit(db):
    for i in range(5000):
        fx.add_signal(db, f"GJ411_L_57542.9764_weird_t{9000 + i:05d}", "GJ411_L_57542.9764",
                      fx.STAR_PUBLIC, "L", "weird", 1100.0 + i * 0.01, 1.5, "ELIMINATED", 1,
                      fx.REASONS[1] + " and a long-ish trailing explanation to add bytes",
                      decided=f"2026-10-1{5 + i // 2000}T{(i // 60) % 24:02d}:{i % 60:02d}:00Z")
    db.commit()
    s = snap(db)
    raw = serialize(s)
    assert len(raw) <= 256 * 1024
    out = json.loads(raw)
    assert len(out["recent_eliminated"]) == 200
    stamps = [r["decided_utc"] for r in out["recent_eliminated"]]
    assert stamps == sorted(stamps, reverse=True)
    assert out["funnel"]["eliminated_by_rung"]["1"] == 5001  # counts stay complete


def test_serialize_truncates_then_raises(db):
    s = snap(db)
    s["recent_eliminated"] = [dict(s["recent_eliminated"][0], reason="x" * 2000) for _ in range(200)]
    raw = serialize(s)
    assert len(raw) <= 256 * 1024
    assert 0 < len(json.loads(raw)["recent_eliminated"]) < 200
    s["progress"]["padding"] = "y" * (300 * 1024)
    with pytest.raises(SnapshotTooLarge):
        serialize(s)


def test_uses_given_now_not_clock(db, monkeypatch):
    class NoClock(datetime):
        @classmethod
        def now(cls, tz=None):
            raise AssertionError("snapshot read the wall clock")

        @classmethod
        def utcnow(cls):
            raise AssertionError("snapshot read the wall clock")

        @classmethod
        def today(cls):
            raise AssertionError("snapshot read the wall clock")

    monkeypatch.setattr(snapmod, "datetime", NoClock)
    s = snap(db)
    assert s["as_of_utc"] == "2026-10-17T11:55:00Z"


def test_rejects_naive_now(db):
    with pytest.raises(ValueError):
        build_snapshot(db, datetime(2026, 10, 17, 11, 55), sample_names=fx.SAMPLE)


def test_mode_demo_when_no_cadence_scored(db):
    assert snap(db)["mode"] == "MEASURED"
    db.execute("UPDATE cadences SET status='queued'")
    db.commit()
    assert snap(db)["mode"] == "DEMO"


def test_progress_and_heartbeat(db):
    s = snap(db)
    p = s["progress"]
    assert p["stars_total"] == len(fx.SAMPLE)
    assert p["cadences_total"] == 7
    assert p["cadences_done"] == 4
    assert p["cadences_parked"] == 1
    assert p["cadences_incomplete"] == 1
    assert p["stars_done"] == 4  # every star except the queued one
    # searched: hex bitmap over sample order; bit i set = star i finished.
    bits = int(p["searched"], 16)
    assert [bool(bits >> i & 1) for i in range(len(fx.SAMPLE))] == [True, True, True, True, False]
    assert p["bytes_streamed"] == 5_812_000_000
    assert s["heartbeat"] == {"star": fx.STAR_LIVE, "scan_idx": 3, "speed_mb_s": 1.31,
                              "updated_utc": "2026-10-17T11:50:00Z"}
    assert len(s["speed_series"]) == 60
    assert s["speed_series"][0] < s["speed_series"][-1]  # oldest first
    assert s["schema"] == 1
    assert set(s) == {"schema", "as_of_utc", "mode", "progress", "funnel", "pending_batch_utc",
                      "recent_eliminated", "heartbeat", "speed_series"}
    assert set(s["recent_eliminated"][0]) == {"id", "star", "band", "shape", "peak_freq_mhz",
                                              "drift_rate_hz_s", "rung", "reason", "weirdness",
                                              "figure", "decided_utc"}


def test_stars_total_defaults_to_the_sample_file(db):
    s = build_snapshot(db, NOW, sample_path="tests/fixtures/gbt_sample_price2020.csv")
    assert s["progress"]["stars_total"] == 1133
