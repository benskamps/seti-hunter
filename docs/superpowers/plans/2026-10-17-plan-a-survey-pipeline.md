# Plan A: Whole-Sample Survey Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn seti-hunter from a six-target pilot into a resumable whole-sample survey: sample → archive index → cadences → per-shape detection → five-rung ladder → blind plants → frozen full run.

**Architecture:**
- New code lives in a `survey/` package with pytest tests in `tests/`. It wraps the existing engine (`weirdness_engine.py`, `cadence_check.py`, `run_survey.py`) instead of rewriting it.
- A SQLite state file is the single source of truth for the run. Plan B reads it read-only to build the public snapshot.
- Thresholds live only in `ladder.yaml`, and a git tag freezes them.

**Tech Stack:**
- Python in the existing venv `E:\seti_staging\venv`: numpy, h5py, blimpy (present); add pytest, PyYAML, setigen.
- SQLite (stdlib `sqlite3`), and Windows Task Scheduler for the run.

**Spec:** `docs/superpowers/specs/2026-10-17-whole-sample-survey-design.md` (approved 2026-10-17). Read it before any task. §-numbers below refer to it.

**Companion plans:**
- Plan B (`2026-10-17-plan-b-live-dashboard.md`) consumes this plan's SQLite schema (Task 8).
- Plan C (unblinding, limits, paper) is written after the full run completes, because its inputs are the run's results.

## Global Constraints

- **Interpreter:** `E:/seti_staging/venv/Scripts/python.exe` for every command. Tests run with `-m pytest`.
- **Raw files:** downloaded to `E:\seti_staging\raw` and purged after scoring. Keep only cutouts and per-signal features.
- **Copy rule:** signals are **eliminated**, never "killed" (also in code comments, log lines and column values).
- **Verdict vocabulary** (exact strings, extending `CADENCE_VERDICTS`): `ELIMINATED`, `PENDING_R5`, `SURVIVOR`, `UNTESTED`, `NOT-RECOVERED`, `INCOMPLETE`.
- **Rung numbers** are ints 1–5:
  1. present in an OFF scan
  2. missing from an ON scan
  3. instrument artifact
  4. known human-transmitter band
  5. seen around another star
- **Rung ③ is the instrument artifact check, never zero-drift** (spec §5). Drift coverage: 0 to the drift bank's edge (≈ ±95 Hz/s).
- **Committed shapes** (exact ids): `wide_drift`, `chirp`, `intermittent`, `comb`. The discovery channel id is `weird`.
- **Thresholds, band lists, tolerances and artifact zones** exist only in `ladder.yaml`, never as literals in code.
- **The full run refuses to start** unless `ladder.yaml` matches the commit tagged `ladder-v<N>`.
- **No agents in the run loop.** The runner is a plain script.
- **Commits end with:** `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A truncated or 404 download** (network drop, archive hiccup): the cadence is marked `failed` with a reason and retried at most 3 times, then `parked`. A partial file is never scored. Test in Task 7.
2. **A cadence whose scans have different frequency setups** (different `fch1`/channel counts between ON and OFF): signals are matched by frequency in MHz, never by channel index, or the cadence is marked `incomplete` with a reason. Test in Task 3.
3. **A kill or power loss mid-run:** rerunning the runner resumes and writes no duplicate signals. Signal ids are deterministic (cadence id + shape + tile + scan), and writes are upserts. Test in Task 7.
4. **E: running low on disk:** the runner pauses before downloading when free space < 2× the next cadence's size, records `paused: disk`, and doesn't corrupt state. Test in Task 7.
5. **Editing `ladder.yaml` after the freeze:** the full run refuses with a message naming the mismatching tag. Calibration runs are allowed only with `--calibration`. Test in Task 9.

---

### Task 1: Project scaffolding, sample list and archive index in the repo (M1, part 1)

**Files:**
- Create: `survey/__init__.py`, `survey/sample.py`, `tests/test_sample.py`, `requirements.txt`, `pytest.ini`
- Create: `data/gbt_sample_price2020.csv`, `scripts/build_sample.py`, `scripts/harvest_index.py`, `data/listen2019_tables.txt`
- Copy from the design session's scratchpad (`%TEMP%\claude\...\scratchpad\`): `build_sample.py`, `harvest_index.py`, `dl/tables.txt`, `dl/sample_rows.json`, `archive_index.jsonl`, `archive_targets_done.txt`. If the scratchpad is gone, re-download `http://seti.berkeley.edu/listen2019/listen2019_tables.pdf` and re-run the parse described in spec §4.

