"""
Stage 2: High-Throughput Out-of-Core Fine-Resolution Grinder
============================================================
Processes massive (750 MB - 16 GB+) fine-frequency resolution (.0000.h5 / .0000.fil / Parkes _fine.h5)
Breakthrough Listen files with hundreds of millions of ~2.7 Hz channels without loading the full
array into RAM.

Architecture:
1. Streams ON-target and OFF-target files to E:\\seti_staging\\raw.
2. Uses blimpy / h5py hyperslab slicing to read 1,048,576 channels (4,096 tiles of 256 bins) at a time.
3. Scores every 256-channel tile across all 5 Weirdness axes + ABACAD ON/OFF veto.
4. Maintains a bounded min-heap of the top N weirdest sky-localized anomalies across the entire 15 GB scan.
5. Renders high-resolution waterfall cutouts and immediately purges the multi-GB raw files from E:\\.
"""

import os
import time
import json
import argparse
import numpy as np
import hdf5plugin  # noqa: F401
import h5py
from blimpy import Waterfall

from targets_catalog import STAGE2_FINE_RES_QUEUE
from weirdness_engine import (
    normalize_bandpass,
    extract_tile_features,
    compute_dedoppler_snr,
    standardize_metric,
    classify_anomaly_type,
)
from run_survey import (
    STAGING_RAW_DIR,
    RESULTS_DIR,
    PLOTS_DIR,
    ensure_dirs,
    download_file_streaming,
    render_candidate_plot,
)


