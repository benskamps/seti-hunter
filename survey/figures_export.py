"""Daily export of eliminated-signal figures for the Weird Wall and the Ledger (spec §9).

Writes, for every ELIMINATED, non-planted signal of a *settled* star (see
survey.snapshot: every cadence finished, nothing pending or under review):

    <out_dir>/{id}.webp       the full three-panel figure, <= FULL_MAX_BYTES
    <out_dir>/{id}_on.webp    the ON-panel crop for Wall tiles, TILE_SIZE, <= TILE_MAX_BYTES
    <out_dir>/../figures.json one whitelisted item per signal, sorted by (star, peak_freq_mhz, id)

Any {id}.webp / {id}_on.webp in out_dir that is no longer eligible is deleted,
so a star that gains a pending signal drops off the Wall at the next export.
Same database + same source figures -> byte-identical output.

    python -m survey.figures_export [--db PATH] [--out site/listen/figures]
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


def export(db: sqlite3.Connection, out_dir="site/listen/figures", now_utc: datetime | None = None,
           *, src_dir=DEFAULT_SRC) -> dict:
    """Write the Wall/Ledger figures and figures.json. Returns counts.

    `now_utc` is accepted for the daily commit message and future use; eligibility
    depends only on the database (figures publish daily, behind the live counts).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    src_dir = Path(src_dir)
    _, settled = settled_stars(db)
    rows = []
    if settled:
        marks = ",".join("?" * len(settled))
        rows = db.execute(
            "SELECT id, star, band, shape, peak_freq_mhz, drift_rate_hz_s, rung, reason, weirdness, scans_json, "
            f"decided_utc, figure FROM signals WHERE verdict='ELIMINATED' AND COALESCE(planted,0)=0 "
            f"AND star IN ({marks})", sorted(settled)).fetchall()

    items, keep, missing, written = [], set(), 0, 0
    for (sid, star, band, shape, f, drift, rung, reason, weird, scans_json, decided, fig_col) in rows:
        src = _source(fig_col, sid, src_dir)
        item = {
            "id": sid, "star": star, "band": band, "shape": shape,
            "peak_freq_mhz": None if f is None else round(float(f), 6),
            "drift_rate_hz_s": None if drift is None else round(float(drift), 3),
            "rung": int(rung), "reason": reason,
            "weirdness": None if weird is None else round(float(weird), 3),
            "scans": _scans(scans_json), "decided_utc": decided,
            "figure": None, "tile": None,
        }
        if src is None:
            missing += 1
        else:
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
        items.append(item)

    removed = 0
    for p in out.iterdir():
        if p.is_file() and OURS.match(p.name) and p.name not in keep:
            p.unlink()
            removed += 1

    items.sort(key=lambda it: (it["star"], it["peak_freq_mhz"] if it["peak_freq_mhz"] is not None else -1, it["id"]))
    data = (json.dumps(items, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    _write_if_changed(out.parent / "figures.json", data)
    return {"signals": len(items), "figures": len(keep) // 2, "written": written, "missing": missing,
            "removed": removed}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default="site/listen/figures")
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    a = ap.parse_args(argv)
    db = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    try:
        counts = export(db, a.out, datetime.now(timezone.utc), src_dir=a.src)
    finally:
        db.close()
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