**Interfaces:**
- Produces: `survey.sample.Star` (dataclass with `name: str, aliases: list[str], ra_deg: float, dec_deg: float, bands: str` (`"L"`, `"S"` or `"LS"`), `dist_pc: float | None, first_mjd: float`).
- Produces: `survey.sample.load_sample(path: str = "data/gbt_sample_price2020.csv") -> list[Star]`.

- [ ] **Step 1:** Add `requirements.txt` with the versions now installed in the venv for numpy, h5py, blimpy, scikit-learn, matplotlib, pillow, plus `pytest`, `PyYAML`, `setigen` (pin exact versions after install). Add `pytest.ini` with `testpaths = tests`. Install: `E:/seti_staging/venv/Scripts/python.exe -m pip install -r requirements.txt`.
- [ ] **Step 2:** Move the scripts and data into `scripts/` and `data/`. Extend `build_sample.py` to also parse the **distance (pc)** column from the table rows, written as a `dist_pc` CSV column (empty when absent). The header keeps the provenance lines from spec §4. Re-run it: it should print `L=881 S=999 both=747 total=1133`.
- [ ] **Step 3: Write the failing test** `tests/test_sample.py`:

```python
def test_sample_counts_match_design():
    stars = load_sample()
    assert len(stars) == 1133
    assert sum("L" in s.bands for s in stars) == 881
    assert sum("S" in s.bands for s in stars) == 999
    assert sum(s.bands == "LS" for s in stars) == 747

def test_aliases_merged():
    by = {s.name: s for s in load_sample()}
    assert "GJ166" not in by and "GJ166" in by["HIP19849"].aliases
    assert "GJ702A" not in by and "GJ702A" in by["HIP88601"].aliases

def test_distances_parsed_for_most_stars():
    stars = load_sample()
    assert sum(s.dist_pc is not None for s in stars) >= 1000
```

- [ ] **Step 4:** Run `python -m pytest tests/test_sample.py -v`. Expected: FAIL (`load_sample` not defined).
- [ ] **Step 5:** Implement `load_sample` (skip `#` comment lines; `aliases` = `table_names` minus `star`).
- [ ] **Step 6:** Run the test again. Expected: PASS. If the distance test fails, fix the parser; don't lower the bar.
- [ ] **Step 7:** Commit: `git add survey tests data scripts requirements.txt pytest.ini` then `git commit -m "survey: sample list and archive index in the repo"`.

### Task 2: Finish the archive index (M1, part 2)

**Files:**
- Modify: `scripts/harvest_index.py`
- Create: `survey/archive_index.py`, `tests/test_archive_index.py`

**Interfaces:**
- Produces: `survey.archive_index.IndexRow` (dataclass: `target, url, size, center_freq, mjd, ra, decl, file_type`).
- Produces: `survey.archive_index.load_index(path="data/archive_index.jsonl", aliases: dict[str,str] | None = None) -> list[IndexRow]`. Alias names are mapped to canonical star names.
- Produces: `survey.archive_index.midres_rows(rows) -> list[IndexRow]` (URLs ending `.gpuspec.0002.h5`).

- [ ] **Step 1:** Make the harvest resumable and **sample-first**. With `--targets data/gbt_sample_price2020.csv` it fetches the 1,133 stars (and their aliases) before anything else. OFF pointings are discovered in Task 3 and fetched with `--targets-file data/off_targets.txt`. Each finished target is appended to `data/archive_targets_done.txt` with a flush after every target (today it buffers). Run it in the background to completion.
- [ ] **Step 2: Write the failing tests** in `tests/test_archive_index.py`, using a 6-row fixture JSONL written in the test:
  - `test_alias_rows_map_to_canonical_star`: a row with target `GJ166` comes back as `HIP19849`.
  - `test_midres_filter`: `.0000.h5`, `.8.0001.h5` and `.fil` rows are dropped; only `.gpuspec.0002.h5` rows are kept.
  - `test_malformed_line_is_skipped_and_counted`: a non-JSON line is skipped, and `load_index(...).skipped == 1` (return a list subclass with a `skipped` attribute).
- [ ] **Step 3:** Run the tests. Expected: FAIL.
- [ ] **Step 4:** Implement `load_index` and `midres_rows`.
- [ ] **Step 5:** Run the tests. Expected: PASS.
- [ ] **Step 6:** Commit.

