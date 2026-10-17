# Plan B: Live Public Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the survey on brokenbranch.dev at `/listen/`, live while the run is going, without ever exposing a signal that is waiting on rung ⑤ or under review.

**Architecture:**
- **seti-hunter** builds a sanitized `snapshot.json` from the run's SQLite state (Plan A, Task 7) and publishes it to a public gist every ~15 minutes. It also exports eliminated-signal figures plus a `figures.json` into the wing folder, committed daily.
- **The site** gets a new `api/listen.js` that proxies the gist through a strict allowlist with edge caching, the same pattern as `api/tank.js`. The existing `mirror-pull` workflow copies the wing page in from the public seti-hunter repo.
- **The page itself** is static HTML/CSS/JS on the site's `/css/tokens.css`.

**Tech Stack:**
- Python 3 (venv `E:\seti_staging\venv`), `gh` CLI for the gist.
- Vanilla HTML/CSS/JS, Node 22 `node --test` for the site's contract tests.

**Spec:** `docs/superpowers/specs/2026-10-17-whole-sample-survey-design.md`, §9 (approved 2026-10-17).

**Consumer:** the public, plus Ben, at `brokenbranch.dev/listen/`. Numbers refresh every ~15 minutes during the run; figures refresh daily. After the run it stays as the paper's linked results page.
**Retires:** the pilot's local `dashboard.html` and its generator `run_survey.generate_html_dashboard`. Both are deleted in B7, once `/listen/` is live.

**Depends on:**
- Plan A Task 7's SQLite schema: tables `cadences`, `signals`, `heartbeat`, `events`, columns exactly as listed there.
- Tasks B1–B5 can be built and tested against a fixture database before the run starts. B7 goes live when the run starts.

## Global Constraints

- **The page lives at** `https://www.brokenbranch.dev/listen/`. Its source is `site/listen/` in seti-hunter.
- **House style:** `~/.claude/skills/html-artifacts/house-style.md`.
  - Link `/css/tokens.css` first.
  - Serif (Fraunces) = human voice, mono (JetBrains Mono) = machine voice.
  - MEASURED / DEMO badges on live panels.
  - A **BOUNDARY** block saying what the survey does not claim.
  - A designed reduced-motion still.
  - No horizontal scroll at 375 px.
- **Visual bar [Ben]:** "top shelf, be creative, give more than you think you need." The approved mockups are the floor, not the target. They're copied into `docs/superpowers/mockups/` in Task B5.
- **Copy:** signals are **eliminated**, never "killed".
- **Every callout number is computed from data, never typed.**
- **Redaction rules [Ben, spec §9], exact:**
  - **Eliminated signals** appear live.
  - **`PENDING_R5` signals never appear** except as a count that changes **only once per UTC day** (at the first snapshot after 00:00 UTC). It's computed from state as of that 00:00 UTC boundary.
  - **A star's Ledger list** appears only when the star has **no** `PENDING_R5` or `SURVIVOR` signal.
  - **`SURVIVOR` signals appear only as the under-review count.** No star, frequency, date or figure is ever written.
  - **The standing note** under the review count, exact copy: *"Some signals under review may be planted test signals; we check each one first."*
- **Snapshot schema version 1.** Size cap: **256 KB** serialized.
- **No tokens in the site.** The gist is public and the proxy fetches it unauthenticated.
- **Commits end with:** `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **The gist is unreachable or stale** (machine asleep, network down): the page shows the last good numbers with an "as of" time. A stale badge appears after 60 minutes, and the page never shows blank zeros as if they were real (house rule: empty state is blank, not zero). Tests in B4 and B5.
2. **The snapshot outgrows 256 KB as eliminations pile up:** counts stay complete; the `recent_eliminated` list is cut to the newest 200. The full Ledger comes from the daily `figures.json`. Test in B1.
3. **A star's pending signal is eliminated at `finalize`:** that star's Ledger list appears at the next export, and the Funnel still sums correctly (flagged = sum of rungs + pending + under review + untested buckets). Test in B1.
4. **The UTC day boundary:** a snapshot built at 23:59 UTC and one at 00:01 UTC give different pending counts only through the 00:00 batch, never mid-day. Built from a fixed `now`, never the local clock. Test in B1.
5. **Phone width and reduced motion:** no horizontal scroll at 375 px, and every animation has a designed still frame. Verification step in B5.

---

### Task B1: Snapshot builder with the redaction rules

**Files:**
- Create: `survey/snapshot.py`, `tests/test_snapshot.py`, `tests/fixtures/make_fixture_db.py`

**Interfaces:**
- Consumes: `survey.state.open_db` and the Plan A tables.
- Produces: `survey.snapshot.build_snapshot(db, now_utc: datetime) -> dict`, with schema 1:

```text
{schema:1, as_of_utc, mode:"MEASURED"|"DEMO",
 progress:{stars_total:1133, stars_done, cadences_total, cadences_done, cadences_parked, cadences_incomplete, bytes_streamed},
 funnel:{flagged, eliminated_by_rung:{"1":n,...,"5":n}, untested, not_recovered, incomplete, pending_final_check, under_review, public_candidates},
 pending_batch_utc,            # the 00:00 UTC boundary the pending count was taken at
 recent_eliminated:[{id, star, band, shape, peak_freq_mhz, drift_rate_hz_s, rung, reason, weirdness, figure, decided_utc}],  # newest first, <= 200
 heartbeat:{star, scan_idx, speed_mb_s, updated_utc},
 speed_series:[float]}         # last 60 rows of the speed_log table, oldest first
