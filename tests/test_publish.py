"""Plan B Task B3: publish the snapshot to the public gist (fake runner, no network)."""
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import make_fixture_db as fx
from survey.publish import maybe_publish, read_gist_id
from survey.snapshot import build_snapshot, serialize

T0 = datetime(2026, 10, 17, 11, 55, tzinfo=timezone.utc)
GIST = "0123456789abcdef0123456789abcdef"


class FakeGh:
    def __init__(self, returncode=0, stderr="", raises=None):
        self.calls, self.payloads = [], []
        self.returncode, self.stderr, self.raises = returncode, stderr, raises

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if self.raises:
            raise self.raises
        self.payloads.append(Path(cmd[-1]).read_bytes())  # read while the tmpfile exists
        return subprocess.CompletedProcess(cmd, self.returncode, stdout="", stderr=self.stderr)


@pytest.fixture
def db(tmp_path):
    conn = fx.make_fixture_db(str(tmp_path / "survey.sqlite"))
    yield conn
    conn.close()


def publish(db, now, gh, **kw):
    return maybe_publish(db, GIST, now, runner=gh, sample_names=fx.SAMPLE, **kw)


def events(db, kind):
    return db.execute("SELECT utc, detail FROM events WHERE kind=? ORDER BY utc", (kind,)).fetchall()


def test_respects_interval(db):
    gh = FakeGh()
    assert publish(db, T0, gh) is True
    assert publish(db, T0 + timedelta(minutes=14, seconds=59), gh) is False
    assert publish(db, T0 + timedelta(minutes=15), gh) is True
    assert len(gh.calls) == 2
    assert [u for u, _ in events(db, "publish")] == ["2026-10-17T11:55:00Z", "2026-10-17T12:10:00Z"]


def test_command_shape(db):
    gh = FakeGh()
    publish(db, T0, gh)
    cmd = gh.calls[0]
    assert cmd[:6] == ["gh", "gist", "edit", GIST, "-f", "snapshot.json"]
    assert Path(cmd[6]).name == "snapshot.json"
    assert not Path(cmd[6]).exists()  # tmpfile cleaned up


def test_publishes_serialized_bytes_exactly(db):
    gh = FakeGh()
    publish(db, T0, gh)
    assert gh.payloads[0] == serialize(build_snapshot(db, T0, sample_names=fx.SAMPLE))


def test_gh_failure_is_logged_not_raised(db):
    gh = FakeGh(returncode=1, stderr="HTTP 502: Bad Gateway")
    assert publish(db, T0, gh) is False
    (utc, detail), = events(db, "publish_failed")
    assert utc == "2026-10-17T11:55:00Z" and "502" in detail
    assert events(db, "publish") == []
    # A failure doesn't start the interval: the next cadence tries again.
    ok = FakeGh()
    assert publish(db, T0 + timedelta(minutes=1), ok) is True


def test_missing_gh_or_timeout_is_logged_not_raised(db):
    for exc in (FileNotFoundError("gh"), subprocess.TimeoutExpired("gh", 120)):
        assert publish(db, T0, FakeGh(raises=exc)) is False
    assert len(events(db, "publish_failed")) == 2


def test_snapshot_failure_is_logged_not_raised(db):
    db.execute("UPDATE signals SET verdict='MYSTERY' WHERE id=?", (fx.PENDING_ID,))
    db.commit()
    gh = FakeGh()
    assert publish(db, T0, gh) is False
    assert gh.calls == []
    assert "MYSTERY" in events(db, "publish_failed")[0][1]


def test_read_gist_id(tmp_path):
    p = tmp_path / "gist_id.txt"
    assert read_gist_id(p) is None
    p.write_text("  " + GIST + "\n")
    assert read_gist_id(p) == GIST
    p.write_text("not a gist; rm -rf /")
    with pytest.raises(ValueError):
        read_gist_id(p)


def test_malformed_last_publish_time_does_not_raise(db):
    db.execute("INSERT INTO events VALUES ('not a time', 'publish', '1 bytes')")
    db.commit()
    assert publish(db, T0, FakeGh()) in (True, False)


def test_a_database_that_refuses_writes_does_not_raise(tmp_path):
    path = tmp_path / "ro.sqlite"
    fx.make_fixture_db(str(path)).close()
    import sqlite3
    ro = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for gh in (FakeGh(returncode=1, stderr="boom"), FakeGh(raises=FileNotFoundError("gh")), FakeGh()):
            maybe_publish(ro, GIST, T0, runner=gh, sample_names=fx.SAMPLE)  # must not raise
    finally:
        ro.close()


def test_publish_if_configured_is_the_never_raising_runner_hook(db, tmp_path):
    from survey.publish import publish_if_configured
    gh = FakeGh()
    missing = tmp_path / "none.txt"
    assert publish_if_configured(db, T0, gist_file=missing, runner=gh, sample_names=fx.SAMPLE) is False
    bad = tmp_path / "bad.txt"
    bad.write_text("not a gist; rm -rf /")
    assert publish_if_configured(db, T0, gist_file=bad, runner=gh, sample_names=fx.SAMPLE) is False
    assert gh.calls == []
    assert "gist id" in events(db, "publish_failed")[-1][1]
    good = tmp_path / "good.txt"
    good.write_text(GIST)
    assert publish_if_configured(db, T0, gist_file=good, runner=gh, sample_names=fx.SAMPLE) is True