### Task 3: Assemble cadences, and measure the real data volume (M1, part 3)

**Files:**
- Create: `survey/cadences.py`, `tests/test_cadences.py`, `scripts/build_cadences.py`, `data/cadences.json`, `data/off_targets.txt`

**Interfaces:**
- Consumes: `load_sample`, `load_index`, `midres_rows`.
- Produces: `survey.cadences.Cadence` (dataclass):
  - `id: str` (e.g. `"HIP12345-L-57802-0011"`)
  - `star: str`, `band: str` (`"L"` or `"S"`)
  - `scans: list[dict]`, where each dict is `{"role": "ON"|"OFF", "label": str, "url": str, "size": int, "mjd": float, "target": str}`
  - `status: str` (`"complete"` or `"incomplete"`), `reason: str`
- Produces: `survey.cadences.assemble(sample, rows) -> list[Cadence]`.
- Produces: `survey.cadences.band_of(center_freq_mhz: float) -> str` (`< 1900` is `"L"`, else `"S"`).

**How to assemble:**
- Group mid-res rows by observing session: the `AGBTxxx_999_NN` path segment plus the `blcNN..` prefix plus the receiver band.
- Order by the trailing scan number (`_0031`).
- A **complete** cadence is 6 consecutive scans alternating A,x,A,x,A,x, where A is the sample star (by canonical name) and each x is a different target. The x targets are OFF pointings.
- Fewer scans, wrong alternation, or mismatched frequency setups are `incomplete`, with the reason.
- One star may have several cadences per band; keep them all.

- [ ] **Step 1: Write the failing tests** in `tests/test_cadences.py`, using in-test fixture rows built from the real Tabby cadence URLs in `targets_catalog.py` (scans 0031–0036):
  - `test_abacad_cadence_is_complete`: 6 rows alternating star/other → one `complete` cadence with roles ON,OFF,ON,OFF,ON,OFF.
  - `test_five_scans_is_incomplete_with_reason`: `reason` contains `"5 of 6 scans"`.
  - `test_mismatched_frequency_setup_is_incomplete`: one OFF row has a different `center_freq` (> 1 MHz apart) → `incomplete`, and `"frequency setup"` is in `reason` (Review Focus 2).
  - `test_band_split`: rows at 1501 MHz and 2251 MHz in the same session become two cadences, L and S.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `band_of` and `assemble`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** `scripts/build_cadences.py` writes `data/cadences.json` and `data/off_targets.txt` (OFF target names not yet in the index). It prints:
  - complete cadences per band
  - stars with ≥1 complete cadence per band
  - incomplete counts by reason
  - **the total bytes of all complete cadences**

  Run the harvest for `off_targets.txt` (Task 2), then rebuild. **Record the printed totals in the spec's §4 "Volume" bullet**, replacing the estimate with "measured".
- [ ] **Step 6:** Commit (cadences.json, off_targets.txt, the spec edit).

### Task 4: `ladder.yaml` and the five rungs (M2)

**Files:**
- Create: `ladder.yaml`, `survey/ladder.py`, `tests/test_ladder.py`

**Interfaces:**
- Consumes: `weirdness_engine.cadence_verdict` (per-scan `present` rows), `weirdness_engine.OFF_DETECTION_SNR`.
- Produces: `survey.ladder.Ladder` (loaded config), `survey.ladder.load_ladder(path="ladder.yaml") -> Ladder`.
- Produces: `survey.ladder.LadderResult` (dataclass: `verdict: str, rung: int | None, reason: str`).
- Produces: `survey.ladder.rungs_1_to_4(signal: dict, scans: list[dict], ladder: Ladder) -> LadderResult`.
  - `signal` has `peak_freq_mhz, drift_rate_hz_s, shape, coarse_chan_offset`; `scans` are rows with `role` and `present`.
  - It returns `ELIMINATED` with the first failing rung, `PENDING_R5` if rungs 1–4 pass, or `UNTESTED` / `NOT-RECOVERED` / `INCOMPLETE` mapped from `cadence_verdict`.
- Produces: `survey.ladder.rung_5_final(pending: list[dict], ladder: Ladder) -> dict[str, LadderResult]`, keyed by signal id. A pending signal is eliminated at rung 5 if any **other** signal (pending or eliminated) from a **different star and a different session** matches within `rung5.freq_tol_khz` and `rung5.drift_tol_hz_s`. Otherwise `SURVIVOR`.