```

- Produces: `survey.snapshot.serialize(snap: dict) -> bytes`. It's compact JSON and raises `SnapshotTooLarge` above 256 KB after truncating `recent_eliminated`.

- [ ] **Step 1:** Write `tests/fixtures/make_fixture_db.py`. It builds a temp SQLite file with Plan A's schema and seeds: 3 stars; signals eliminated at each rung; one `PENDING_R5` on star A; one `SURVIVOR` on star B; parked and incomplete cadences.
- [ ] **Step 2: Write the failing tests** `tests/test_snapshot.py`:
  - `test_pending_and_survivor_details_never_serialized`: serialize the snapshot and assert that neither the pending signal's `id`, frequency (as `f"{f:.3f}"`) nor star name, nor the survivor's, appears anywhere in the bytes.
  - `test_pending_count_changes_only_at_utc_midnight`: add a new pending signal at 12:00 UTC; the snapshot at 12:05 has the same `pending_final_check` as 11:55. At 00:01 next day it includes it. `pending_batch_utc` equals that midnight.
  - `test_funnel_sums_to_flagged` (Review Focus 3).
  - `test_truncates_recent_list_to_fit` (Review Focus 2): seed 5,000 eliminations; the serialized size ≤ 256 KB and `len(recent_eliminated) == 200`, newest first.
  - `test_uses_given_now_not_clock`: monkeypatch `datetime` to raise if `now()` is called.
  - `test_mode_demo_when_no_cadence_scored`.
- [ ] **Step 3:** Run `python -m pytest tests/test_snapshot.py -v`. Expected: FAIL.
- [ ] **Step 4:** Implement `build_snapshot` and `serialize`. The redaction is a **whitelist of columns per section**, not a blacklist.
- [ ] **Step 5:** Run the tests. Expected: PASS.
- [ ] **Step 6:** Commit.

### Task B2: Figure export for the Wall and Ledger (daily)

**Files:**
- Create: `survey/figures_export.py`, `tests/test_figures_export.py`, `scripts/daily_export.ps1`

**Interfaces:**
- Consumes: the `signals` table, and figures at `E:\seti_staging\results\figures\{signal_id}.webp`.
- Produces: `survey.figures_export.export(db, out_dir="site/listen/figures", now_utc) -> dict` (counts). It writes:
  - `site/listen/figures/{id}.webp`: the full three-panel figure, ≤ 120 KB
  - `site/listen/figures/{id}_on.webp`: the ON-panel crop for Wall tiles, 300×232, ≤ 25 KB. Crop box `(97, 82, 540, 424)` on the 1620×504 figure, as in the approved mockup.
  - `site/listen/figures.json`: `[{id, star, band, shape, peak_freq_mhz, drift_rate_hz_s, rung, reason, weirdness, scans:[{role, snr, present}], decided_utc}]`

  Only `ELIMINATED` signals whose star has no `PENDING_R5`/`SURVIVOR` are written.
- `scripts/daily_export.ps1` runs the export, then `git add site/listen && git commit -m "listen: daily export <date>" && git push`. It runs once a day via Task Scheduler and is registered in B7.

- [ ] **Step 1: Write the failing tests:**
  - `test_star_with_pending_is_withheld`: star A (has pending) has no entries and no files.
  - `test_sizes_capped`
  - `test_export_is_deterministic`: two runs, byte-identical `figures.json`, sorted by `(star, peak_freq_mhz)`.
  - `test_stale_files_removed`: a figure for a signal no longer eligible is deleted.
- [ ] **Step 2:** Run the tests. Expected: FAIL. Then implement. Then run. Expected: PASS.
- [ ] **Step 3:** Commit.

### Task B3: Publish the snapshot to a public gist

**Files:**
- Create: `survey/publish.py`, `tests/test_publish.py`
- Modify: `survey/runner.py`, so it calls `maybe_publish` after each cadence

**Interfaces:**
- Produces: `survey.publish.maybe_publish(db, gist_id: str, now_utc, min_interval_s=900, runner=subprocess.run) -> bool`. It publishes when ≥ 15 minutes have passed since the last publish (time stored in `events`). It runs `gh gist edit <gist_id> -f snapshot.json <tmpfile>`. Failures are logged to `events` and never stop the survey run.
- **The gist id** is read from `E:\seti_staging\state\gist_id.txt`. Creating the gist (`gh gist create --public snapshot.json`) is an outward-facing step: **Ben confirms it in B7.**

- [ ] **Step 1: Write the failing tests** (fake `runner`, no network):
  - `test_respects_interval`
  - `test_gh_failure_is_logged_not_raised`
  - `test_publishes_serialized_bytes_exactly`: the tmpfile content equals `serialize(build_snapshot(...))`.
- [ ] **Step 2:** Run the tests. Expected: FAIL. Then implement. Then run. Expected: PASS.
- [ ] **Step 3:** Commit.

### Task B4: Site proxy `api/listen.js` (brokenbranchdevwebsite repo)

**Files (in `~/projects/brokenbranchdevwebsite`, on a new branch `listen-wing`):**
- Create: `api/listen.js`, `test/listen.contract.test.mjs`
- Modify: `vercel.json` (a function entry beside `api/tank.js`, with the same `maxDuration` and memory)

**Interfaces:**
- Consumes: the gist raw URL (constant `GIST_RAW`, filled in at B7), schema 1 from B1.
- Produces: `export function sanitizeListenSnapshot(snapshot) -> object` and the default handler. The handler:
  - fetches the gist server-side and returns `sanitizeListenSnapshot(json)`
  - sends `Cache-Control: public, s-maxage=300, stale-while-revalidate=3600`
  - on any failure, returns `{empty:true, reason}` with status 200

**Sanitizing:**
- Copy the structure of `api/tank.js`'s `sanitizeTankSnapshot`: an allowlist field by field, typed checkers (`finiteNumber`, `shortString`), and schema bounds.
- Unknown keys are dropped at every level. `recent_eliminated` is capped at 200. String fields are capped at 120 chars.
- **Defence in depth:** any `recent_eliminated` item whose `rung` isn't an integer 1–5 is dropped, so a pending or survivor row that leaked into the gist still can't reach the page.

- [ ] **Step 1: Write the failing tests** `test/listen.contract.test.mjs`, modelled on `test/tank.contract.test.mjs`:
  - bad shape → `{empty:true, reason:"bad-shape"}`
  - schema 2 → `unsupported-schema`
  - an unknown top-level key and an unknown item key are both dropped
  - a `recent_eliminated` item with `rung: null` or a `verdict: "SURVIVOR"` key is dropped
  - 500 items → 200
  - a fetch failure → `{empty:true}` with status 200
- [ ] **Step 2:** Run `node --test test/listen.contract.test.mjs`. Expected: FAIL. Then implement. Then run. Expected: PASS. Also run `npm test` to keep the existing suite green.
- [ ] **Step 3:** Commit on the `listen-wing` branch. Don't merge; B7 does that with Ben's OK.

### Task B5: The wing page

**Files (seti-hunter):**
- Create: `site/listen/index.html`, `site/listen/listen.css`, `site/listen/listen.js`, `site/listen/og.png`, `site/listen/demo-snapshot.json`
- Create: `docs/superpowers/mockups/`, holding copies of the approved mockups:
  - `dashboard-directions-v5.html`, `dashboard-wall-real-v6.html`, `under-review-v8.html` (from `.superpowers/brainstorm/12191-1792207702/content/`)
  - `showpiece-sky-and-spectrum.html` (from the design session folder `.superpowers/brainstorm/24491-1792208836/content/`)
  - their thumbnail `.jpg` assets

**Interfaces:**
- Consumes: `/api/listen` (B4), `/listen/figures.json` and `/listen/figures/*` (B2), `/css/tokens.css` and `/fonts/*` from the site, and `data/gbt_sample_price2020.csv` (baked in as a JS constant at build by `scripts/bake_stars.py` → `site/listen/stars.js`).

**Sections, top to bottom** (spec §9; the mockups show each one):
1. Eyebrow + italic Fraunces headline + lede.
2. "How to read this" strip: cadence diagram, three fingerprints, the ladder.
3. **The Funnel** (front door): one bar per rung, untested / not re-found, pending final check (daily), under review, public candidates. Count-up on load.
4. The sky map: all 1,133 stars in Hammer-Aitoff, the Milky Way, "Replay the survey", searched stars lit from snapshot progress.
5. The spectrum ribbon, 1.1–2.8 GHz: receiver ranges, notches, rung ④ bands **read from `ladder.yaml`** (baked into `stars.js`), the water hole, pinned eliminated signals, computed callouts.
6. **The Weird Wall:** ON-panel tiles sorted by weirdness, with fate stamps. The gold "still unexplained" slot shows the under-review tile (generated art, frosted, seal, redaction bars, 4-step tracker) when `under_review > 0`, and "nothing yet" otherwise.
7. **The Ledger** (one click from any tile): full figure, six-scan fingerprint, rung, plain reason.
8. The live heartbeat: progress ring, current star + scan lights, bytes streamed, speed sparkline, MEASURED badge (DEMO before the run). The caption "Figures update daily; numbers every ~15 minutes."
9. **The BOUNDARY block:**
   - the shapes and drift range covered (0 to ±95 Hz/s)
   - what isn't searched (Hz-narrow tones beyond calibration, ms pulses, Parkes)
   - "an elimination is a reason, not a verdict on the star"
10. Footer: data sources (Breakthrough Listen open data, Price et al. 2020), code link, author line "Ben Schippers, independent researcher, Broken Branch", sign-off.

- [ ] **Step 1:** Copy the mockups into `docs/superpowers/mockups/` and commit them, so the executor and reviewers see the approved floor.
- [ ] **Step 2:** Build the page against `demo-snapshot.json` (generated from the B1 fixture database) when `/api/listen` returns `{empty:true}`. In demo mode every live panel shows the DEMO badge naming the difference ("DEMO DATA: THE RUN HASN'T STARTED").
- [ ] **Step 3: Verify in a real browser** at desktop and 375 px. Serve `site/` locally with `python -m http.server`, and map `/css` and `/fonts` to the site checkout.
  - The pending and survivor details from the fixture never appear in the DOM: `document.body.innerText` contains neither the fixture's pending frequency nor its star.
  - `scrollWidth <= innerWidth` at 375 px.
  - With `prefers-reduced-motion: reduce`, there's no rAF loop running (the frame counter stays fixed for 2 s) and a designed still is shown.
  - With `/api/listen` → `{empty:true}`, last-known or demo data is shown with the stale/DEMO badge, never zeros as if they were real (Review Focus 1).
  - The console has no errors.
- [ ] **Step 4:** Run the site's validators on the page after copying it into a scratch copy of the site: `npx html-validate listen/index.html`, `node scripts/check-csp.mjs`, `node scripts/check-links.mjs`.
- [ ] **Step 5:** Commit.

### Task B6: Mirror the wing into the site

**Files (brokenbranchdevwebsite, branch `listen-wing`):**
- Modify: `scripts/mirror-pull.mjs` (add a `listen` source: repo `benskamps/seti-hunter`, path `site/listen/` → `listen/`, verbatim copy), `.github/workflows/mirror-pull.yml` (clone the source), `test/mirror-pull.contract.test.mjs`
- Modify: `labs/index.html` (a door band to `/listen/`), `sitemap.xml`, `llms.txt`, and `inventory.json` if `test/inventory.contract.test.mjs` requires it

**Interfaces:**
- Consumes: the public seti-hunter repo. **Ben confirms creating `benskamps/seti-hunter` as public before this task** (outward-facing).

- [ ] **Step 1:** Extend `test/mirror-pull.contract.test.mjs` with the `listen` source. Expect it to fail before `mirror-pull.mjs` is changed.
- [ ] **Step 2:** Implement, then run `npm test`. Expected: all PASS.
- [ ] **Step 3:** Commit on the branch. Open a PR. Don't merge; B7 does that.

### Task B7: Go live with the run

- [ ] **Step 1: Ask Ben, then:**
  - create the public gist (`gh gist create --public snapshot.json`) and save its id to `E:\seti_staging\state\gist_id.txt`
  - fill `GIST_RAW` in `api/listen.js`
  - push seti-hunter publicly
  - merge the `listen-wing` PR
- [ ] **Step 2:** Register `scripts/daily_export.ps1` in Task Scheduler (daily, 06:00 local).
- [ ] **Step 3:** Retire the old surface. Delete `generate_html_dashboard`, `scan_cell_html` and `VERDICT_BADGES` from `run_survey.py`, plus the root `dashboard.html` and its `.gitignore` line. Run the existing benchmarks to confirm nothing else used them.
- [ ] **Step 4:** After the first publish, check production: `curl https://www.brokenbranch.dev/api/listen` returns schema 1 with `mode:"MEASURED"`, and `/listen/` renders with the MEASURED badge. Drive the page once more in the browser at 375 px. Record the check in a seal.
