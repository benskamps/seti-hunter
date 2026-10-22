"""
SETI Rolling-Buffer Survey & Observatory Dashboard Generator
============================================================
Streams Breakthrough Listen cadences to E:\\seti_staging\\raw, runs the 5-axis
Weirdness & ON/OFF Veto Engine across millions of channels on the first ON/OFF pair,
then tests every candidate across the target's full ON/OFF cadence (cadence_check.py),
renders side-by-side ON vs OFF waterfall spectrograms, purges the raw files to keep
disk footprint near zero, and builds an interactive HTML dashboard whose badges are
the cadence verdicts.
"""

import os
import sys
import json
import time
import base64
import shutil
import argparse
import requests
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cadence_check import print_cadence_result, run_cadence_check
from targets_catalog import STAGE1_CADENCES, STAGE2_FINE_RES_QUEUE
from weirdness_engine import (
    OFF_DETECTION_SNR,
    assess_cadence,
    gate_verdicts,
    run_cadence_edge_case_benchmark,
    run_noise_calibration_benchmark,
    run_synthetic_cadence_benchmark,
    run_synthetic_verification_benchmark,
)

STAGING_RAW_DIR = r"E:\seti_staging\raw"
RESULTS_DIR = r"E:\seti_staging\results"
PLOTS_DIR = os.path.join(RESULTS_DIR, "plots")


