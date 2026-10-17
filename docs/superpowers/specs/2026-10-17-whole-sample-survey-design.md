# seti-hunter: whole-sample survey design

**Status:** draft for Ben's approval · **Date:** 2026-10-17 · **Owner:** Ben Schippers (independent researcher, Broken Branch)
**Written by:** Claude, from the 2026-10-16 design conversation. Marks used below: **[Ben]** = Ben decided it; **[Claude's call]** = a default Ben can override; **[builder]** = left to whoever builds it.

---

## 1. Intent

Search every star in Breakthrough Listen's public Green Bank sample for signal shapes their pipelines were not built to find. Publish the result honestly, whatever it is.

A year from now (≈ 2027-10), Ben holds three things that ship together **[Ben]**:

1. **A short paper:** *Research Notes of the AAS* (RNAAS) first, arXiv after. Author: **Ben Schippers, independent researcher, affiliation Broken Branch** **[Ben]**.
2. **The open code** that produced every number in it.
3. **A public dashboard on brokenbranch.dev** listing every signal the search flagged and the exact reason each was eliminated, or why it wasn't.

The rejection record is the deliverable, not a side effect **[Ben]**. The expected outcome is an upper limit, not a detection. A survivor becomes a re-observation request, never a claim.

### Why this is worth doing

- **Prior work is narrowband.** Price et al. 2020 (arXiv:1906.07750), Ma et al. 2023 (arXiv:2301.12670) and Painter et al. 2024 (arXiv:2412.05786) all search the same telescope's data for Hz-wide tones drifting at ≤ ±4 Hz/s. Gajjar et al. 2022 (arXiv:2205.02964) covers millisecond dispersed pulses at C-band.
- **The gap.** Breakthrough Listen's own overview (arXiv:1907.05519) says broadband or modulated emission has seen "very limited searches". Painter 2024 notes that the standard pipeline misses "signals with other morphologies".
- **Our resolution fits that gap.** The mid-resolution files (~2.86 kHz × 1.07 s) are the natural instrument for kHz-wide structure.

### What Ben fears most, which this design exists to prevent **[Ben]**

1. Calling something a candidate when it was obviously interference.
2. An upper limit that's wrong because the planted-signal tests don't match real data.

---

## 2. Goals, non-goals, anti-goals

**Goals**
- Score every complete cadence of the 1,133-star sample at L- and S-band with the existing engine, extended as below.
- Put every flagged signal through a **frozen five-rung rejection ladder** (§5) and record the first rung that eliminated it.
- Set upper limits for four shapes using **blind planted signals in real files** (§6).
- Keep a playful "weird anything" discovery channel running throughout, with no limit claimed for it **[Ben: "keep an ear, eye, and whiskers out for weird. All weird."]**.
- Run the public dashboard **live during the run** **[Ben]**.

**Non-goals**
- Hz-resolution narrowband searching. That's Price, Ma and Painter's ground; we use it only as a calibration anchor (§7).
- Millisecond dispersed pulses (Gajjar's ground; our 1 s sampling can't see them).
- Parkes data, C/X band, and stars outside the Price 2020 Green Bank tables. All are possible follow-ups.
- Claiming a detection.

**Anti-goals: failure even if everything "works"**
- A "candidate" a skeptic can dismiss in one glance.
- A limit that the injection tests don't actually support.
- Thresholds tuned after seeing the data.
- Any public leak of a survivor's star, frequency or date before review ends.
- Hype language. Public copy is clinical: signals are **eliminated**, never "killed" **[Ben]**.
- Overnight agent swarms. The run is a plain scheduled script (night shifts are retired; see `~/CLAUDE.md`).

---

## 3. Constraints

- **Fully independent:** no outside reader before submission **[Ben]**. After private review, Ben is willing to contact Breakthrough Listen or the SETI Institute for a re-observation **[Ben]**.
- **Home-scale bandwidth:** measured 1.2–1.4 MB/s from `bldata.berkeley.edu` on 2026-10-16.
- **Disk:** a rolling buffer on `E:\seti_staging` (697 GB free). Raw files are purged after scoring.
- **Machine:** Ben's Windows box; Python venv at `E:\seti_staging\venv`. Weeks of unattended running are fine **[Ben: "I'm good for a hot moment"]**.
- **No secrets in code.** Anything public goes through an allowlist (§9).
- **Journal policy:** disclose AI-tool use (Claude, Codex) in the paper per AAS policy. Confirm the current RNAAS limits (length, figure count) at writing time **[builder]**.

---

## 4. The sample and the data

- **Sample:** the 1,133 distinct Green Bank stars in Price et al. 2020's supplementary tables (`listen2019_tables.pdf`, Tables 1–2): 881 at L-band, 999 at S-band, 747 at both.
  - The paper's text says 1,138 (882 / 1,005 / 749). The tables genuinely list fewer, and no rows are missing from the PDF. Two stars appear under two names each and are merged: GJ166 = HIP19849, GJ702A = HIP88601.
  - The paper reports this discrepancy in one sentence.
  - The list lives as `gbt_sample_price2020.csv`, with a provenance header, built by `build_sample.py`. Both are currently in Claude's session scratchpad and **must be copied into the repo** (`data/`) as the first build step **[Claude's call]**.