**`ladder.yaml` initial content** (values are starting points, tuned only in Task 6, then frozen):

```yaml
version: 1
rung1: {off_detection_snr: 8.0}
rung3: {coarse_chan_mhz: 2.9296875, dc_zone_fine_chans: 3, edge_zone_fine_chans: 8}
rung4:
  bands_mhz:   # name: [lo, hi]
    gps_l5: [1166.45, 1186.45]
    gps_l2: [1217.60, 1237.60]
    inmarsat: [1525.0, 1559.0]
    gps_l1: [1565.42, 1585.42]
    glonass: [1598.0, 1606.0]
    iridium: [1616.0, 1626.5]
    spacecraft_telemetry: [2200.0, 2290.0]
    wifi_ism: [2400.0, 2483.5]
rung5: {freq_tol_khz: 6.0, drift_tol_hz_s: 10.0}
detectors: {wide_drift: {snr: 10.0}, chirp: {snr: 10.0}, intermittent: {snr: 10.0}, comb: {snr: 10.0}}
weird: {top_k_per_cadence: 5}
```

- [ ] **Step 1: Write the failing tests** in `tests/test_ladder.py`, one per rung plus ordering:
  - `test_rung1_off_presence_eliminates_first`: present in OFF and also in a rung-4 band → rung 1 (order matters).
  - `test_rung2_missing_on_eliminates`: present in ON 1 only → rung 2, reason `"in 1/3 ON"`.
  - `test_rung3_dc_spike_eliminates`: `coarse_chan_offset` within `dc_zone_fine_chans` of centre → rung 3; one channel outside the zone → not rung 3.
  - `test_rung4_iridium_eliminates`: 1617.88 MHz (the real Kepler-992b signal) → rung 4, reason contains `"iridium"`.
  - `test_passes_1_to_4_is_pending_r5`: a clean signal → `PENDING_R5`, never `SURVIVOR` from `rungs_1_to_4`.
  - `test_rung5_cross_star_match_eliminates`: Sgr B2 at 2193.563 MHz vs Tabby's Star's control at 2193.5658 MHz, different session, drift within tolerance → rung 5.
  - `test_rung5_same_star_does_not_count`: a match on the same star (another cadence) does not eliminate.
  - `test_no_threshold_literals_in_code`: read `survey/ladder.py` source and assert none of `8.0`, `2.9296875`, `1616.0` appear (they belong in `ladder.yaml`).
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `load_ladder`, `rungs_1_to_4` and `rung_5_final`. Rung 3 uses `coarse_chan_offset`: the signal's fine-channel offset from its coarse-channel centre, computed by the detector in Task 5.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit.

### Task 5: Per-shape detectors and presence models (M2/M3)

**Files:**
- Create: `survey/detectors.py`, `survey/presence.py`, `tests/test_detectors.py`, `tests/test_presence.py`
- Modify: `weirdness_engine.py` only if a helper must be exposed (no behaviour change; the existing benchmarks must still pass).

**Interfaces:**
- Consumes: `weirdness_engine.normalize_bandpass`, `extract_tile_features`, `compute_dedoppler_snr`, `drift_aligned_snr`, `load_spectrogram_fast`; `Ladder`.
- Produces: `survey.detectors.detect(on: tuple, ladder: Ladder) -> list[dict]`. `on` is `(data, freqs, hdr)`. Each flag dict has:
  - `shape` (one of the four ids or `"weird"`), `tile_idx`, `peak_freq_mhz`, `drift_rate_hz_s`, `snr` (absolute, calibrated)
  - `coarse_chan_offset`, `t_ref_mjd`, `drift_bins`, `ref_span_s`, `ref_foff_hz`
  - `features` (dict of the axis values)
- Produces: `survey.presence.present_in_scan(flag: dict, scan: tuple, ladder: Ladder, dt_s: float) -> dict`, returning `{"present": bool | None, "snr": float, "offset_ch": int}` with shape-aware rules (spec §5):
  - `wide_drift` and `comb`: drift-aligned track, with the window from `cadence_search_chans`.
  - `chirp`: a curvature-bounded fan of tracks.
  - `intermittent`: time-collapsed detection anywhere in the scan.
  - `weird`: drift-aligned if `drift_bins != 0`, otherwise time-collapsed.

