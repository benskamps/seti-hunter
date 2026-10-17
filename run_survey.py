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
    CADENCE_PRESENT_SNR,
    OFF_DETECTION_SNR,
    assess_cadence,
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


# Dashboard badge per cadence verdict (weirdness_engine.cadence_verdict). Only PASSES is green.
VERDICT_BADGES = {
    "PASSES": ("#10b981", "PASSES CADENCE"),
    "ONE-OFF": ("#f97316", "ONE-OFF (ON_1 ONLY)"),
    "PARTIAL": ("#eab308", "PARTIAL"),
    "RFI": ("#f43f5e", "RFI (IN AN OFF SCAN)"),
    "NOT-RECOVERED": ("#94a3b8", "NOT RECOVERED BY CADENCE CHECK"),
    "UNTESTED": ("#94a3b8", "UNTESTED (NO OFF SCAN)"),
}


def scan_cell_html(row: dict) -> str:
    """One cell of a candidate's per-scan strip: role and drift-aligned SNR, lit if present."""
    snr = "&ndash;" if row["snr"] is None else f"{row['snr']:.1f}"
    classes = "scan-cell" + (" scan-hit" if row["present"] else "") + (" scan-off" if row["role"] == "OFF" else "")
    title = f"{row['label']}: peak offset {row['offset_ch']} ch, searched +/-{row['search_chans']} ch"
    return f'<span class="{classes}" title="{title}">{row["role"]} {snr}</span>'


