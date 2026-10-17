"""
Full-cadence follow-up for Stage 1 candidates
=============================================
Stage 1 scores each target from ONE ON scan vs ONE OFF scan. This script pulls
every scan of a real ON/OFF/ON/OFF/ON/OFF cadence and asks, for each candidate:
is the signal present in every ON scan at the frequency its drift rate predicts,
and absent from every OFF scan? That is the standard Breakthrough Listen test.

Usage:
    python cadence_check.py                 # Tabby's Star candidates from survey_report.json
    python cadence_check.py --keep-raw      # keep the 6 raw files on E: afterwards
"""

import argparse
import json
import os

import numpy as np

from run_survey import RESULTS_DIR, STAGING_RAW_DIR, download_file_streaming, ensure_dirs
from weirdness_engine import load_spectrogram_fast

TABBY_BASE = "https://bldata.berkeley.edu/pipeline/AGBT17A_999_68/holding/"
TABBY_SCANS = [
    ("ON", "spliced_blc2021222324252627_guppi_57898_22410_DIAG_KIC8462852_0031.gpuspec.0002.h5"),
    ("OFF", "spliced_blc2021222324252627_guppi_57898_22733_DIAG_KIC8462852_OFF_0032.gpuspec.0002.h5"),
    ("ON", "spliced_blc2021222324252627_guppi_57898_23056_DIAG_KIC8462852_0033.gpuspec.0002.h5"),
    ("OFF", "spliced_blc2021222324252627_guppi_57898_23379_DIAG_KIC8462852_OFF_0034.gpuspec.0002.h5"),
    ("ON", "spliced_blc2021222324252627_guppi_57898_23702_DIAG_KIC8462852_0035.gpuspec.0002.h5"),
    ("OFF", "spliced_blc2021222324252627_guppi_57898_24026_DIAG_KIC8462852_OFF_0036.gpuspec.0002.h5"),
]

# Known OFF-present carrier from the 2026-10-15 run (OFF SNR 3897, zero drift).
# A working check must call this one RFI; if it doesn't, the check is broken.
NEGATIVE_CONTROL = {"label": "control: OFF-present RFI", "peak_freq_mhz": 2193.5658, "drift_rate_hz_s": 0.0}

DETECT_SNR = 10.0      # integrated-spectrum SNR that counts as "present"
SEARCH_CHANS = 40      # +/- channels searched around the predicted frequency
BG_CHANS = 2000        # +/- channels used to estimate the local noise floor


def window_snr(spec: np.ndarray, freqs: np.ndarray, f_expected_mhz: float) -> tuple[float, float]:
    """Peak SNR within +/-SEARCH_CHANS of f_expected, against a robust local noise floor.
    Returns (snr, offset_khz of the peak from f_expected)."""
    i0 = int(np.argmin(np.abs(freqs - f_expected_mhz)))
    lo, hi = max(i0 - BG_CHANS, 0), min(i0 + BG_CHANS, len(spec))
    bg = np.concatenate([spec[lo : max(i0 - SEARCH_CHANS, lo)], spec[min(i0 + SEARCH_CHANS + 1, hi) : hi]])
    med = float(np.median(bg))
    sigma = max(1.4826 * float(np.median(np.abs(bg - med))), 1e-9)
    s_lo, s_hi = max(i0 - SEARCH_CHANS, 0), min(i0 + SEARCH_CHANS + 1, len(spec))
    k = s_lo + int(np.argmax(spec[s_lo:s_hi]))
    return (float(spec[k]) - med) / sigma, (freqs[k] - f_expected_mhz) * 1e3


def verdict(rows: list[dict]) -> str:
    on = [r["present"] for r in rows if r["role"] == "ON"]
    off = [r["present"] for r in rows if r["role"] == "OFF"]
    if any(off):
        return "RFI - present in an OFF scan"
    if all(on):
        return "PASSES cadence - in every ON, no OFF"
    if on[0] and not any(on[1:]):
        return "ONE-OFF - only in the first ON scan (transient or local RFI)"
    return f"PARTIAL - in {sum(on)}/{len(on)} ON scans, no OFF"


def main(keep_raw: bool) -> None:
    ensure_dirs()
    report = json.load(open(os.path.join(RESULTS_DIR, "survey_report.json"), encoding="utf-8"))
    tabby = next(c for c in report["cadences"] if c["cadence_id"] == "tabbys_star_sband")
    cands = [
        {"label": f"rank {i}", "peak_freq_mhz": c["peak_freq_mhz"], "drift_rate_hz_s": c["drift_rate_hz_s"]}
        for i, c in enumerate(tabby["candidates"], 1)
    ] + [NEGATIVE_CONTROL]

    paths = [download_file_streaming(TABBY_BASE + fn, STAGING_RAW_DIR, timeout=300) for _, fn in TABBY_SCANS]

    results = {c["label"]: {"candidate": c, "scans": []} for c in cands}
    t_ref = None
    for (role, fn), path in zip(TABBY_SCANS, paths):
        data, freqs, hdr = load_spectrogram_fast(path)
        spec = data.mean(axis=0)
        if freqs[0] > freqs[-1]:
            freqs, spec = freqs[::-1], spec[::-1]
        t_mid = hdr["tstart_mjd"] * 86400.0 + hdr["total_duration_s"] / 2
        t_ref = t_mid if t_ref is None else t_ref
        dt = t_mid - t_ref
        for c in cands:
            f_exp = c["peak_freq_mhz"] + c["drift_rate_hz_s"] * dt / 1e6
            snr, off_khz = window_snr(spec, freqs, f_exp)
            results[c["label"]]["scans"].append({
                "scan": fn.split("_")[-1].split(".")[0], "role": role, "dt_s": round(dt, 1),
                "f_expected_mhz": round(f_exp, 6), "snr": round(snr, 1),
                "peak_offset_khz": round(off_khz, 2), "present": bool(snr >= DETECT_SNR),
            })
        del data

    print(f"\nTabby's Star full cadence check (present = SNR >= {DETECT_SNR}, searched +/-{SEARCH_CHANS} channels)\n")
    for label, r in results.items():
        r["verdict"] = verdict(r["scans"])
        c = r["candidate"]
        print(f"{label:28s} {c['peak_freq_mhz']:.4f} MHz  drift {c['drift_rate_hz_s']:+.2f} Hz/s  ->  {r['verdict']}")
        for s in r["scans"]:
            print(f"    {s['role']:3s} {s['scan']}  dt={s['dt_s']:7.1f}s  SNR={s['snr']:9.1f}  offset={s['peak_offset_khz']:+8.2f} kHz")

    out = os.path.join(RESULTS_DIR, "cadence_check_tabby.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n[SAVED] {out}")

    if not keep_raw:
        for p in paths:
            if os.path.exists(p):
                os.remove(p)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep-raw", action="store_true", help="Keep the raw cadence files on E:")
    main(ap.parse_args().keep_raw)