def ensure_dirs():
    os.makedirs(STAGING_RAW_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(PLOTS_DIR, exist_ok=True)


def download_file_streaming(url: str, dest_dir: str, timeout: int = 120) -> str:
    """Streams a file from the Breakthrough Listen archive to E:\\seti_staging\\raw."""
    fname = url.split("/")[-1]
    dest_path = os.path.join(dest_dir, fname)
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024 * 100:
        print(f"  [CACHE HIT] {fname} ({os.path.getsize(dest_path)/(1024*1024):.1f} MB)")
        return dest_path

    print(f"  [DOWNLOADING] {fname} from {url} ...")
    t0 = time.time()
    tmp_path = dest_path + ".part"
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        total_bytes = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=4 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
    os.replace(tmp_path, dest_path)
    dt = max(time.time() - t0, 0.01)
    mb = downloaded / (1024 * 1024)
    print(f"  [DONE] {fname}: {mb:.1f} MB in {dt:.1f}s ({mb/dt:.1f} MB/s)")
    return dest_path


def render_candidate_plot(
    cadence_id: str,
    target_name: str,
    cand_rank: int,
    cand: dict,
    header: dict,
    out_dir: str,
) -> tuple[str, str]:
    """
    Renders a 3-panel diagnostic figure for a weirdness candidate:
      - Left: ON-Target (A) Normalized Time-Frequency Waterfall
      - Middle: OFF-Target (B) Reference Time-Frequency Waterfall (same MHz window)
      - Right: Integrated Spectral Power Profile (ON vs OFF) + 5-Axis Weirdness Radar Bars
    Returns (filepath, base64_png_data).
    """
    on_cut = cand["on_cutout"]
    off_cut = cand["off_cutout"]
    freqs = cand["tile_freqs_mhz"]
    T, W = on_cut.shape
    dur_s = header.get("total_duration_s", T * 18.0)

    # Convert frequency axis to kHz offset from tile start
    f0_mhz = freqs[0]
    df_khz = (freqs - f0_mhz) * 1e3

    fig = plt.figure(figsize=(13.5, 4.2), dpi=120, facecolor="#0b0f19")
    gs = fig.add_gridspec(1, 3, width_ratios=[1.25, 1.25, 1.1], wspace=0.26)

    vmin, vmax = -1.5, max(8.0, min(float(np.percentile(on_cut, 99.8)), 25.0))

    # Panel 1: ON-Target Waterfall
    ax1 = fig.add_subplot(gs[0, 0], facecolor="#0b0f19")
    im1 = ax1.imshow(
        on_cut,
        aspect="auto",
        origin="lower",
        extent=[df_khz[0], df_khz[-1], 0, dur_s],
        cmap="inferno",
        vmin=vmin,
        vmax=vmax,
    )
    ax1.set_title(
        f"ON-TARGET: {target_name[:26]}\nPeak @ {cand['peak_freq_mhz']:.6f} MHz",
        color="#38bdf8",
        fontsize=10,
        fontweight="bold",
    )
    ax1.set_xlabel(f"Offset (kHz) from {f0_mhz:.4f} MHz", color="#cbd5e1", fontsize=8.5)
    ax1.set_ylabel("Elapsed Time (s)", color="#cbd5e1", fontsize=8.5)
    ax1.tick_params(colors="#94a3b8", labelsize=8)

    # Panel 2: OFF-Target Reference Waterfall
    ax2 = fig.add_subplot(gs[0, 1], facecolor="#0b0f19")
    im2 = ax2.imshow(
        off_cut,
        aspect="auto",
        origin="lower",
        extent=[df_khz[0], df_khz[-1], 0, dur_s],
        cmap="inferno",
        vmin=vmin,
        vmax=vmax,
    )
    ax2.set_title(
        f"OFF-TARGET VETO (single OFF scan)\nON/OFF Ratio: {cand['on_off_ratio']:.2f}x | OFF SNR: {cand['off_peak_snr']:.1f}",
        color="#f43f5e" if cand["off_peak_snr"] > OFF_DETECTION_SNR else "#34d399",
        fontsize=10,
        fontweight="bold",
    )
    ax2.set_xlabel(f"Offset (kHz) from {f0_mhz:.4f} MHz", color="#cbd5e1", fontsize=8.5)
    ax2.set_ylabel("Elapsed Time (s)", color="#cbd5e1", fontsize=8.5)
    ax2.tick_params(colors="#94a3b8", labelsize=8)

    # Panel 3: Integrated Spectral Profile (ON vs OFF)
    ax3 = fig.add_subplot(gs[0, 2], facecolor="#111827")
    on_prof = np.sum(on_cut, axis=0) / np.sqrt(max(T, 1))
    off_prof = np.sum(off_cut, axis=0) / np.sqrt(max(off_cut.shape[0], 1))
    ax3.plot(df_khz, on_prof, color="#38bdf8", lw=1.3, label="ON-Target (A)")
    ax3.plot(df_khz, off_prof, color="#f43f5e", lw=1.0, alpha=0.75, label="OFF-Target (B)")
    ax3.axhline(0, color="#475569", lw=0.7, ls="--")
    ax3.set_title(
        f"Weirdness: {cand['total_weirdness_score']:.1f} | Drift: {cand['drift_rate_hz_s']:+.2f} Hz/s\n{cand['classification'][:38]}",
        color="#fbbf24",
        fontsize=9.5,
        fontweight="bold",
    )
    ax3.set_xlabel("Frequency Offset (kHz)", color="#cbd5e1", fontsize=8.5)
    ax3.set_ylabel("Integrated Zero-Drift Z-SNR", color="#cbd5e1", fontsize=8.5)
    ax3.tick_params(colors="#94a3b8", labelsize=8)
    leg = ax3.legend(loc="upper right", facecolor="#1e293b", edgecolor="#334155", fontsize=7.5)
    for text in leg.get_texts():
        text.set_color("#e2e8f0")

    for ax in (ax1, ax2, ax3):
        for spine in ax.spines.values():
            spine.set_color("#334155")

    fig.subplots_adjust(left=0.06, right=0.98, bottom=0.16, top=0.84)
    plot_fname = f"{cadence_id}_rank{cand_rank:02d}_{cand['peak_freq_mhz']:.4f}MHz.png"
    plot_path = os.path.join(out_dir, plot_fname)
    fig.savefig(plot_path, facecolor=fig.get_facecolor())
    plt.close(fig)

    with open(plot_path, "rb") as bf:
        b64 = base64.b64encode(bf.read()).decode("ascii")
    return plot_path, b64


def run_stage1_survey(keep_raw: bool = False, top_k_per_cadence: int = 5):
    ensure_dirs()
    print("=================================================================")
    print(" STEP 0: Running Synthetic Ground-Truth Verification Benchmark")
    print("=================================================================")
    bench = run_synthetic_verification_benchmark()
    print(f"  Benchmark Passed: {bench['passed']} | Recovered Tiles: {bench['recovered_on_targets']} | RFI Tile 210 Vetoed Score: {bench['rfi_tile_210_score']}")
    noise_bench = run_noise_calibration_benchmark()
    print(f"  Noise Calibration Benchmark Passed: {noise_bench['passed']} | false alarms in structured noise: "
          f"{noise_bench['structured_false_alarm_frac']:.2%} | injected carrier SNR {noise_bench['injected_tile_77_snr']}")
    bench["noise_calibration"] = noise_bench
    bench["passed_stage1_only"] = bench["passed"]
    bench["passed"] = bench["passed"] and noise_bench["passed"]
    cadence_bench = run_synthetic_cadence_benchmark()
    print(f"  Cadence Benchmark Passed: {cadence_bench['passed']}")
    for chk_name, chk in cadence_bench["checks"].items():
        print(f"    {chk_name}: expected {chk['expected']}, got {chk['got']}")
    edge_bench = run_cadence_edge_case_benchmark()
    print(f"  Cadence Edge-Case Benchmark Passed: {edge_bench['passed']}")
    for chk_name, chk in edge_bench["checks"].items():
        print(f"    {chk_name}: {'ok' if chk['ok'] else 'FAILED'} ({chk.get('got')})")
    cadence_bench["edge_cases"] = edge_bench
    cadence_bench["passed_main_only"] = cadence_bench["passed"]
    cadence_bench["passed"] = cadence_bench["passed"] and edge_bench["passed"]
    benchmarks_passed = bench["passed"] and cadence_bench["passed"]
    if not benchmarks_passed:
        print("  [WARNING] A synthetic benchmark FAILED; every PASSES verdict below is withheld (UNTESTED).")

    cadence_reports = []
    for cad in STAGE1_CADENCES:
        cid = cad["cadence_id"]
        name = cad["name"]
        print("\n=================================================================")
        print(f" TARGET: {name} [{cad['category']}]")
        print("=================================================================")

        scans = cad["scans"]
        roles = [s["role"] for s in scans]
        on1 = roles.index("ON")
        off1 = roles.index("OFF") if "OFF" in roles else None
        print(f"  Cadence: {cad['cadence']} ({len(scans)} scans: {' '.join(roles)})")

        scan_paths = [None] * len(scans)
        try:
            scan_paths[on1] = download_file_streaming(scans[on1]["url"], STAGING_RAW_DIR)
            off_path = None
            if off1 is not None:
                off_path = scan_paths[off1] = download_file_streaming(scans[off1]["url"], STAGING_RAW_DIR)

            off_label = scans[off1]["label"] if off1 is not None else "no OFF scan"
            print(f"  [ASSESSING] Running 5-Axis Weirdness + ON/OFF Veto on {name} ({scans[on1]['label']} vs {off_label}) ...")
            summary = assess_cadence(scan_paths[on1], off_path, tile_width=256, top_k=top_k_per_cadence)
            summary["cadence_id"] = cid
            summary["target_name"] = name
            summary["category"] = cad["category"]
            summary["description"] = cad["description"]

            # Render waterfall plots for each candidate and strip raw numpy arrays for JSON
            clean_candidates = []
            for rank, cand in enumerate(summary["candidates"], 1):
                plot_path, b64 = render_candidate_plot(cid, name, rank, cand, summary["header"], PLOTS_DIR)
                c_copy = {k: v for k, v in cand.items() if k not in ("on_cutout", "off_cutout", "tile_freqs_mhz")}
                c_copy["plot_path"] = plot_path
                clean_candidates.append(c_copy)
                print(
                    f"    Rank #{rank}: {cand['peak_freq_mhz']:.6f} MHz | Weirdness={cand['total_weirdness_score']:.1f} | "
                    f"Drift={cand['drift_rate_hz_s']:+.2f} Hz/s (SNR {cand['drift_snr']:.1f}) | "
                    f"ON/OFF={cand['on_off_ratio']:.2f}x | {cand['classification']}"
                )
            summary["candidates"] = clean_candidates

            # Full-cadence test: every candidate, every scan of the cadence. If it cannot run,
            # the candidates stay UNTESTED rather than keeping their single-pair label.
            try:
                for i, s in enumerate(scans):
                    if scan_paths[i] is None:
                        scan_paths[i] = download_file_streaming(s["url"], STAGING_RAW_DIR, timeout=300)
                print(f"  [CADENCE CHECK] Testing {len(clean_candidates)} candidates across all {len(scans)} scans ...")
                summary["cadence_check"] = run_cadence_check(cad, summary, scan_paths)
                gate_verdicts(clean_candidates, summary["cadence_check"]["negative_controls_passed"], benchmarks_passed)
                print_cadence_result(summary, summary["cadence_check"])
            except Exception as e:
                print(f"  [ERROR] Cadence check failed for {name}: {e}")
                summary["cadence_check"] = {"cadence": cad["cadence"], "error": str(e), "negative_controls": [],
                                            "negative_controls_passed": None, "verdict_counts": {}}
                for c in clean_candidates:
                    c["cadence_verdict"], c["cadence_detail"], c["cadence_scans"] = "UNTESTED", f"cadence check failed: {e}", []
            summary["raw_bytes_processed_mb"] = round(
                sum(os.path.getsize(p) for p in scan_paths if p and os.path.exists(p)) / (1024 * 1024), 2
            )
            cadence_reports.append(summary)

        except Exception as e:
            print(f"  [ERROR] Failed processing {name}: {e}")
        finally:
            if not keep_raw:
                for p in scan_paths:
                    if p and os.path.exists(p):
                        os.remove(p)
                        print(f"  [PURGED RAW] {os.path.basename(p)} removed from E:\\seti_staging\\raw")

    full_report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "benchmark": bench,
        "cadence_benchmark": cadence_bench,
        "cadences": cadence_reports,
    }

    json_report = json.loads(json.dumps(full_report))

    json_path = os.path.join(RESULTS_DIR, "survey_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2)
    shutil.copy2(json_path, os.path.join(os.path.dirname(__file__), "survey_report.json"))

    print(f"\n[COMPLETE] Survey report saved to {json_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SETI Weirdness Rolling-Buffer Survey")
    parser.add_argument("--keep-raw", action="store_true", help="Do not delete raw .h5/.fil files after scoring")
    parser.add_argument("--top-k", type=int, default=4, help="Top candidates to extract per target cadence")
    args = parser.parse_args()
    run_stage1_survey(keep_raw=args.keep_raw, top_k_per_cadence=args.top_k)
