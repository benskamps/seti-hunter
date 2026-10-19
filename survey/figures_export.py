"""Daily export of eliminated-signal figures for the Weird Wall and the Ledger (spec §9).

Every ELIMINATED, non-planted signal of a *listed* star (see survey.snapshot:
finished and holding nothing pending or under review, or any finished star
once the run has ended) is published, in two layers sized for a survey that
may flag 10^4-10^5 signals:

    <out_dir>/../figures.json         the Wall: the `max_figures` weirdest, whitelisted items
    <out_dir>/{id}.webp               their full three-panel figures, <= FULL_MAX_BYTES
    <out_dir>/{id}_on.webp            their ON-panel tiles, TILE_SIZE, <= TILE_MAX_BYTES
    <out_dir>/../ledger/{slug}.json   the Ledger: every listed signal of one star (images only for the capped few)
    <out_dir>/../ledger/index.json    {star: {file, count}} for the page's "find a star"

Images and Wall entries are capped because they go into a public repo's
permanent history (~66 KB of webp per signal). Anything no longer eligible
(images, shards) is deleted, so a star that gains a pending signal leaves the
Wall and the Ledger at the next export. Same database + same source figures ->
byte-identical output.

    python -m survey.figures_export [--db PATH] [--out site/listen/figures] [--max-figures N]
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from survey.snapshot import settled_stars

FULL_MAX_BYTES = 120 * 1024
TILE_MAX_BYTES = 25 * 1024
TILE_SIZE = (300, 232)
# The ON waterfall's plot area on run_survey.render_candidate_plot's 1620x504 figure
# (figsize 13.5x4.2 in at 120 dpi), as cropped in the approved Wall mockup.
FIGURE_SIZE = (1620, 504)
ON_CROP = (97, 82, 540, 424)
DEFAULT_SRC = Path(r"E:\seti_staging\results\figures")
DEFAULT_DB = Path(r"E:\seti_staging\state\survey.sqlite")

MAX_FIGURES = 400  # Wall entries with images: ~26 MB of webp at the cap
# A figure's ON cutout spans ~0.73 MHz. No image is published for a signal within this many MHz
# of a pending or survivor signal of the same cadence: the neighbour's waterfall could show it.
GUARD_MHZ = 2.0
QUALITIES = (82, 70, 58, 46, 34, 22, 12)
FULL_SCALES = (1.0, 0.85, 0.7, 0.55, 0.4)
OURS = re.compile(r"^(?P<id>.+?)(?P<on>_on)?\.webp$")


def _encode(im: Image.Image, cap: int, scales=(1.0,)) -> bytes:
    """Smallest-effort WebP under `cap`: highest quality first, then downscale."""
    for s in scales:
        frame = im if s == 1.0 else im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        for q in QUALITIES:
            buf = io.BytesIO()
            frame.save(buf, format="WEBP", quality=q, method=4)
            if buf.tell() <= cap:
                return buf.getvalue()
    raise ValueError(f"cannot encode a {im.size} figure under {cap} bytes")


def _on_crop(im: Image.Image) -> Image.Image:
    if im.size != FIGURE_SIZE:  # crop box is defined on the standard figure; scale it for others
        sx, sy = im.width / FIGURE_SIZE[0], im.height / FIGURE_SIZE[1]
        box = (round(ON_CROP[0] * sx), round(ON_CROP[1] * sy), round(ON_CROP[2] * sx), round(ON_CROP[3] * sy))
    else:
        box = ON_CROP
    return im.crop(box).resize(TILE_SIZE, Image.LANCZOS)


def _write_if_changed(path: Path, data: bytes) -> None:
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)


def _scans(scans_json: str | None) -> list[dict]:
    out = []
    for r in json.loads(scans_json or "[]"):
        snr = r.get("snr")
        out.append({"role": str(r.get("role", "")),
                    "snr": None if snr is None else round(float(snr), 2),
                    "present": r.get("present") if r.get("present") in (True, False) else None})
    return out


def _source(figure_col: str | None, sid: str, src_dir: Path) -> Path | None:
    for cand in (Path(figure_col) if figure_col else None, src_dir / f"{sid}.webp", src_dir / f"{sid}.png"):
        if cand is not None and cand.is_file():
            return cand
    return None


def _slug(star: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", star)


def _dump(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _order(it):
    return (it["star"], it["peak_freq_mhz"] if it["peak_freq_mhz"] is not None else -1, it["id"])


def export(db: sqlite3.Connection, out_dir="site/listen/figures", now_utc: datetime | None = None,
           *, src_dir=DEFAULT_SRC, max_figures: int = MAX_FIGURES) -> dict:
    """Write the Wall (figures.json + capped images) and the per-star Ledger shards. Returns counts.

    `now_utc` is accepted for the daily commit message; eligibility depends only
    on the database (figures publish daily, behind the live counts).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ledger_dir = out.parent / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    src_dir = Path(src_dir)
    _, listed = settled_stars(db)
    rows = []
    if listed:
        marks = ",".join("?" * len(listed))
        rows = db.execute(
            "SELECT id, star, band, shape, peak_freq_mhz, drift_rate_hz_s, rung, reason, weirdness, snr, scans_json, "
            f"decided_utc, figure, cadence_id FROM signals WHERE verdict='ELIMINATED' AND COALESCE(planted,0)=0 "
            f"AND star IN ({marks})", sorted(listed)).fetchall()
    # Held signals (pending or under review): no image may be published near one (see GUARD_MHZ).
    held = db.execute("SELECT cadence_id, peak_freq_mhz FROM signals WHERE COALESCE(planted,0)=0 "
                      "AND verdict IN ('PENDING_R5','SURVIVOR') AND peak_freq_mhz IS NOT NULL").fetchall()

    def near_held(cadence_id, f) -> bool:
        return f is not None and any(c == cadence_id and abs(float(f) - hf) <= GUARD_MHZ for c, hf in held)

    items, sources, guarded = [], {}, set()
    for (sid, star, band, shape, f, drift, rung, reason, weird, snr, scans_json, decided, fig_col, cad) in rows:
        items.append({
            "id": sid, "star": star, "band": band, "shape": shape,
            "peak_freq_mhz": None if f is None else round(float(f), 6),
            "drift_rate_hz_s": None if drift is None else round(float(drift), 3),
            "rung": int(rung), "reason": reason,
            "weirdness": None if weird is None else round(float(weird), 3),
            "snr": None if snr is None else round(float(snr), 2),
            "scans": _scans(scans_json), "decided_utc": decided,
            "figure": None, "tile": None,
        })
        sources[sid] = _source(fig_col, sid, src_dir)
        if near_held(cad, f):
            guarded.add(sid)

    # The Wall is cutouts: of the listed signals that have a figure (and aren't near a held
    # signal), the `max_figures` weirdest; most committed-shape flags carry no weirdness (only
    # the weird channel does), so SNR ranks next. Ties break by id: the cut is deterministic.
    def rank(it):
        w, s = it["weirdness"], it["snr"]
        return (w is None, -(w or 0.0), s is None, -(s or 0.0), it["id"])

    candidates = [it for it in items if sources[it["id"]] is not None and it["id"] not in guarded]
    missing = sum(1 for it in items if sources[it["id"]] is None)
    wall = sorted(candidates, key=rank)[:max_figures]
    keep, written = set(), 0
    for item in wall:
        sid = item["id"]
        src = sources[sid]
        full_p, tile_p = out / f"{sid}.webp", out / f"{sid}_on.webp"
        stale = not (full_p.exists() and tile_p.exists()) or min(
            full_p.stat().st_mtime, tile_p.stat().st_mtime) < src.stat().st_mtime
        if stale:
            with Image.open(src) as im:
                im = im.convert("RGB")
                _write_if_changed(full_p, _encode(im, FULL_MAX_BYTES, FULL_SCALES))
                _write_if_changed(tile_p, _encode(_on_crop(im), TILE_MAX_BYTES))
            written += 1
        keep.update({full_p.name, tile_p.name})
        item["figure"] = f"figures/{full_p.name}"
        item["tile"] = f"figures/{tile_p.name}"

    removed = 0
    for p in out.iterdir():
        if p.is_file() and OURS.match(p.name) and p.name not in keep:
            p.unlink()
            removed += 1

    _write_if_changed(out.parent / "figures.json", _dump(sorted(wall, key=_order)))

    # The Ledger: one shard per listed star with every one of its listed signals.
    by_star: dict[str, list] = {}
    for it in items:
        by_star.setdefault(it["star"], []).append(it)
    index, shards = {}, set()
    for star in sorted(by_star):
        name = f"{_slug(star)}.json"
        shards.add(name)
        _write_if_changed(ledger_dir / name, _dump(sorted(by_star[star], key=_order)))
        index[star] = {"file": f"ledger/{name}", "count": len(by_star[star])}
    for p in ledger_dir.iterdir():
        if p.is_file() and p.suffix == ".json" and p.name != "index.json" and p.name not in shards:
            p.unlink()
    _write_if_changed(ledger_dir / "index.json", _dump(index))
    return {"signals": len(items), "wall": len(wall), "figures": len(keep) // 2, "written": written,
            "missing": missing, "removed": removed, "stars": len(index)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default="site/listen/figures")
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--max-figures", type=int, default=MAX_FIGURES)
    a = ap.parse_args(argv)
    db = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    try:
        counts = export(db, a.out, datetime.now(timezone.utc), src_dir=a.src, max_figures=a.max_figures)
    finally:
        db.close()
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