def generate_html_dashboard(survey_report: dict, out_html_path: str):
    """Generates an interactive standalone HTML dashboard of all SETI weirdness findings."""
    bench = survey_report["benchmark"]
    cadences = survey_report["cadences"]
    total_chans = sum(c["n_channels_evaluated"] for c in cadences)
    total_tiles = sum(c["n_tiles_evaluated"] for c in cadences)
    total_mb = sum(c["raw_bytes_processed_mb"] for c in cadences)

    # Flatten all candidates across all targets and sort by total weirdness score
    all_cands = []
    for c in cadences:
        for cand in c["candidates"]:
            item = dict(cand)
            item["target_name"] = c["target_name"]
            item["category"] = c["category"]
            item["cadence_id"] = c["cadence_id"]
            all_cands.append(item)
    all_cands.sort(key=lambda x: x["total_weirdness_score"], reverse=True)

    cards_html = []
    for rank, cand in enumerate(all_cands, 1):
        verdict = cand.get("cadence_verdict", "UNTESTED")
        badge_color, badge_label = VERDICT_BADGES[verdict]
        badge_text = f"{badge_label} &middot; {cand.get('cadence_detail', 'no cadence check')}"
        scan_cells = "".join(scan_cell_html(r) for r in cand.get("cadence_scans", []))
        cards_html.append(f"""
        <div class="card" data-verdict="{verdict}" data-target="{cand['cadence_id']}">
            <div class="card-header">
                <div>
                    <span class="rank-badge">#{rank}</span>
                    <span class="target-title">{cand['target_name']}</span>
                    <span class="category-pill">{cand['category']}</span>
                </div>
                <div>
                    <span class="status-badge" style="background:{badge_color}22;color:{badge_color};border:1px solid {badge_color};">
                        {badge_text}
                    </span>
                    <span class="score-pill">Weirdness: {cand['total_weirdness_score']:.1f} &sigma;</span>
                </div>
            </div>
            <div class="metrics-bar">
                <div class="metric"><span>Frequency:</span> <strong>{cand['peak_freq_mhz']:.6f} MHz</strong></div>
                <div class="metric"><span>Classification:</span> <strong style="color:#fbbf24">{cand['classification']}</strong></div>
                <div class="metric"><span>De-Doppler SNR:</span> <strong>{cand['drift_snr']:.1f}</strong> ({cand['drift_rate_hz_s']:+.2f} Hz/s)</div>
                <div class="metric"><span>ON/OFF Ratio:</span> <strong>{cand['on_off_ratio']:.2f}x</strong> (OFF SNR: {cand['off_peak_snr']:.1f})</div>
                <div class="metric"><span>5-Axis Z-Profile:</span>
                    <code>Drift:{cand['z_drift']:.1f} | Burst:{cand['z_burst']:.1f} | Curve:{cand['z_curvature']:.1f} | Morph:{cand['z_morphology']:.1f} | Manifold:{cand['z_manifold']:.1f}</code>
                </div>
            </div>
            <div class="scan-strip"><span class="scan-strip-label">Cadence, drift-aligned SNR per scan (lit = &ge; {CADENCE_PRESENT_SNR:.0f}):</span>{scan_cells or '<em>no cadence check</em>'}</div>
            <div class="plot-container">
                <img src="data:image/png;base64,{cand['plot_b64']}" alt="Waterfall {cand['peak_freq_mhz']} MHz" />
            </div>
        </div>
        """)

    target_rows = []
    controls_total = controls_ok = 0
    for c in cadences:
        chk = c.get("cadence_check", {})
        verdicts = ", ".join(f"{n} {v}" for v, n in sorted(chk.get("verdict_counts", {}).items())) or "&ndash;"
        ctrl = chk.get("negative_controls", [])
        controls_total += len(ctrl)
        controls_ok += sum(x["passed"] for x in ctrl)
        if chk.get("error"):
            ctrl_html = f'<span style="color:#f43f5e">check failed: {chk["error"]}</span>'
        elif not ctrl:
            ctrl_html = '<span style="color:#94a3b8">none (no OFF scan)</span>'
        else:
            ctrl_html = "<br>".join(
                f'<span style="color:{"#34d399" if x["passed"] else "#f43f5e"}">{x["peak_freq_mhz"]:.4f} MHz &rarr; '
                f'{x["cadence_verdict"]} ({x["cadence_detail"]})</span>' for x in ctrl
            )
        target_rows.append(f"""
        <tr>
            <td><strong>{c['target_name']}</strong><br><small style="color:#94a3b8">{c['category']}</small></td>
            <td>{c['header']['fch1_mhz']:.2f} MHz<br><small>{c['header']['bandwidth_mhz']:.1f} MHz BW</small></td>
            <td><strong>{chk.get('cadence', '?')}</strong><br><small>{len(chk.get('scans', []))} scans</small></td>
            <td>{c['n_channels_evaluated']:,}<br><small>({c['n_tiles_evaluated']:,} tiles)</small></td>
            <td>{c['raw_bytes_processed_mb']:.1f} MB<br><small style="color:#34d399">Purged after scan</small></td>
            <td><strong style="color:#fbbf24">{c['max_weirdness_score']:.1f} &sigma;</strong></td>
            <td>{verdicts}</td>
            <td><small>{ctrl_html}</small></td>
        </tr>
        """)
    cad_bench = survey_report.get("cadence_benchmark", {"passed": False, "checks": {}})
    n_checks = len(cad_bench["checks"])
    n_checks_ok = sum(x["ok"] for x in cad_bench["checks"].values())
    filter_buttons = "".join(
        f'<button class="btn" onclick="filterCards(\'{v}\', this)">{v} '
        f'({sum(1 for x in all_cands if x.get("cadence_verdict", "UNTESTED") == v)})</button>'
        for v in VERDICT_BADGES
        if any(x.get("cadence_verdict", "UNTESTED") == v for x in all_cands)
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SETI Weirdness & Anomaly Observatory</title>
<style>
    body {{
        background: #070a12;
        color: #e2e8f0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        margin: 0;
        padding: 24px 36px;
    }}
    h1 {{ margin: 0 0 6px 0; font-size: 26px; color: #f8fafc; }}
    .subtitle {{ color: #94a3b8; font-size: 14px; margin-bottom: 22px; }}
    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 14px;
        margin-bottom: 24px;
    }}
    .kpi {{
        background: #111827;
        border: 1px solid #1e293b;
        border-radius: 10px;
        padding: 14px 18px;
    }}
    .kpi-label {{ color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }}
    .kpi-val {{ font-size: 24px; font-weight: 700; color: #38bdf8; margin-top: 4px; }}
    table {{
        width: 100%;
        border-collapse: collapse;
        background: #111827;
        border-radius: 10px;
        overflow: hidden;
        margin-bottom: 28px;
        border: 1px solid #1e293b;
    }}
    th, td {{ padding: 11px 14px; text-align: left; border-bottom: 1px solid #1e293b; font-size: 13.5px; }}
    th {{ background: #1e293b; color: #cbd5e1; font-weight: 600; }}
    .filter-bar {{
        display: flex;
        gap: 10px;
        margin-bottom: 18px;
        flex-wrap: wrap;
    }}
    .btn {{
        background: #1e293b;
        color: #e2e8f0;
        border: 1px solid #334155;
        padding: 8px 14px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
    }}
    .btn.active {{ background: #0284c7; border-color: #38bdf8; color: #fff; font-weight: 600; }}
    .card {{
        background: #111827;
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    }}
    .card-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
        margin-bottom: 12px;
    }}
    .rank-badge {{
        background: #38bdf8;
        color: #0f172a;
        font-weight: 800;
        padding: 3px 9px;
        border-radius: 6px;
        margin-right: 8px;
    }}
    .target-title {{ font-size: 17px; font-weight: 700; color: #f8fafc; margin-right: 10px; }}
    .category-pill {{
        background: #1e293b;
        color: #94a3b8;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 12px;
    }}
    .status-badge {{
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 11.5px;
        font-weight: 700;
        margin-right: 8px;
    }}
    .score-pill {{
        background: #fbbf2422;
        color: #fbbf24;
        border: 1px solid #fbbf24;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 13px;
    }}
    .metrics-bar {{
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        background: #0b0f19;
        padding: 10px 14px;
        border-radius: 8px;
        margin-bottom: 12px;
        font-size: 13px;
        border: 1px solid #1e293b;
    }}
    .metric span {{ color: #94a3b8; }}
    .scan-strip {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 12px; font-size: 12.5px; }}
    .scan-strip-label {{ color: #94a3b8; margin-right: 4px; }}
    .scan-cell {{
        font-family: ui-monospace, Consolas, monospace;
        padding: 3px 8px;
        border-radius: 5px;
        border: 1px solid #334155;
        color: #94a3b8;
    }}
    .scan-cell.scan-hit {{ background: #38bdf833; border-color: #38bdf8; color: #e0f2fe; font-weight: 700; }}
    .scan-cell.scan-off.scan-hit {{ background: #f43f5e33; border-color: #f43f5e; color: #ffe4e6; }}
    .plot-container img {{ width: 100%; border-radius: 8px; border: 1px solid #1e293b; }}
</style>
</head>
<body>
    <h1>SETI Weirdness & Technosignature Observatory</h1>
    <div class="subtitle">
        Breakthrough Listen Open Data Archive &bull; 5-Axis Unsupervised Anomaly Scorer on the first ON/OFF pair, then every candidate tested across the full ON/OFF cadence (badge = cadence verdict) &bull; Rolling Staging Buffer on <code>E:\\seti_staging</code>
    </div>

    <div class="kpi-grid">
        <div class="kpi">
            <div class="kpi-label">Total Channels Assessed</div>
            <div class="kpi-val">{total_chans:,}</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">Time-Frequency Tiles</div>
            <div class="kpi-val">{total_tiles:,}</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">Raw Spectrogram Data Streamed</div>
            <div class="kpi-val">{total_mb:,.1f} MB</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">Synthetic Ground-Truth Check</div>
            <div class="kpi-val" style="color:{'#34d399' if bench['passed'] else '#f43f5e'}">
                {'PASS (4/4 + RFI Veto)' if bench['passed'] else 'FAIL'}
            </div>
        </div>
        <div class="kpi">
            <div class="kpi-label">Synthetic Cadence Check</div>
            <div class="kpi-val" style="color:{'#34d399' if cad_bench['passed'] else '#f43f5e'}">
                {'PASS' if cad_bench['passed'] else 'FAIL'} ({n_checks_ok}/{n_checks})
            </div>
        </div>
        <div class="kpi">
            <div class="kpi-label">Real-Data Negative Controls &rarr; RFI</div>
            <div class="kpi-val" style="color:{'#34d399' if controls_ok == controls_total else '#f43f5e'}">
                {controls_ok}/{controls_total}
            </div>
        </div>
    </div>

    <h2>Target Cadence Summary</h2>
    <table>
        <thead>
            <tr>
                <th>Target System</th>
                <th>Band &amp; Bandwidth</th>
                <th>Cadence</th>
                <th>Channels Assessed</th>
                <th>Streamed &amp; Purged</th>
                <th>Peak Weirdness</th>
                <th>Candidate Verdicts</th>
                <th>Negative Controls (must be RFI)</th>
            </tr>
        </thead>
        <tbody>
            {''.join(target_rows)}
        </tbody>
    </table>

    <h2>Top Ranked Weirdness Candidates ({len(all_cands)} Cutouts)</h2>
    <div class="filter-bar">
        <button class="btn active" onclick="filterCards('all', this)">All Candidates ({len(all_cands)})</button>
        {filter_buttons}
    </div>

    <div id="cards-list">
        {''.join(cards_html)}
    </div>

    <script>
    function filterCards(mode, btn) {{
        document.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        document.querySelectorAll('.card').forEach(c => {{
            if (mode === 'all') c.style.display = 'block';
            else c.style.display = (c.dataset.verdict === mode) ? 'block' : 'none';
        }});
    }}
    </script>
</body>
</html>
"""
    with open(out_html_path, "w", encoding="utf-8") as f:
        f.write(html)


def run_stage1_survey(keep_raw: bool = False, top_k_per_cadence: int = 5):
    ensure_dirs()
    print("=================================================================")
    print(" STEP 0: Running Synthetic Ground-Truth Verification Benchmark")
    print("=================================================================")
    bench = run_synthetic_verification_benchmark()
    print(f"  Benchmark Passed: {bench['passed']} | Recovered Tiles: {bench['recovered_on_targets']} | RFI Tile 210 Vetoed Score: {bench['rfi_tile_210_score']}")
    cadence_bench = run_synthetic_cadence_benchmark()
    print(f"  Cadence Benchmark Passed: {cadence_bench['passed']}")
    for chk_name, chk in cadence_bench["checks"].items():
        print(f"    {chk_name}: expected {chk['expected']}, got {chk['got']}")
    if not (bench["passed"] and cadence_bench["passed"]):
        print("  [WARNING] A synthetic benchmark FAILED; treat every verdict below as untrusted.")

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
                c_copy["plot_b64"] = b64
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

    # Save JSON report (without base64 images so JSON stays lightweight and readable)
    json_report = json.loads(json.dumps(full_report))
    for c in json_report["cadences"]:
        for cand in c["candidates"]:
            cand.pop("plot_b64", None)

    json_path = os.path.join(RESULTS_DIR, "survey_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2)
    shutil.copy2(json_path, os.path.join(os.path.dirname(__file__), "survey_report.json"))

    html_path = os.path.join(RESULTS_DIR, "dashboard.html")
    generate_html_dashboard(full_report, html_path)
    local_html = os.path.join(os.path.dirname(__file__), "dashboard.html")
    shutil.copy2(html_path, local_html)
    print(f"\n[COMPLETE] Survey report saved to {json_path}")
    print(f"[COMPLETE] Interactive HTML Observatory Dashboard saved to {html_path} and {local_html}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SETI Weirdness Rolling-Buffer Survey")
    parser.add_argument("--keep-raw", action="store_true", help="Do not delete raw .h5/.fil files after scoring")
    parser.add_argument("--top-k", type=int, default=4, help="Top candidates to extract per target cadence")
    args = parser.parse_args()
    run_stage1_survey(keep_raw=args.keep_raw, top_k_per_cadence=args.top_k)