- **Files:** the mid-resolution `.gpuspec.0002.h5` product of each scan (~230–270 MB each). Only **complete cadences** of 6 scans are analysed, as in Price 2020. Incomplete cadences are counted and listed, not scored.
- **Volume (measured on a random 40-star sample, 2026-10-17, seed 20261016):**
  - Mid-res files have a median size of 242 MB.
  - A star's own (ON) scans total a median of 1.53 GB and a mean of 1.91 GB, which extrapolates to **≈ 2.2 TB** of ON data for 1,133 stars.
  - A cadence's OFF scans are other stars' files, so the full total is **≈ 2.2–4.3 TB**, depending on how many OFF files are shared between cadences. That's **≈ 3–6 weeks** at measured speeds.
  - In the sample, 6 of 40 stars had no L-band files and 5 had no S-band files, consistent with the per-band counts.
  - Milestone M1 replaces this estimate with the exact number from the full archive index (`harvest_index.py`, ~600k file records harvested so far).
- **Distances:** the Price tables also carry each star's distance (pc). M1 parses it into the CSV, because the EIRP limits (§6) need it.
- **The archive index:** a one-time pull of the open-data API (`seti.berkeley.edu/opendata/api`), one query per target. Cadences are assembled from it by session and scan number.

---

## 5. The rejection ladder (frozen before the full run)

Every flagged signal goes down the same five rungs in this order. The dashboard and the paper record the **first rung that eliminated it**.

| Rung | Eliminates a signal that… | Notes |
|---|---|---|
| ① | is present in **any** OFF scan | Detection threshold as in today's cadence check (OFF_DETECTION_SNR = 8, drift-aligned). |
| ② | is missing from **any** ON scan along its predicted drift line | Today's full-cadence test (commit `ad36591` plus the Codex fixes through `fb48fb3`). |
| ③ | is an **instrument artifact**: it sits on a coarse-channel centre (the polyphase filterbank's DC spike) or within a few fine channels of a coarse-channel edge | **[Claude's call, changed after the builder check]** The width of the excluded zone is set from the data, then frozen. See the note below the table for why this replaced "zero drift". |
| ④ | falls inside a known human-transmitter band | Initial list: GPS L5 / L2 / L1, Inmarsat 1525–1559, GLONASS 1598–1606, Iridium 1616–1626.5, spacecraft telemetry 2200–2290, Wi-Fi/ISM 2400–2483.5 MHz. The receiver notches (≈1200–1341 and ≈2300–2360 MHz) hold no data. The list is checked against ITU allocations and the GBT RFI reports before freezing **[builder]**. |
| ⑤ | is also seen around **another star** in a different session (same frequency and drift within a frozen tolerance) | Only possible at whole-sample scale, and the strongest rung. Already demonstrated: the 2193.56 MHz carrier at Sgr B2 matches the interference control seen at Tabby's Star on another date. |