**Absolute thresholds:**
- Each shape's statistic is converted to SNR against the tile's robust noise (MAD), as `run_noise_calibration_benchmark` does for drift SNR. That way a planted signal's recovery doesn't depend on how much interference is in the file.
- A tile is flagged for shape S when its S-statistic SNR ≥ `ladder.detectors[S].snr`. The `weird` channel keeps the composite score with per-cadence top-K.

- [ ] **Step 1: Write the failing tests** in `tests/test_detectors.py`, using setigen frames built in the test (Gaussian noise plus one planted signal, mid-res header values `foff = 2.86102294921875 kHz`, `tsamp = 1.073741824 s`, 273 samples):
  - `test_wide_drift_found_at_snr_25`: a 5 kHz-wide carrier drifting 30 Hz/s → exactly one `wide_drift` flag within ±2 channels of truth, `abs(drift - 30) <= 10`.
  - `test_chirp_found`: a quadratic track → a `chirp` flag.
  - `test_intermittent_found`: a carrier on for 3 bursts of 20 s → an `intermittent` flag.
  - `test_comb_found`: 5 carriers spaced 30 kHz → one `comb` flag, not five `wide_drift` flags.
  - `test_pure_noise_flags_nothing_above_threshold`: 20 noise-only frames → 0 committed-shape flags.
  - `test_snr_is_absolute`: the same plant in a frame with ten extra strong RFI carriers keeps its SNR within 15%.
- [ ] **Step 2:** In `tests/test_presence.py`, cover each shape: present in a scan that contains it, absent in one that doesn't, and `None` when the track leaves the band.
- [ ] **Step 3:** Run both test files. Expected: FAIL.
- [ ] **Step 4:** Implement `detect` and `present_in_scan`.
- [ ] **Step 5:** Run both test files, plus the existing benchmarks: `python -c "import weirdness_engine as w; assert w.run_synthetic_verification_benchmark()['passed'] and w.run_synthetic_cadence_benchmark()['passed'] and w.run_cadence_edge_case_benchmark()['passed']"`. Expected: all PASS.
- [ ] **Step 6:** Commit.

### Task 6: Injection, blind plants and the calibration campaign (M3)

**Files:**
- Create: `survey/inject.py`, `survey/blind.py`, `survey/calibrate.py`, `tests/test_inject.py`, `tests/test_blind.py`, `data/anchors_ma2023.json`

**Interfaces:**
- Produces: `survey.inject.plant(on: tuple, spec: dict, seed: int) -> tuple`. It returns a new `(data, freqs, hdr)` with one setigen signal added in the raw (pre-normalization) power units. `spec` is `{"shape", "f_mhz", "drift_hz_s", "snr", "width_hz", "duty", "n_teeth", "spacing_hz", "curv"}`.
- Produces: `survey.blind.BlindSchedule(manifest_path: str, rate: float, seed: int)`, with:
  - `.maybe_plant(cadence_id: str, scan_idx: int, on: tuple) -> tuple`: plants into ON scans only, at the same location in all three ON scans (drift-consistent), and appends to the manifest
  - `.unblind(flag: dict) -> dict | None`
- Produces: `survey.calibrate.run_campaign(cadences: list, grid: dict, ladder: Ladder) -> dict`, which writes `results/calibration.json`: per shape × band × snr × drift, recovered/planted plus the rung that eliminated each miss.

**Rules (spec §6):**
- **The manifest** is written to `E:\seti_staging\sealed\plants.jsonl`, outside the repo. No module except `blind.py` imports its path; the runner gets a schedule from `BlindSchedule.default(rate, seed)`, which supplies the path. A test asserts this by grepping the `survey/` sources.
- **The blind rate** is set in `ladder.yaml` as `blind: {rate: 0.02}`; that edit is part of this task.
- **The calibration campaign** uses a random 5% of complete cadences (seed `20261017`), which stay in the survey.
- **The grid:** each committed shape × SNR {6, 8, 10, 15, 25, 40} × drift {0, 2, 10, 30, 60, 90} Hz/s × both bands. Also Price-style narrow tones (width 3 Hz, drift ≤ 4 Hz/s) for the Price anchor (spec §7).
- **Plants run the full path**, `detect` → `present_in_scan` → `rungs_1_to_4`, exactly as the runner does.
- **`data/anchors_ma2023.json`:** the 8 Ma et al. 2023 signals of interest (target, MJD, frequency, drift) transcribed from the paper's table (arXiv:2301.12670), with the table number cited. Run them through the ladder and add the results to `calibration.json` under `anchors.ma2023`. If the paper does not give enough to locate them, record that in the file and in the spec's §7.