def inspect_file_metadata(filepath: str) -> dict:
    """Reads header metadata and total channel count without loading the spectrogram array."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".h5", ".hdf5"):
        with h5py.File(filepath, "r") as f:
            dset = f["data"]
            attrs = dict(dset.attrs)
            shape = dset.shape
            fch1 = float(attrs.get("fch1", 0.0))
            foff = float(attrs.get("foff", -1e-6))
            tsamp = float(attrs.get("tsamp", 18.25))
            source = attrs.get("source_name", b"UNKNOWN")
            if isinstance(source, bytes):
                source = source.decode("utf-8", errors="ignore")
            return {
                "is_h5": True,
                "source_name": str(source).strip(),
                "n_time": int(shape[0]),
                "n_chans": int(shape[2]),
                "fch1_mhz": fch1,
                "foff_mhz": foff,
                "foff_hz": abs(foff) * 1e6,
                "tsamp_s": tsamp,
                "total_duration_s": float(shape[0] * tsamp),
                "bandwidth_mhz": abs(shape[2] * foff),
            }
    else:
        wf = Waterfall(filepath, load_data=False)
        hdr = wf.header
        n_chans = int(hdr.get("nchans", 0))
        n_time = int(wf.n_ints_in_file)
        fch1 = float(hdr.get("fch1", 0.0))
        foff = float(hdr.get("foff", -1e-6))
        tsamp = float(hdr.get("tsamp", 18.25))
        return {
            "is_h5": False,
            "source_name": str(hdr.get("source_name", "UNKNOWN")).strip(),
            "n_time": n_time,
            "n_chans": n_chans,
            "fch1_mhz": fch1,
            "foff_mhz": foff,
            "foff_hz": abs(foff) * 1e6,
            "tsamp_s": tsamp,
            "total_duration_s": float(n_time * tsamp),
            "bandwidth_mhz": abs(n_chans * foff),
        }


def read_channel_slab(filepath: str, meta: dict, c_start: int, c_end: int) -> tuple[np.ndarray, np.ndarray]:
    """Reads a contiguous slice [c_start:c_end] of channels from disk in ascending frequency order."""
    fch1 = meta["fch1_mhz"]
    foff = meta["foff_mhz"]
    freqs = fch1 + np.arange(c_start, c_end, dtype=np.float64) * foff

    if meta["is_h5"]:
        with h5py.File(filepath, "r") as f:
            slab = f["data"][:, 0, c_start:c_end].astype(np.float32)
    else:
        f_a = fch1 + c_start * foff
        f_b = fch1 + (c_end - 1) * foff
        f_start, f_stop = min(f_a, f_b), max(f_a, f_b)
        wf = Waterfall(filepath, f_start=f_start, f_stop=f_stop, max_load=2.0)
        slab = wf.data[:, 0, :].astype(np.float32)
        freqs = np.linspace(f_a, f_b, slab.shape[1], dtype=np.float64)

    if freqs[0] > freqs[-1]:
        freqs = freqs[::-1].copy()
        slab = slab[:, ::-1].copy()
    return slab, freqs


def grind_fine_cadence(
    target_info: dict,
    slab_chans: int = 1_048_576,
    tile_width: int = 256,
    max_slabs: int | None = None,
    top_k: int = 6,
    keep_raw: bool = False,
) -> dict:
    """Streams and grinds a fine-resolution ON/OFF pair in memory-bounded slabs."""
    ensure_dirs()
    name = target_info["name"]
    print(f"\n=================================================================")
    print(f" STAGE 2 FINE-RES GRINDER: {name}")
    print(f"=================================================================")

    downloaded = []
    try:
        on_path = download_file_streaming(target_info["on_url"], STAGING_RAW_DIR, timeout=300)
        downloaded.append(on_path)
        off_path = None
        if target_info.get("off_url"):
            off_path = download_file_streaming(target_info["off_url"], STAGING_RAW_DIR, timeout=300)
            downloaded.append(off_path)

        meta = inspect_file_metadata(on_path)
        total_chans = meta["n_chans"]
        n_slabs = math.ceil(total_chans / slab_chans) if hasattr(time, "__name__") else (total_chans // slab_chans)
        n_slabs = (total_chans + slab_chans - 1) // slab_chans
        if max_slabs is not None:
            n_slabs = min(n_slabs, max_slabs)

        print(
            f"  [METADATA] Source={meta['source_name']} | Total Chans={total_chans:,} "
            f"| Freq Res={meta['foff_hz']:.2f} Hz | Time Steps={meta['n_time']} | Slabs={n_slabs}"
        )

        all_slab_candidates = []
        total_evaluated_chans = 0
        t0 = time.time()

        for s_idx in range(n_slabs):
            c_start = s_idx * slab_chans
            c_end = min(total_chans, c_start + slab_chans)
            if c_end - c_start < tile_width * 8:
                continue

            on_slab, freqs = read_channel_slab(on_path, meta, c_start, c_end)
            on_z, usable = normalize_bandpass(on_slab, tile_width=tile_width)
            freqs = freqs[:usable]
            T = on_z.shape[0]
            N_tiles = usable // tile_width
            on_tiles = on_z.reshape(T, N_tiles, tile_width)

            feats = extract_tile_features(on_tiles, meta, tile_width=tile_width)

            off_tiles = None
            off_peak_snr = np.ones(N_tiles, dtype=np.float32) * 2.5
            if off_path and os.path.exists(off_path):
                off_slab, _ = read_channel_slab(off_path, meta, c_start, c_end)
                off_z, off_usable = normalize_bandpass(off_slab, tile_width=tile_width)
                c_tiles = min(N_tiles, off_usable // tile_width)
                off_tiles = off_z[:, : c_tiles * tile_width].reshape(off_z.shape[0], c_tiles, tile_width)
                off_drift_snr, _, _ = compute_dedoppler_snr(off_tiles, max_shift_bins=8)
                off_max_pt = np.max(off_tiles, axis=(0, 2)) / 2.0
                off_peak_snr[:c_tiles] = np.maximum(off_drift_snr, off_max_pt)

            on_eff = np.maximum(feats["drift_snr"], feats["ts_max"] * 0.7)
            on_off_ratio = (on_eff + 1.0) / (np.maximum(off_peak_snr, 2.5) + 1.0)

            z_drift = standardize_metric(feats["drift_snr"])
            z_burst = standardize_metric(feats["burst_score"])
            z_curvature = standardize_metric(feats["ridge_curvature_score"])
            z_morphology = standardize_metric(feats["morphology_score"])
            z_manifold = standardize_metric(feats["manifold_score"])
            doppler_bonus = np.where(np.abs(feats["drift_bins"]) >= 1, 1.35, 1.0)

            intrinsic = (
                0.30 * z_drift * doppler_bonus
                + 0.20 * z_burst
                + 0.20 * z_curvature
                + 0.15 * z_morphology
                + 0.15 * z_manifold
            )
            veto_mult = np.where(
                (off_peak_snr > 8.0) & (on_off_ratio < 1.6),
                0.15,
                np.clip(np.sqrt(on_off_ratio), 0.5, 4.0),
            )
            total_weirdness = intrinsic * veto_mult

            # Keep top 2 tiles per slab
            slab_top = np.argsort(total_weirdness)[::-1][:2]
            for idx in slab_top:
                idx = int(idx)
                t_freqs = freqs[idx * tile_width : (idx + 1) * tile_width]
                row = {
                    "slab_idx": s_idx,
                    "tile_idx": int(c_start // tile_width + idx),
                    "center_freq_mhz": round(float(np.mean(t_freqs)), 6),
                    "peak_freq_mhz": round(float(t_freqs[feats["best_chan"][idx]]), 6),
                    "freq_span_khz": round(abs(t_freqs[-1] - t_freqs[0]) * 1e3, 3),
                    "total_weirdness_score": round(float(total_weirdness[idx]), 2),
                    "intrinsic_weirdness": round(float(intrinsic[idx]), 2),
                    "drift_snr": round(float(feats["drift_snr"][idx]), 2),
                    "static_snr": round(float(feats["static_snr"][idx]), 2),
                    "drift_bins": int(feats["drift_bins"][idx]),
                    "drift_rate_hz_s": round(float(feats["drift_rate_hz_s"][idx]), 3),
                    "burst_score": round(float(feats["burst_score"][idx]), 2),
                    "kurtosis": round(float(feats["kurtosis"][idx]), 2),
                    "ts_max": round(float(feats["ts_max"][idx]), 2),
                    "ridge_curvature_score": round(float(feats["ridge_curvature_score"][idx]), 2),
                    "weighted_resid": round(float(feats["weighted_resid"][idx]), 2),
                    "morphology_score": round(float(feats["morphology_score"][idx]), 2),
                    "active_chans_count": int(feats["active_chans_count"][idx]),
                    "manifold_score": round(float(feats["manifold_score"][idx]), 2),
                    "off_peak_snr": round(float(off_peak_snr[idx]), 2),
                    "on_off_ratio": round(float(on_off_ratio[idx]), 2),
                    "z_drift": round(float(z_drift[idx]), 2),
                    "z_burst": round(float(z_burst[idx]), 2),
                    "z_curvature": round(float(z_curvature[idx]), 2),
                    "z_morphology": round(float(z_morphology[idx]), 2),
                    "z_manifold": round(float(z_manifold[idx]), 2),
                    "on_cutout": on_tiles[:, idx, :].copy(),
                    "off_cutout": (
                        off_tiles[:, idx, :].copy()
                        if (off_tiles is not None and idx < off_tiles.shape[1])
                        else np.zeros_like(on_tiles[:, idx, :])
                    ),
                    "tile_freqs_mhz": t_freqs,
                }
                row["classification"] = classify_anomaly_type(row)
                all_slab_candidates.append(row)

            total_evaluated_chans += usable
            print(
                f"  [SLAB {s_idx+1}/{n_slabs}] Chans {c_start:,}..{c_end:,} "
                f"({freqs[0]:.2f}-{freqs[-1]:.2f} MHz) | Peak Weirdness={ np.max(total_weirdness):.1f}"
            )

        all_slab_candidates.sort(key=lambda x: x["total_weirdness_score"], reverse=True)
        final_top = all_slab_candidates[:top_k]

        clean_cands = []
        for rank, cand in enumerate(final_top, 1):
            plot_path, _ = render_candidate_plot(
                "stage2_fine", name, rank, cand, meta, PLOTS_DIR
            )
            c_copy = {
                k: v
                for k, v in cand.items()
                if k not in ("on_cutout", "off_cutout", "tile_freqs_mhz")
            }
            c_copy["plot_path"] = plot_path
            clean_cands.append(c_copy)
            print(
                f"  ★ FINE-RES TOP #{rank}: {cand['peak_freq_mhz']:.6f} MHz | "
                f"Weirdness={cand['total_weirdness_score']:.1f} | Drift={cand['drift_rate_hz_s']:+.3f} Hz/s "
                f"(SNR {cand['drift_snr']:.1f}) | ON/OFF={cand['on_off_ratio']:.2f}x | {cand['classification']}"
            )

        elapsed = round(time.time() - t0, 2)
        out = {
            "name": name,
            "metadata": meta,
            "channels_evaluated": total_evaluated_chans,
            "elapsed_s": elapsed,
            "candidates": clean_cands,
        }
        out_path = os.path.join(RESULTS_DIR, "stage2_fine_report.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        return out

    finally:
        if not keep_raw:
            for p in downloaded:
                if p and os.path.exists(p):
                    os.remove(p)
                    print(f"  [PURGED FINE-RES RAW] {os.path.basename(p)} deleted from E:\\seti_staging\\raw")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 2 Fine-Resolution Out-of-Core SETI Grinder")
    parser.add_argument("--target-idx", type=int, default=3, help="Index in STAGE2_FINE_RES_QUEUE (default 3 = TRAPPIST-1 768MB fine-res)")
    parser.add_argument("--max-slabs", type=int, default=8, help="Max 1M-channel slabs to grind per file")
    parser.add_argument("--keep-raw", action="store_true", help="Keep raw files on E:")
    args = parser.parse_args()
    grind_fine_cadence(
        STAGE2_FINE_RES_QUEUE[args.target_idx],
        max_slabs=args.max_slabs,
        keep_raw=args.keep_raw,
    )