**Why rung ③ is not "zero drift" [Claude's call].** Price 2020 eliminates zero-drift signals, because a source off the Earth almost always drifts a little. That test works at their ~3 Hz resolution and fails at ours:
- A real sky source's drift is typically under ~1 Hz/s. At mid-res (≈ 2.86 kHz channels), anything under ≈ 10 Hz/s looks like zero within one scan, and under ≈ 2 Hz/s looks like zero across a whole 25-minute cadence.
- A "zero drift" rung would therefore eliminate the realistic drift range of every committed shape, and most of the discovery channel.
- Earth-fixed transmitters are already caught by ① (they appear in OFF scans) and ⑤ (they appear around other stars).

So rung ③ instead removes the one well-known instrument artifact. **Drift range covered:** the survey covers |drift| from 0 up to the drift bank's edge (≈ ±95 Hz/s), and the paper says so.

**Each shape gets its own presence model, inside the same five rungs [Claude's call].** Rung ② asks "is it present in every ON scan?", but "present" is defined per shape in `ladder.yaml`:
- **Linear drifts:** along the extrapolated drift line, with a window that grows with the drift-rate uncertainty. This is what the cadence code does now.
- **Chirps:** along a curvature-bounded fan of tracks, extrapolated from the scan where the chirp was fitted.
- **Intermittent tones:** a time-collapsed detection anywhere in the scan. Duty cycles too low to show in every ON scan are honestly outside that limit, and the limit names the duty-cycle range it covers.
- **Combs:** the comb's centroid and spacing, tracked like a linear drift.
- **Discovery-channel finds:** the drift-aligned test where a drift was measured, otherwise time-collapsed presence.

The ladder's *order and meaning* are identical for every shape; only "present" is shape-aware.

Signals that can't be tested (e.g. no OFF scans) get **Untested**, not a pass. The re-check failing to re-find a signal gets **Not re-found**, also not a pass.

**Freezing [Claude's call]:**
- All thresholds, band lists and tolerances live in one committed file (`ladder.yaml`), tagged `ladder-v1` before the full run starts.
- Any later change gets a new tag and a full re-scoring, and the paper says so.
- Thresholds may be tuned only on the injection set and the six-target pilot, never on the full run.

**Survivors:** a signal that passes all five rungs is **held privately** **[Ben]**. Its private review:

1. Re-check on the full-resolution `.0000` files (~17 GB each; feasible for a handful of survivors).
2. A second reviewer agrees it passes (Codex via the `codex` skill, graded, per the canon).
3. Ben requests a re-observation from Breakthrough Listen or the SETI Institute.
4. Public release with everything.

If review eliminates it, it joins the Ledger like any other signal, with the step and the reason.

---

## 6. Signal shapes and the upper limits

**Committed shapes:** each gets an upper limit, because each can be planted and its recovery measured **[Claude's call, Ben approved the direction]**.

1. **Wide drifting carriers:** kHz-wide tones, as a modulated, data-carrying carrier would look.
2. **Fast and curving drifts:** linear drifts well beyond ±4 Hz/s, plus chirps whose drift changes within a scan.
3. **Intermittent tones:** carriers switching on and off within a 5-minute scan.
4. **Combs:** several evenly spaced carriers moving together.

**Discovery channel, no limit claimed:** the engine's open-ended weirdness score. Its finds go down the same ladder and onto the dashboard.

**What "flagged" means [Claude's call, from the builder check]:**
- **Each committed shape gets its own detector with an absolute threshold.** Every tile is scored for every shape, and a tile above a shape's threshold is flagged for that shape. Today's per-file axes are the starting point (drift SNR for linear drifts, curvature for chirps, burst score for intermittent tones, morphology for combs). They need recalibrating to absolute SNR so that a planted signal's recovery doesn't depend on how much interference the file holds.
- **The discovery channel keeps the composite weirdness score with a per-cadence top-K.** It sets no limit, so a relative ranking is fine there.
- The number of flagged signals per shape is measured during the calibration campaign. Thresholds are chosen so the total stays tractable for the Ledger and rung ⑤; the target is ~10⁴–10⁵ flagged signals across the survey.

**How the limits are measured** (this answers fear #2):
- Plant synthetic signals **into the real recorded files**, with their real noise, interference and channel edges, using Breakthrough Listen's open `setigen` package.
  - Plants go into ON scans only and run through the identical pipeline end to end, including the ladder.
  - Planting happens on the downloaded file, before scoring, so the scorer can't tell plants from sky.
- **Two plant sets:**
  - *Calibration campaign:* a fixed grid of shape × strength × drift × band on a random 5% of cadences. It produces the sensitivity curves and sets every threshold.
    - **These cadences stay in the survey [Claude's call].** Tuning uses only the recovery of planted signals, never the outcome of a real flagged signal. So "never tune on the full run" holds, and the survey still covers every star.
  - *Blind plants:* mixed into the live run at a low rate. The seed and manifest live in a sealed file the pipeline never reads until unblinding at the end.
- **The limit is quoted where recovery reaches a stated fraction** (e.g. 90%) **[builder: pick and justify]**. Masked bandwidth, notches and incomplete cadences all count against the limit.
- **The form of the limit [Claude's call]:** each shape gets two numbers.
  1. The signal-to-noise (and flux-density) threshold at that recovery fraction.
  2. A Price-style EIRP statement: "fewer than X% of stars host a transmitter of this shape brighter than Y W", using the Price-table distances (§4) and the GBT receivers' published system-equivalent flux densities (SEFD).

  The Price anchor (§7) is computed in the same EIRP units, so the two numbers compare directly.
- **Blind plants and review [Claude's call, from the builder check]:**
  - Plants exist only in the downloaded mid-res file, so a planted survivor can't go through the full-resolution re-check or a re-observation request.
  - **A survivor is checked against the sealed plant manifest *before* review step 1.** The manifest is written by the planting script to a location the scorer never reads; a separate `unblind` command checks one survivor against it.
  - A plant that survived is marked "planted, recovered", counts toward the blind-plant result, and leaves review. Only true survivors continue to the full-resolution re-check, and **no re-observation request can ever be sent for a plant.**
  - The public "under review" count may include plants for the hours before that check, so the dashboard carries a standing note: *"Some signals under review may be planted test signals; we check each one first."*

---

## 7. Calibration anchors (how we know the method isn't wrong)

1. **Price 2020's narrowband limit.** Plant Price-style narrow drifting tones and measure our sensitivity to them. Our limit for that shape should differ from Price's by the amount our ~1,000× wider channels predict. If it doesn't, the method is wrong, and we find out before a reviewer does.
2. **Ma et al. 2023's eight "signals of interest".** Find their cadences and run them through our ladder; the paper reports what our ladder says about each. Do the same for Painter 2024's candidates if they're listed **[builder]**.
3. **Negative controls stay in every run.** Known interference carriers must come back eliminated at ① or ⑤. A run whose controls pass is invalid; the pipeline already withholds PASSES when a control fails (commit `67d269a`).

---

## 8. The run

- **Order:** M1 sample + index + cadence list → M2 ladder rungs ③–⑤ and `ladder.yaml` → M3 calibration campaign → freeze `ladder-v1` → M4 full run → M5 unblinding and limits → M6 paper.
- **Runner [Claude's call]:**
  - A plain resumable Python script started by Windows Task Scheduler; no agents.
  - Its state lives in a SQLite file: one row per cadence with its status (queued / downloading / scored / failed + reason).
  - Restart-safe and idempotent.
  - Purges raw files after scoring.
  - Keeps per-signal cutouts and features, which are small, so the paper can be rebuilt without re-downloading.
- **Parallel downloads:** 2–3 streams if the server allows **[builder: measure first]**.
- **Failure handling:** a cadence that fails 3 times is parked with its reason and listed on the dashboard as "not analysed". It's never silently skipped.

---

## 9. The public dashboard (live during the run)

**Layout [Ben]:**
- **The Funnel** is the front door: one count per rung, flagged → eliminated → under review → public candidates.
- **The Weird Wall** is for browsing: real ON-scan cutouts sorted by weirdness, each stamped with its fate, plus a gold "still unexplained" slot.
- **The Ledger** is one click deep: the full three-panel figure, six-scan fingerprint, rung, and a plain-English reason.

**Also on the page [Ben approved, from the mockups]:**
- the all-sky map of the 1,133 stars with "replay the survey"
- the 1.1–2.8 GHz spectrum ribbon with interference bands and pinned signals, with callouts **computed from data, never typed**
- the live heartbeat panel (progress ring, current star and scan lights, data streamed, speed)
- a "how to read this" strip (what a cadence is, the three fingerprints, the ladder)

**Under private review [Ben]:** a large pinned animated tile.
- Its waterfall is generated art behind frosted glass. It shows no star, frequency or date, only the four-step review tracker.
- The Funnel gets a shimmering "Under private review" row.

**Visual bar [Ben]:** "top shelf, be creative, give more than you think you need." Every visual is a showpiece, not a wireframe.

**Match the site [Ben]:**
- It's a wing of brokenbranch.dev, like `erdos/`.
- It links `/css/tokens.css` (self-hosted Fraunces + JetBrains Mono) and adds a wing palette.
- It follows the house style (`~/.claude/skills/html-artifacts/house-style.md`): serif = human voice, mono = machine voice; MEASURED / DEMO badges on live panels; a **BOUNDARY** block saying what the survey does not claim; reduced-motion path; no horizontal scroll at phone width.
- The instrument panels may use the sanctioned "bioluminescent lab" register inside the warm page.

**Wiring [Claude's call, reusing the site's existing patterns]:**
- **Where it lives:** the page is built in the seti-hunter repo, which must become a **public GitHub repo** (Ben confirms creation at build time). The site's existing `mirror-pull` workflow pulls it in; no tokens.
- **How it stays live:**
  - The runner publishes a sanitized `snapshot.json` to a public gist every ~15 minutes.
  - A new `api/` function on the site proxies it with a strict allowlist and edge cache, exactly like `api/tank.js`.
- **What the public sees mid-run [Ben, 2026-10-17, from the builder check]:**
  - **Eliminated signals show live**, the moment their rung eliminates them: Funnel, Wall and Ledger.
  - **Signals waiting on rung ⑤ stay hidden until the run ends.** Rung ⑤ (seen around another star) can only be final once the whole sample is in.
  - The public sees only a **"pending final check" count, updated once a day.** It's batched across all stars scored that day, so neither a jump in the count nor a gap in a star's Ledger list can point at one star.
  - The Ledger lists a star's signals only once that star has nothing pending, or after the run ends.
  - At the end of the run, rung ⑤ runs as one final pass over every pending signal. Its eliminations go public. **Survivors go straight to private review**, so in practice "under review" only exists after the run.
  - The heartbeat may show the current star, because the daily batching breaks the link between that star and the pending count.
- **Redaction is enforced twice.** The runner never writes survivor details into the snapshot (only a count), and the `api/` allowlist drops anything not on the contract. A test proves a survivor's star, frequency and date cannot reach the page.
- **Wing path:** `/listen/` **[Claude's call; Ben can rename]**.
- **Figures update daily, numbers update every ~15 minutes [Claude's call, from the builder check].**
  - Spectrogram figures are too big for the gist snapshot (the tank.js pattern caps it at 256 KB), so they're committed to the public repo and reach the site through the daily `mirror-pull`.
  - The Wall and Ledger can therefore lag the Funnel and heartbeat by up to a day, and the page says so in a mono caption.
  - This keeps the wiring token-free.

---

## 10. The paper

- **Venue:** RNAAS first (short), then a fuller arXiv version.
- **Author line:** Ben Schippers, independent researcher, Broken Branch **[Ben]**.
- **One figure:** the Funnel, or the sensitivity curves **[builder]**.
- **Content:**
  - the sample and its table-vs-text discrepancy
  - the four shapes and the ladder
  - the limits
  - the two calibration anchors
  - the blind-plant result
  - links to the code (with a tagged release / DOI) and the dashboard
  - an AI-use disclosure
- **Honesty rules carried into the text:** limits only where injections support them, and "eliminated" language throughout.

---

## 11. Milestones: what "done" looks like for each

| # | Milestone | Done means |
|---|---|---|
| M1 | Sample + archive index + cadence list in the repo | `data/` holds the 1,133-star CSV, the index, and a cadence table. The paper-ready count of complete cadences per band and the measured TB total replace §4's estimate. |
| M2 | Rungs ③–⑤ + `ladder.yaml` | Each rung has a test that fails before it exists. The six-target pilot rerun shows every elimination with its rung. |
| M3 | Calibration campaign | Sensitivity curves per shape × band. Per-shape detection thresholds and the rung ③ artifact zone are set. The Price anchor and the Ma anchor are reported. |
| M4 | Freeze + full run | `ladder-v1` tag; the run finishes with every cadence scored, parked with a reason, or listed incomplete. |
| M5 | Unblinding + limits | Blind-plant recovery reported; limits computed; survivors (if any) through private review. |
| M6 | Dashboard live | The wing is on brokenbranch.dev from the *start* of M4, updated every ~15 min, redaction test green. |
| M7 | Paper | RNAAS submitted; arXiv follows; code tagged. |

The dashboard (M6) is built during M2–M3 so it's live when M4 starts.

---

## 12. Left to the builder

- The exact detection thresholds and tolerances (justified, then frozen in `ladder.yaml`).
- The recovery fraction quoted for limits, and the injection grid's exact values.
- The parallel-download count, the snapshot cadence, and the SQLite schema.
- Dashboard implementation details within the visual bar and the house style.
- Whether the arXiv version adds analyses beyond the RNAAS note.

## 13. Known risks

- **The archive index API is slow** (one query per target, ~12k targets). Mitigation: a resumable harvest with an on-disk cache, already running.
- **Some sample stars may lack complete mid-res cadences.** These are reported as a number, not hidden.
- **setigen's injection may not exactly match how real signals pass through the BL reduction.** Mitigation: the Price anchor (§7) catches a gross mismatch. The paper names the residual risk in its BOUNDARY paragraph.
- **The run, the paper and the dashboard all depend on one Windows machine.** Mitigation: the SQLite state plus kept features make the run resumable and the paper rebuildable.

## 14. Where things are now (2026-10-17)

- `~/projects/seti-hunter` (local git, no remote yet) has:
  - the engine
  - the fixed OFF veto (`6b3fde6`)
  - the full-cadence test as the Stage 1 default
  - the Codex-reviewed fixes through `fb48fb3`
  - a six-target pilot whose 24 flagged signals were all eliminated or untested
- Mockups of the dashboard directions, the review tile, and the sky/spectrum showpiece are in `.superpowers/brainstorm/` (gitignored) in seti-hunter and in the design session's folder.
- Seals: `personal-infra/seals/2026-10-16-seti-hunter-veto-and-cadence-claude.md` and the cadence session's seal.