- [ ] **Step 1: Write the failing tests:**
  - `test_plant_changes_only_target_region`: the difference between the planted and original data is nonzero only within ±(width + drift span) of `f_mhz`.
  - `test_plant_is_deterministic`: same seed → identical arrays.
  - `test_blind_rate_and_on_only`: over 1,000 calls at rate 0.02, the plant count is in [10, 35], all in ON scans, each manifest row has `cadence_id`, `f_mhz`, `drift_hz_s`, `shape`.
  - `test_unblind_matches_planted_flag`: a flag within `rung5.freq_tol_khz` of a manifest row → returns that row; a flag elsewhere → `None`.
  - `test_manifest_path_only_in_blind_module`: grep `survey/*.py`; only `blind.py` contains `sealed`.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `plant`, `BlindSchedule` and `run_campaign`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Run the campaign: `python -m survey.calibrate --fraction 0.05 --seed 20261017`. Then set each `detectors.<shape>.snr` and the rung-3 zone widths in `ladder.yaml` to the values the campaign justifies (90% recovery at the quoted limit, spec §6), and write the justification as YAML comments with the `calibration.json` numbers. **No real-signal outcomes may inform these values.**
- [ ] **Step 6:** Commit (`ladder.yaml`, `calibration.json` summary, anchors).

### Task 7: Resumable runner with SQLite state (M4)

**Files:**
- Create: `survey/state.py`, `survey/runner.py`, `tests/test_state.py`, `tests/test_runner.py`, `scripts/run_survey_task.ps1`

