"""
Full-cadence test for Stage 1 candidates
========================================
Stage 1 scores each target from ONE ON scan vs ONE OFF scan. run_cadence_check() takes
every scan of the target's ON/OFF/ON/OFF[/ON/OFF] cadence (targets_catalog.py) and asks,
for each candidate: is the signal present in every ON scan at the frequency its drift
rate predicts, and absent from every OFF scan? That is the standard Breakthrough Listen
test. Each scan is summed along the candidate's drift track (de-Doppler), so a drifting
signal is measured as strongly as Stage 1 measured it.

Verdicts (weirdness_engine.cadence_verdict): PASSES / ONE-OFF / PARTIAL / RFI, plus
NOT-RECOVERED (the check could not see the signal even in the scan Stage 1 scored) and
UNTESTED (the target has no OFF scan).

Negative controls: the strongest carrier in OFF_1, plus any "known_rfi" listed in the
catalog. Each must come back RFI; if not, the check is broken for that target.

run_survey.py calls run_cadence_check() for every target. Standalone, this script
re-checks targets from an existing survey_report.json:
    python cadence_check.py                       # every target
    python cadence_check.py tabbys_star_sband     # one target
    python cadence_check.py --keep-raw            # keep the raw cadence files on E:
"""

import argparse
import json
import os

from targets_catalog import STAGE1_CADENCES
from weirdness_engine import cadence_signal, cadence_test_signals, load_spectrogram_fast

SCAN_KEYS = ("label", "role")


def _loader(paths: list[str]):
    def load(i: int):
        print(f"    [CADENCE] scan {i + 1}/{len(paths)}: {os.path.basename(paths[i])}")
        return load_spectrogram_fast(paths[i])
    return load


def run_cadence_check(cadence: dict, summary: dict, scan_paths: list[str], method: str = "dedoppler") -> dict:
    """
    cadence: a STAGE1_CADENCES entry. summary: the Stage 1 result for it (candidates with
    peak_freq_mhz / drift_rate_hz_s / t_ref_mjd, and negative_control). scan_paths: local
    files for cadence["scans"], same order. Adds cadence_verdict / cadence_detail /
    cadence_scans to every candidate in place and returns the cadence-level result.
    """
    scans = cadence["scans"]
    roles = [s["role"] for s in scans]
    controls = []
    if summary.get("negative_control"):
        controls.append(dict(summary["negative_control"]))
    for rfi in cadence.get("known_rfi", []):
        controls.append({"label": f"control: known RFI {rfi['peak_freq_mhz']:.4f} MHz",
                         "t_ref_mjd": summary["header"]["tstart_mjd"], **rfi})

    signals = [cadence_signal(c) for c in summary["candidates"]] + controls
    tested = cadence_test_signals(_loader(scan_paths), roles, signals, method=method)

    for cand, res in zip(summary["candidates"], tested):
        for row in res["cadence_scans"]:
            row["label"] = scans[row["scan"]]["label"]
        cand["cadence_verdict"] = res["cadence_verdict"]
        cand["cadence_detail"] = res["cadence_detail"]
        cand["cadence_scans"] = res["cadence_scans"]
        if "drift_refined_from" in res:  # Stage 1 drift was at its bank edge; see refine_bank_edge_drift
            cand["cadence_drift_refined"] = {
                "from": res["drift_refined_from"],
                "to": {k: res[k] for k in ("drift_bins", "drift_rate_hz_s", "peak_freq_mhz")},
            }
            cand["cadence_detail"] += (f", drift refined {res['drift_refined_from']['drift_bins']:+d}"
                                       f" -> {res['drift_bins']:+d} bins")
    control_results = tested[len(summary["candidates"]):]
    for res in control_results:
        for row in res["cadence_scans"]:
            row["label"] = scans[row["scan"]]["label"]
        res["passed"] = res["cadence_verdict"] == "RFI"

    counts = {}
    for cand in summary["candidates"]:
        counts[cand["cadence_verdict"]] = counts.get(cand["cadence_verdict"], 0) + 1
    return {
        "cadence": cadence["cadence"],
        "method": method,
        "scans": [{k: s[k] for k in SCAN_KEYS} | {"file": os.path.basename(p)} for s, p in zip(scans, scan_paths)],
        "verdict_counts": counts,
        "negative_controls": control_results,
        "negative_controls_passed": all(c["passed"] for c in control_results) if control_results else None,
    }


def print_cadence_result(summary: dict, result: dict) -> None:
    for i, cand in enumerate(summary["candidates"], 1):
        snrs = " ".join(f"{r['role']}:{'-' if r['snr'] is None else r['snr']}" for r in cand["cadence_scans"])
        print(f"    Rank #{i} {cand['peak_freq_mhz']:.6f} MHz -> {cand['cadence_verdict']:13s} ({cand['cadence_detail']})  {snrs}")
    for c in result["negative_controls"]:
        snrs = " ".join(f"{r['role']}:{'-' if r['snr'] is None else r['snr']}" for r in c["cadence_scans"])
        print(f"    {c['label']} {c['peak_freq_mhz']:.6f} MHz -> {c['cadence_verdict']} "
              f"[{'OK' if c['passed'] else 'CONTROL FAILED'}]  {snrs}")


def main(target_ids: list[str], keep_raw: bool) -> None:
    from run_survey import RESULTS_DIR, STAGING_RAW_DIR, download_file_streaming, ensure_dirs

    ensure_dirs()
    report_path = os.path.join(RESULTS_DIR, "survey_report.json")
    report = json.load(open(report_path, encoding="utf-8"))
    catalog = {c["cadence_id"]: c for c in STAGE1_CADENCES}
    for summary in report["cadences"]:
        cid = summary["cadence_id"]
        if target_ids and cid not in target_ids:
            continue
        cad = catalog[cid]
        print(f"\n=== {summary['target_name']} ({cad['cadence']}, {len(cad['scans'])} scans) ===")
        paths = [download_file_streaming(s["url"], STAGING_RAW_DIR, timeout=300) for s in cad["scans"]]
        try:
            summary["cadence_check"] = run_cadence_check(cad, summary, paths)
            print_cadence_result(summary, summary["cadence_check"])
        finally:
            if not keep_raw:
                for p in paths:
                    if os.path.exists(p):
                        os.remove(p)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n[SAVED] verdicts written into {report_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="*", help="cadence_id(s) to check (default: all in survey_report.json)")
    ap.add_argument("--keep-raw", action="store_true", help="Keep the raw cadence files on E:")
    args = ap.parse_args()
    main(args.targets, args.keep_raw)