**Interfaces (Plan B depends on this schema; don't rename columns without updating Plan B):**
- Produces: `survey.state.open_db(path=r"E:\seti_staging\state\survey.sqlite") -> sqlite3.Connection`, with these tables:
  - `cadences(id TEXT PRIMARY KEY, star TEXT, band TEXT, status TEXT, attempts INT, reason TEXT, bytes INT, started_utc TEXT, finished_utc TEXT)`
    - `status` ∈ `queued`, `downloading`, `scoring`, `scored`, `failed`, `parked`, `incomplete`
  - `signals(id TEXT PRIMARY KEY, cadence_id TEXT, star TEXT, band TEXT, shape TEXT, peak_freq_mhz REAL, drift_rate_hz_s REAL, snr REAL, weirdness REAL, verdict TEXT, rung INT, reason TEXT, figure TEXT, scans_json TEXT, planted INT DEFAULT 0, created_utc TEXT, decided_utc TEXT)`
    - `planted` is set only by unblinding (Plan C)
  - `heartbeat(id INT PRIMARY KEY CHECK (id=1), star TEXT, cadence_id TEXT, scan_idx INT, bytes_total INT, speed_mb_s REAL, updated_utc TEXT)`
  - `speed_log(utc TEXT, mb_s REAL)`: one row per finished download, for Plan B's speed graph
  - `events(utc TEXT, kind TEXT, detail TEXT)`
- Produces: `survey.state.signal_id(cadence_id, shape, tile_idx) -> str`, deterministic.
- Produces: `survey.runner.run(db, cadences, ladder, *, calibration: bool = False, max_cadences: int | None = None) -> None`. The loop for each cadence:
  1. download all 6 scans (reuse `run_survey.download_file_streaming`, verifying size against the index `size`)
  2. blind-plant (ON scans)
  3. `detect` on ON 1
  4. `present_in_scan` per scan
  5. `rungs_1_to_4`
  6. upsert signals; render figures for every signal (`run_survey.render_candidate_plot`), saved under `E:\seti_staging\results\figures\{signal_id}.webp`
  7. purge raw
  8. update the heartbeat
- Produces: the CLI `python -m survey.runner run|status|finalize`. `finalize` runs `rung_5_final` over all `PENDING_R5` signals after the last cadence.

- [ ] **Step 1: Write the failing tests** (`tests/test_runner.py` uses a fake downloader and two tiny synthetic cadences; no network):
  - `test_rerun_is_idempotent`: run twice → same signal rows, same count (Review Focus 3).
  - `test_truncated_download_fails_then_parks`: the downloader returns a file 10 bytes short → status `failed`, `attempts` increments; after 3 attempts → `parked`, reason `"size mismatch"`. No signals are written for it (Review Focus 1).
  - `test_low_disk_pauses`: patch `shutil.disk_usage` so free < 2× cadence bytes → no download, an event `paused: disk`, cadence status unchanged (Review Focus 4).
  - `test_raw_purged_after_scoring`: no files are left in the raw dir.
  - `test_signal_verdicts_written`: every signal row has a verdict in the global vocabulary, and `rung` is set iff `ELIMINATED`.
  - `test_finalize_turns_pending_into_eliminated_or_survivor`: after `finalize`, there are no `PENDING_R5` rows.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `state.py` and `runner.py`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Pilot on 10 real cadences: `python -m survey.runner run --max-cadences 10 --calibration`. Check `status` shows 10 `scored`/`parked`/`incomplete` and figures exist. Kill it once mid-download and rerun to confirm the resume.
- [ ] **Step 6:** Commit. `scripts/run_survey_task.ps1` registers a Windows Task Scheduler task that runs `python -m survey.runner run` at logon and restarts on failure. Don't register it yet; that's Task 9.

### Task 8: Survey pipeline acceptance on the six-target pilot (M2 done-check)

**Files:**
- Create: `tests/test_pilot_regression.py`, `data/pilot_expected.json`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1:** Run the new pipeline on the six pilot cadences in `targets_catalog.STAGE1_CADENCES`. Record every signal's verdict and rung in `data/pilot_expected.json`.
- [ ] **Step 2: Write** `test_pilot_regression.py`:
  - asserts no pilot signal is `SURVIVOR`
  - asserts the Kepler-992b 1617.88 MHz signal is eliminated at rung 2 or 4
  - asserts the Sgr B2 2193.56 MHz carrier is eliminated (rung 1 when OFF scans exist, else rung 5 after `finalize`)
  - marked `@pytest.mark.network`, skipped unless `SETI_NETWORK=1`
- [ ] **Step 3:** Run it with `SETI_NETWORK=1`. Expected: PASS. Hand `data/pilot_expected.json` to a fresh reviewer (Codex via the `codex` skill) as a non-author check that every elimination's reason is right, and grade it per the canon.
- [ ] **Step 4:** Commit.

### Task 9: Freeze the ladder and start the full run (M4)

**Files:**
- Create: `survey/freeze.py`, `tests/test_freeze.py`
- Modify: `survey/runner.py` (call the freeze check in `run` unless `calibration=True`)

**Interfaces:**
- Produces: `survey.freeze.check_frozen(repo=".", ladder_path="ladder.yaml") -> str`. It returns the tag name, or raises `LadderNotFrozen(msg)`. Passing requires:
  - a tag `ladder-v<version>` exists
  - `git show <tag>:ladder.yaml` is byte-identical to the working file
  - the working tree has no changes to `ladder.yaml`

- [ ] **Step 1: Write the failing tests** (in a temp git repo created in the test):
  - `test_untagged_refuses`
  - `test_tag_matches_passes`
  - `test_edit_after_tag_refuses_and_names_tag`: the message contains `ladder-v1` (Review Focus 5)
  - `test_calibration_mode_skips_check`
- [ ] **Step 2:** Run the tests. Expected: FAIL. Then implement. Then run. Expected: PASS.
- [ ] **Step 3:** Commit. Tag: `git tag -a ladder-v1 -m "Frozen ladder for the whole-sample run"`.
- [ ] **Step 4: Ask Ben before this step.** Register the Task Scheduler job with `scripts/run_survey_task.ps1` and start the run. Confirm in `python -m survey.runner status` that cadences are moving. Write a seal noting the tag, the start time, and the measured TB total from Task 3.

---

## Self-review notes (kept for the executor)

- **Spec coverage:**
  - §4 → Tasks 1–3
  - §5 → Task 4 (rungs), Task 5 (presence), Task 7 (`finalize` = rung 5 at run end)
  - §6 → Tasks 5–6
  - §7 → Task 6 (Price + Ma anchors), Task 8 (controls via the existing `gate_verdicts`)
  - §8 → Tasks 7, 9
  - §9 → Plan B
  - §10 and M5 → Plan C
- **Plan C will need:**
  - `signals.planted`
  - `results/calibration.json`
  - the sealed manifest
  - Price-table distances (`Star.dist_pc`)
  - GBT SEFD values (to be sourced and cited in Plan C)
