# Dyson-sphere search plan: waste heat around the Breakthrough Listen stars

**Date:** 2026-10-17 · **Status:** plan only, nothing built · **Author:** Claude (Opus 5.5), one bounded research session · **For:** Ben

**Consumer:** Ben reads this once to decide whether this goes ahead, and in what shape (§9). If it goes ahead, the first build session reads §5 and §6 as its brief. No dashboard or index is created by this document.

**Citation rule:** every factual claim carries a numbered source from §11, and I opened every source listed there (usually the arXiv abstract page). Anything I could not verify is marked **[unverified]**. Numbers I computed myself are marked **[computed]**, with the script named. Probe results from this session are marked **[probe]**.

---

## 0. The answer in one screen

- **Recommended first step:** one bounded session (§10, M1). Resolve the 1,133 Green Bank stars to Gaia DR3 IDs and do a proper-motion-correct cross-match to 2MASS, AllWISE, unWISE/CatWISE and NEOWISE. Then run the frozen IR ladder (§4) on two control sets before any real target:
  - **positive controls:** known debris disks in the sample (η Crv, Vega, Fomalhaut, ε Eri);
  - **external test set:** the Project Hephaistos candidates, which the literature has since largely eliminated.
- **Why this sample is the right one:** the field's main failure mode is a faint background dusty galaxy hiding inside WISE's 6–12″ beam. That failure mode shrinks dramatically for nearby, bright stars, and the Green Bank sample is all within 50 pc (median 22 pc) **[probe]**.
- **The novel angle:** a per-star **joint table**. For each star it gives the largest waste-heat covering fraction WISE still allows and the narrowband radio EIRP limit seti-hunter is measuring.
  - **Feasible, and cheap.** A full-sample cross-match took ~15 s **[probe]**.
  - **Three real snags** (§6): positions need proper-motion propagation; W1/W2 are saturated for almost every star; 16 stars are too bright for Gaia.
- **Expected outcome:** a **limit**, not a detection.
  - Rough sensitivity: covering fractions down to ~10⁻⁴ (Sun-like stars) to ~10⁻³ (M dwarfs) for 100–600 K swarms **[computed]**.
  - Publishable as its own short RNAAS note that cites seti-hunter, or as a section of it (Ben's call, §9).

---

## 1. Prior art: what was done, what it found, what eliminated it

### 1.1 IRAS era: Carrigan 2009
- **Method:** fit 100–600 K blackbodies to IRAS Low Resolution Spectrometer data for ~250,000 IRAS sources over 96% of the sky [1].
- **Result:** after removing natural mimics, "very few" ambiguous candidates remained, and upper limits were set for full and partial spheres. The search could reach Sun-luminosity spheres out to ~300 pc (~10⁶ solar-type stars) [1].
- **What eliminated candidates:** known stellar mimics (dusty evolved stars and the like), identified per source [1].

### 1.2 Ĝ ("G-HAT"), Wright et al. 2014–2016
- **Paper I:** motivation for "Dysonian SETI" [2]. It argues large energy use is plausible and that searching for galaxy-spanning civilizations is worthwhile.
- **Paper II:**
  - converts mid-IR photometry into limits on alien energy use;
  - names dust as the dominant false positive, and discusses telling dust from waste heat;
  - zeroth-order WISE result: Kardashev Type III civilizations are very rare locally;
  - predicts Gaia would improve circumstellar (Dyson-sphere) searches [3].
- **Paper III:** ~1×10⁵ galaxies surveyed in WISE; 563 red extended sources vetted [4].
  - None shows a civilization reprocessing >85% of its starlight into the mid-IR.
  - 50 (including Arp 220) are consistent with >50% reprocessing.
  - Everything was explained, or left for follow-up, as natural: heavy star formation, a dusty Be star (48 Lib), a young-star cluster [4].
- **Paper IV:** transiting megastructures. It lists ten ways a megastructure's silhouette, orbit or transmission could differ from a planet's, and the natural mimics of each [5].
  - KIC 12557548 and CoRoT-29 have natural explanations.
  - KIC 8462852 (Boyajian's Star) is named an "outstanding SETI target" [5].

### 1.3 Project Hephaistos (Suazo, Zackrisson, Korn, Wright et al., 2022–2026)

**Paper I (2022)** [6]: Gaia DR2 + AllWISE.
- Of ~2.7×10⁵ stars within 100 pc, fewer than ~2×10⁻⁵ could host a ~300 K sphere at 90% completion.
- The limit is ≤8×10⁻⁴ for ~2.9×10⁸ stars within 5 kpc.
- Limits weaken for less complete spheres (confusion with natural IR sources) and with distance.

**Paper II (2024)** [7]: the "7 candidates" paper. Gaia DR3 + 2MASS + AllWISE, ~5×10⁶ sources within 300 pc. The cut sequence, as reported in the paper's HTML version [7b]:

| Step | Cut | Survivors |
|---|---|---|
| 1 | within 300 pc | ~5,000,000 |
| 2 | W3 and W4 detected, contamination flag clean | ~320,000 |
| 3 | fit 220,745 Dyson-sphere models (100–700 K, covering 0.1–0.9), keep RMSE ≤ 0.2 mag | 11,243 |
| 4 | CNN rejects sources in nebular regions (W3 images) | 5,732 |
| 5 | reject Hα emission, Gaia variability, RUWE > 1.4, extended, star probability ≤ 0.9 | 5,137 |
| 6 | SNR > 3.5 in W3 and W4 | 368 |
| 7 | visual inspection: 328 blends, 29 irregular, 4 nebular removed | **7** |

- All 7 candidates are M dwarfs at 143–275 pc.
- Best fits: T = 100–275 K, covering factor γ = 0.03–0.16 [7, 7b].

**What has happened to the 7 since:**
- **Ren, Garrett & Siemion 2024** [8]:
  - three candidates (A, B, G) have radio sources offset ~4.9″, 0.4″ and 5.0″ from the Gaia position;
  - they propose that dust-obscured galaxies along the line of sight inflate W3/W4, and that this could plausibly contaminate all 7.
  - They adopt a background density of ~9×10⁻⁶ arcsec⁻² for these galaxies. **[unverified]** whether that figure is for Hot DOGs specifically or DOGs generally; it reads high for Hot DOGs.
- **Ren et al. 2025, MNRAS 538 L56** [9]: e-MERLIN + EVN resolve candidate G's radio source (VLASS J233532.86−000424.9) into three compact components, T_b > 10⁸ K. It is a radio-loud background AGN, with no radio emission at the M dwarf. **G eliminated.**
- **Ren et al. 2026 (accepted, MNRAS)** [10]: archival diagnostics on **nine** candidates. Gaia DR3 positions were propagated to the AllWISE epoch and compared with mid-IR centroids, plus deep optical/NIR imaging.
  - Significant contamination: B and C.
  - Suggestive: A. Marginal: E, F, H, J.
  - No obvious contamination: D and I.
- **Hephaistos III, Korn et al. 2026** [11]: the 7 stars plus 3 similar objects.
  - Stellar parameters show no irregularities.
  - The IR looks like transitional disks, but there are no youth signs; one target has weak Hα, probably from activity.
  - "No clear explanation" yet; JWST/ALMA needed.
- **Hephaistos IV, Zackrisson et al. 2026 (JWST/MIRI)** [12]: the excess at D and E comes from background galaxies ~1″ from each star, not from the stars. **D and E eliminated.**
  - D: z ≈ 0.9, spectrum consistent with a Hot DOG.
  - E: z ≈ 0.4, a dusty starburst.
  - Note the tension with [10], which found "no obvious contamination" at D. A 1″ interloper was below what archival data could see. **This is the most important lesson for us** (§3, rung ②).
- **Blain 2024** [13]: critique.
  - Scanning millions of stars for mid-IR excess is risky because of noise and confusion with dusty background galaxies.
  - A real near-complete sphere would dim its star and might drop it from the very optical catalogues used to select targets.

**Net:** of the 7, three (D, E, G) are eliminated by direct follow-up, and B and C carry strong contamination evidence. None is standing as a technosignature.

### 1.4 Contardo & Hogg 2024 (AJ 168)
- **Method:** a data-driven, model-free search [14]:
  - 4,898,812 FGK near-main-sequence stars with G < 16, from Gaia DR3 + 2MASS + unWISE;
  - an ensemble of ML models predicts W1/W2 from optical/NIR inputs;
  - stars that are much brighter than predicted are flagged.
- **Result:** 53 objects (a rate of 1.1×10⁻⁵), including one known extreme debris disk. The fractional IR luminosities, 0.005–0.1, are consistent with extreme debris disks and planetary collisions [14].
- **What eliminated:** cuts on model disagreement and on the objects' astronomical features [14]. The survivors are interpreted as natural dust, not technosignatures.
- **Lesson:** a W1/W2-only search sees **hot** (≳ 500 K) dust and is blind to 100–300 K waste heat. It is complementary to W3/W4 searches, not a substitute.

### 1.5 Boyajian's Star (KIC 8462852): the dimming angle
- **Boyajian et al. 2016** [15]: aperiodic dips up to ~20%, lasting 5–80 days, on an F3 V star with no significant IR excess. Their preferred explanation was a family of exocomet fragments from one breakup.
- **Marengo et al. 2015** [16]: Spitzer found no 3.6 µm excess and a sub-3σ 4.5 µm excess (0.43 ± 0.18 mJy) about two years after the events. This argues against massive collisional dust and is consistent with comets.
- **Boyajian et al. 2018** [17]: the post-Kepler dips are **chromatic** (non-grey). Data are inconsistent with optically thick occulters, and consistent with optically thin dust of grains < 1 µm.
  - **This is the decisive physics test for any dimming candidate:** an opaque engineered structure dims all colours equally, while dust reddens.
- **Radio:** the Allen Telescope Array at 1–10 GHz saw nothing above 180–300 Jy in 1 Hz channels, or 10 Jy in 100 kHz channels [18].
- **Status:** eliminated as a megastructure candidate by chromaticity, and explained as dust (the longer-term "secular" dimming remains open) [17].

### 1.6 Gaia-based "too faint for its parallax": Zackrisson et al. 2018
- **Idea:** a nearly complete sphere makes a star look farther away spectrophotometrically than its parallax says [19].
- **Search:** Gaia DR1 × RAVE DR5 found a small fraction of discrepant stars.
- **Follow-up:** the best case, TYC 6111-1162-1, is about 2× too faint and has no IR excess. It is most plausibly an unseen massive white-dwarf companion corrupting the astrometry [19].

### 1.7 2025–2026 work
- The Hephaistos follow-ups above [9–12] are the main 2025–26 results.
- **Theory:** Amiri 2026 (accepted, *Universe*) gives T_eq ∝ R_D^(−1/2) for spheres around white dwarfs and M dwarfs, and argues for low-luminosity hosts [20].
- **Natural-dust searches** with the same machinery: Luo & Liu 2026 [21] find 12 warm debris-disk candidates within 150 pc (LAMOST + Gaia + WISE SED fits). They use **NEOWISE W1/W2 non-variability** as support for a circumstellar origin, a check we reuse in rung ⑤.
- **[unverified]** I ran two searches for other 2025–26 Dyson-sphere papers and found none beyond these. That is not proof none exist.
- I also found **no published search combining IR waste-heat limits with Breakthrough Listen radio limits on the same stars** (two searches). That supports the novelty of §6, but it is absence of evidence. The Breakthrough Listen "exotica catalogue" [22] lists "Anomaly" targets, but its abstract does not say whether IR-excess stars are among them.

### 1.8 The three strongest prior results
1. **Hephaistos I limits** [6]: ≤2×10⁻⁵ of stars within 100 pc host a 90%-complete ~300 K sphere. This is the benchmark population limit.
2. **Contardo & Hogg** [14]: 4.9 M FGK stars, 53 hot-excess objects, all consistent with natural extreme debris disks. This is the benchmark for a model-free method.
3. **The Hephaistos contamination chain** [9, 10, 12]: VLBI, archival centroiding and JWST together eliminated or strongly suspected most of the 7 candidates. The field's real lesson is that **WISE confusion with background dusty galaxies is the dominant false positive**, and archival data alone can miss a 1″ interloper.

---

## 2. Searchable signatures, each with a physics check

All numbers in this section come from `physics.py` in this session's scratchpad. That is a blackbody star plus a blackbody swarm, energy conserved, with no reflection: the star loses a fraction f of its light, and the swarm re-emits f·L at T_ds **[computed]**.

### 2.1 Mid-IR waste-heat excess: the primary signature

**Temperature.** σT⁴ = S at 1 AU from the Sun gives **394 K** for a shell radiating outward only, and **331 K** for flat collectors radiating from both faces **[computed]**. Hotter or cooler follows T ∝ R^(−1/2) [20]. Wien peaks:

| T (K) | 100 | 300 | 600 |
|---|---|---|---|
| Peak (µm) | 29 | 9.7 | 4.8 |

So 100–600 K maps onto W4 → W3 → W2, which is why the field targets W3/W4 [3, 6, 7].

**Excess as a fraction of the photosphere** **[computed]**:

| Host | T_ds | f | W1 (3.4 µm) | W2 (4.6 µm) | W3 (12 µm) | W4 (22 µm) |
|---|---|---|---|---|---|---|
| G2V | 300 K | 10⁻³ | 1×10⁻⁴ | 3×10⁻³ | 0.59 | 2.1 |
| G2V | 100 K | 10⁻³ | ~0 | ~0 | 0.016 | 1.9 |
| G2V | 600 K | 10⁻³ | 8×10⁻³ | 0.034 | 0.31 | 0.52 |
| M3V | 300 K | 10⁻³ | 3×10⁻⁵ | 7×10⁻⁴ | 0.13 | 0.45 |
| M3V | 300 K | 10⁻² | 3×10⁻⁴ | 7×10⁻³ | 1.3 | 4.5 |

**Sanity check.** The 22 µm band sees a 0.1%-covering, 300 K swarm around a Sun-like star as a 2× excess, so waste heat is very detectable in principle. The limit is set by systematics (calibration, saturation, confusion), not by energetics.

**Minimum detectable covering fraction for a 10% excess floor** (the floor is justified empirically in §6.3) **[computed]**:
- **G2V:** f ≈ 5×10⁻⁵ at 100 K, 3×10⁻⁵ at 200 K, 5×10⁻⁵ at 300 K, 2×10⁻⁴ at 600 K.
- **M3V:** f ≈ 2×10⁻⁴ to 1×10⁻³ over the same range.

**Caveats:**
- A swarm optimised for low-entropy computation could run much colder than 100 K and escape WISE entirely [23].
- A reflective swarm returns light to the star instead of re-emitting it [23].
- Both narrow what a limit means: any limit we publish must name the 100–600 K blackbody model it assumes.

### 2.2 Optical dimming without IR re-emission
- **Physics:** energy is conserved. If a star is dimmed by δ in the optical and is not hidden by beaming or reflection, then ≈ δ·L must come out somewhere. With no WISE excess, it must emerge **below ~50–100 K** (far-IR/sub-mm) or be beamed away from us.
- **Test:** compare any secular dimming with the IR limit.
  - Dimming larger than the IR limit allows → cold, beamed, or not a sphere at all.
  - Chromatic dimming → dust, as at Boyajian's Star [17].
- **Data:**
  - Gaia DR3 mean photometry vs. Hipparcos/Tycho epochs (decades of baseline) **[unverified: per-star precision not checked]**.
  - Gaia DR4 epoch photometry. DR4 promises epoch G/BP/RP photometry and epoch astrometry, about 400 TB in total [24]. ESA's DR4 page (updated 14 Sep 2026) gives no release date; a 2025 review says "December 2026" **[unverified: seen only in a search snippet]**.
- **Prior:** low. Boyajian's Star is the only famous case, and it is dust [15–17].

### 2.3 Anomalous transit shapes
- **Physics:** a transit needs alignment, with probability ~R★/a (≈0.5% at 1 AU for a Sun-like star) **[computed, standard geometry]**. A single sample of 1,133 stars would contain only a handful of aligned systems even if every star had a swarm.
- **Signatures:** the ten megastructure-vs-planet discriminants of Ĝ IV [5]:
  - a non-circular silhouette in ingress/egress;
  - achromatic depth;
  - depth changing with time;
  - phase-curve oddities.
- **Data:** TESS light curves for the sample **[unverified: TESS coverage of these 1,133 stars not checked; the brightest are saturated in TESS and need special photometry]**.
- **Verdict:** a weak channel for this sample. Keep it as a "weird anything" side-channel, like seti-hunter's discovery channel, with no limit claimed.

### 2.4 Gaia astrometric or photometric oddities
- **Underluminous for the parallax** [19]: fails mainly through binaries corrupting the astrometry.
  - In this sample, 270 of 1,117 matched stars have RUWE > 1.4 and 79 have no RUWE **[probe]**. RUWE is mostly a binarity and brightness flag here, not a technosignature axis.
  - 16 stars have **no** Gaia DR3 source within 20″ **[probe]**. 14 are among the brightest stars in the sky (Vega, Procyon, Arcturus, Fomalhaut and others); their astrometry has to come from Hipparcos.
- **Mass:** a swarm massive enough to perturb astrometry is implausible. Astrometry constrains companions, not swarms.
- **Verdict:** use Gaia for **identity, distance and the photospheric model**, not as a detection channel. Revisit with DR4 epoch astrometry.

### 2.5 Radio leakage as a cross-check
- **Physics:** a swarm need not leak radio at all. The radio channel is therefore **independent evidence**, not a confirmation test.
- **What radio does cleanly, as a confirmation tool:** it identifies **background AGN**. That is how candidates A, B and G were contaminated or eliminated [8–10].
- **Inputs:**
  - **VLASS:** 2–4 GHz, ~2.5″ resolution, 70 µJy/beam goal, δ > −40° [25]. This is the continuum check.
  - **seti-hunter's own per-star narrowband EIRP limits.** These are the joint-table column (§6).
- **Precedent:** Price 2020's Green Bank limit for the sample is 2×10¹² W [26].

---

## 3. The false-positive zoo, and the IR rejection ladder

seti-hunter's ladder is: the same rungs in the same order, frozen before the full run, with the **first rung that eliminated** each object recorded. Untestable objects get **Untested**, not a pass. Objects that fail a re-check get **Not re-found**. The IR ladder copies all of that.

### 3.1 The zoo

| Impostor | Why it mimics waste heat | What separates it from waste heat | Our cheapest check |
|---|---|---|---|
| **WISE artifacts** (diffraction spikes, halos, ghosts, latents, saturation) | spurious W3/W4 flux near bright stars | AllWISE `ccf` flags, `ext`, `qph`; W1/W2 saturated near W1 ≈ 8, W2 ≈ 7 mag [27] | catalogue flags, then an unWISE/forced re-measure |
| **Background dusty galaxy / Hot DOG / AGN in the beam** | W3/W4 FWHM 6.5″/12″ [28] holds a faint red galaxy | WISE centroid offset from the PM-propagated Gaia position [10]; an offset radio source [8, 9]; deep optical/NIR imaging [10]; ultimately JWST [12] | centroid test, VLASS, Legacy Survey imaging |
| **Blend with another star** | a second star inside the beam | Gaia/2MASS neighbour list within 12″ | Gaia neighbour count |
| **Debris disk** | collisional dust at 50–400 K | silicate features (Spitzer IRS); resolved disk (Herschel/ALMA); literature. Example: η Crv's warm ~400 K dust at 0.2–0.8 AU plus a cold belt at 133 AU [29] | literature + IRSA Spitzer/Herschel archive |
| **YSO / transitional disk** | disk emission | youth: Hα, lithium, variability, cluster or moving-group membership. Hephaistos III used exactly this [11] | Gaia variability, Hα (Gaia), moving groups |
| **Evolved stars** (giants, AGB) | dusty winds | luminosity class from the Gaia CMD; the sample contains giants: Arcturus, Aldebaran, Kochab, Hamal, Diphda, 109 Her **[probe, SIMBAD]** | absolute magnitude cut → separate class |
| **Hot stars with free-free / Be disks** | ionized-gas IR excess | spectral type. Ĝ III found a dusty Be star [4] | spectral type from SIMBAD |
| **Interstellar dust / nebulosity / cirrus** | extended W3 emission | extended morphology. Hephaistos used a CNN [7b] | W3 image extent; our stars are nearby, so this is rare |
| **Photosphere mis-model** | a wrong Teff or a saturated anchor makes a fake "excess" | the W3−W4 colour is model-independent; check photospheric W3/W4 against a same-type control set | colour test |

### 3.2 The IR ladder (draft, to be frozen as `ladder-ir.yaml`, tag `ladder-ir-v1`)

Every star whose excess clears the threshold goes down the rungs in order. The first rung that eliminates it is recorded with a plain-English reason, as in seti-hunter's Ledger.

| Rung | Eliminates an object whose excess… | Data |
|---|---|---|
| **①** | sits on a WISE artifact or saturation flag in the band carrying the excess, or vanishes on re-measurement (unWISE / forced photometry) | AllWISE `ccf`, `ext`, `qph`; unWISE [30]; CatWISE2020 [31] |
| **②** | is offset from the PM-propagated Gaia position, has another optical/NIR/radio source within the W4 beam, or has a resolved-galaxy counterpart | Gaia DR3; Legacy Survey/Pan-STARRS imaging **[unverified: coverage per star]**; VLASS [25]; FIRST/NVSS **[not opened]** |
| **③** | has a known or archival natural-dust explanation: catalogued debris disk, silicate feature, resolved disk, youth indicators | SIMBAD/literature; IRSA Spitzer & Herschel archives |
| **④** | belongs to a star class with intrinsic IR excess (giant, AGB, Be, Wolf-Rayet) | Gaia CMD, SIMBAD spectral type |
| **⑤** | is **not re-found**: inconsistent across AllWISE vs. unWISE vs. NEOWISE epochs (W1/W2 only) [32], or vs. Spitzer where it exists | NEOWISE single-exposure table [32]; Spitzer |

**Survivors:**
- are held privately, as in seti-hunter's §5;
- get a full Dyson-sphere vs. dust SED fit and a second reviewer (Codex, graded);
- only then, and as a proposal, go to JWST/MIRI or ALMA. Hephaistos IV shows that JWST is what settles a ~1″ interloper [12].

**Rung order rationale:** cheapest and most decisive first, which is also seti-hunter's principle. Rung ② is placed before ③ on purpose. A known debris-disk star can *also* have a background galaxy in the beam, and recording the confusion first keeps the literature from hiding an instrument problem.

### 3.3 Controls that stay in every run (seti-hunter's negative-control rule, inverted)

- **Positive dust controls, which must flag and then be eliminated at ③.**
  - **η Crv:** verified warm disk [29]. In this session's dry run it flags with W3−W4 = +0.56 **[probe]**.
  - **ε Eri:** W3−W4 = +0.34 with W1/W2 saturated **[probe]**.
  - **Vega:** IRAS-discovered excess (Aumann et al. 1984) **[not opened; standard result]**.
  - **Fomalhaut:** disk **[not opened]**.
  - A run that fails to flag these controls is invalid.
- **External test set, which must be eliminated at ① or ② by our own code.**
  - **The Hephaistos candidates A–J** [7, 10]. D, E and G are known answers [9, 12].
  - If our ladder passes D or E, rung ② is too weak. That is expected for archival-only rungs [10 vs. 12], and the paper must say so honestly.
- **Injection-recovery:**
  - Add synthetic waste-heat SEDs (grid over f and T_ds) to each real star's real photometry, with its real errors and flags.
  - Run the identical pipeline. The recovery fraction against f sets the per-star limit.
  - Same philosophy as seti-hunter's planted signals.

---

## 4. Pipeline Ben can run at home

### 4.1 Catalogues

| Catalogue | Role | Access | Size for this sample |
|---|---|---|---|
| Gaia DR3 | identity, astrometry, BP/RP, RUWE, neighbours | Gaia TAP / VizieR I/355 | <1 MB |
| Hipparcos (new reduction) | astrometry for the 16 Gaia-less bright stars | VizieR **[not opened]** | <1 MB |
| 2MASS PSC | J/H/K (saturated for bright stars: Qflg D/E seen in probe) | VizieR II/246 | <1 MB |
| AllWISE | W1–W4 profile-fit photometry; 747 M sources [27] | VizieR II/328, IRSA | <1 MB |
| unWISE / CatWISE2020 | deeper W1/W2 re-measure; CatWISE has 1.89×10⁹ sources, motions, W1/W2 to 17.7/17.5 mag at 90% completeness [30, 31] | VizieR / IRSA | <1 MB |
| NEOWISE single-exposure | W1/W2 time series 2013–2024 (1.998×10¹¹ detections; survey ended 1 Aug 2024) [32] | IRSA TAP, cone per star | ~10–100 MB **[unverified estimate]** |
| VLASS | radio counterparts (AGN check) [25] | CIRADA catalogue **[not opened]** | <10 MB |
| Spitzer / Herschel / JWST archives | follow-up photometry and spectra for flagged stars only | IRSA / ESA / MAST | per-target |
| Wlodarczyk-Sroka 2020 (optional extension) | 288,315 Gaia DR2 field stars inside GBT/Parkes beams, with a min-EIRP per source; 356,616 rows, 35 columns, incl. `GaiaDR2`, `Target`, `InstS` [33] | VizieR J/MNRAS/498/5720 | ~190 MB **[estimate from byte width]** |

### 4.2 Steps
1. **Identity:** resolve each name in SIMBAD to a Gaia DR3 `source_id`. Fall back to Hipparcos for the 16 Gaia-less stars.
2. **Proper-motion-correct cross-match:** propagate each Gaia position to each catalogue's epoch (2MASS ~1997–2001, AllWISE ~2010.5, Gaia 2016.0), then match. Use Gaia's precomputed `allwise_best_neighbour` / `tmass_psc_xsc_best_neighbour` tables as a cross-check [34].
3. **Photosphere:**
   - Gaia BP/RP and literature Teff with model atmospheres, anchored on **unsaturated** bands (W1/W2 are saturated here).
   - Plus a model-independent **W3−W4 colour** test.
   - Measure the excess floor from the sample itself.
4. **Excess statistic:** χ in W3 and W4 using the measured floor, plus a W3−W4 colour outlier test.
5. **Ladder:** apply rungs ①–⑤ and record the first rung that eliminated each flagged star.
6. **Injection-recovery:** produce a per-star f_max(T_ds) for T_ds = 100–600 K.
7. **Joint table:** per star, f_max(T) next to seti-hunter's narrowband EIRP limit and VLASS continuum status.

### 4.3 Compute on one Windows machine
- **Sample size:** everything for 1,133 stars is tiny.
  - This session's whole-sample CDS X-Match ran in **6.6 s against AllWISE and 7.9 s against Gaia DR3**, through `astroquery.xmatch` **[probe]**.
  - Single cone searches take ~0.5 s each **[probe]**.
- **Speed:** the whole pipeline, injection grid included, is minutes to an hour of CPU. No GPU, no Task Scheduler runner and no agents are needed.
- **Optional 288 k field-star extension:** hours of TAP queries and still a laptop job. Most of those stars are faint and distant, so W3/W4 will mostly be upper limits **[unverified]**.
- **Not recommended:** a Hephaistos-scale 5×10⁶ search. It re-runs a crowded experiment whose failure mode (confusion) we cannot beat without JWST.

---

## 5. Physics-honest scope
- **What a limit here means:** "for star X, no non-reflective blackbody swarm at 100–600 K absorbs more than f_max(T) of its light."
- **Unconstrained:**
  - very cold (<~100 K) or reflective swarms [23];
  - near-complete spheres that would have dimmed the star out of the sample. The sample was chosen from optically bright stars, which is Blain's selection point [13].
- **Not the same quantity as Hephaistos I** [6]: theirs is a population fraction for 90%-complete spheres, ours is a per-star covering fraction.
- **Comparing the two:** state both, and convert carefully if we quote a population number (e.g. "0 of N stars host f > f_lim").

---

## 6. The novel angle: the 1,133-star Green Bank sample

### 6.1 Why it is the right sample
- **Nearby and bright:** within 50 pc (median 21.8 pc; 462 within 20 pc) **[probe, from the CSV's dist_pc]**.
- **Photospheres dwarf a background galaxy:**
  - A W4 = 5 mag star has ~83 mJy of photosphere at 22 µm; a W4 = 7 mag star ~13 mJy **[computed; W4 zero point 8.28 Jy assumed, unverified]**. The WISE W4 5σ limit is 5.4 mJy [28].
  - A mJy-level background galaxy is a few-% bump on most of these stars, not the 60× excesses Hephaistos chased.
- **Chance-coincidence count,** at the density in [8]: within a 6″ radius about 1 such galaxy is expected across all 1,133 stars, against ~5,000 across a 5 M-star sample **[computed]**.
- **The residual risk** is concentrated in the sample's faintest M dwarfs.
- **What it adds:** the radio half of a joint statement is already being measured by seti-hunter, on the same stars, by Ben, this year.

### 6.2 Feasibility probe: what I actually saw
Script `xmatch_probe.py` and `cone_probe.py` (session scratchpad, not committed) on the full CSV:

| Check | Result |
|---|---|
| Stars uploaded | 1,133 |
| AllWISE source within 20″ | **1,115** (median nearest separation 7.2″, 90th percentile 13.4″) |
| Gaia DR3 source within 20″ | **1,117**; brightest-in-20″ G at percentiles 5/50/95 = 3.5 / 7.1 / 10.3 |
| W1 < 8 mag or W1 `qph`=U (saturation regime) | **1,076** |
| `ccf` artifact flag in any band / in W3 or W4 | 467 / 197 |
| W3 and W4 both quality A/B and unflagged ("clean") | **905** |
| W3−W4 among clean stars | median **+0.07**, 95th percentile **+0.20** mag |
| Clean stars with W3−W4 > 0.5 (first dry-run flags) | **5**: η Crv (verified warm disk [29]), ζ Lep, γ Oph, 73 Her, BD−07 699 (K5V) |
| Stars with no Gaia source within 20″ | 16: Procyon, Fomalhaut, Algol, Aldebaran, Diphda, Regulus, Algieba, Denebola, Heze, Arcturus, Kochab, Sheratan, Vega, Hamal, HD 25457, HD 111631 |

**Reading the dry-run flags.** The five flags are not candidates. They are what the ladder is for.
- η Crv is a textbook warm debris disk [29], which shows the machinery sees real dust.
- ζ Lep has interferometric hints of inner circumstellar material **[unverified: seen in a search snippet only]**.
- γ Oph, 73 Her and BD−07 699 are unexamined.
- BD−07 699 carries a W1/W2 diffraction-spike flag (`ccf`=dd00), so it is a likely rung ① elimination.

### 6.3 Three snags found, each with its fix

1. **The CSV coordinates are epoch-mixed and coarse.**
   - GJ 1002 (proper motion ~2″/yr): its 2MASS counterpart (J = 8.32, K = 7.44) sits **40.8″** from the CSV position. A naive 30″ cone returns two unrelated 16th-magnitude sources instead **[probe]**.
   - **Fix:** step 4.2-2 (Gaia ID → proper-motion propagation). **Never match on the CSV coordinates directly.**
2. **W1/W2 are saturated for ~97% of the sample** (1,076/1,115) **[probe]**. 2MASS fails for the brightest stars too: ε Eri has quality DDD, and Sirius's nearest 2MASS row has J = H = K = −1.39, an obvious failure **[probe]**.
   - **Fix:** use the photosphere from Gaia and the models, plus the model-independent W3−W4 colour, which covers 100–300 K swarms (e.g. a 0.1%, 300 K swarm around a G2V moves W3−W4 by ~0.7 mag) **[computed]**.
   - 600 K swarms need the photospheric anchor, and the anchor's accuracy is the main systematic.
   - The empirical colour spread (95th percentile +0.20 mag) suggests a ~10% excess floor, which is the floor used in §2.1.
3. **Bright stars, giants, and multiple systems.**
   - 16 stars are Gaia-less, the sample includes giants, and Sirius returns two AllWISE rows flagged as artifacts **[probe]**.
   - **Fix:** a separate "bright/evolved" class with rung ④, honestly reported as **Untested** where the photometry cannot support a test.

**Verdict: feasible.** The cross-match is seconds, the data are tiny, and the limits are useful at the ~10⁻⁴–10⁻³ covering-fraction level **[computed]**. The real work is the proper-motion-correct identity step and the photospheric anchor, not compute.

### 6.4 The combined limit, stated honestly
- **What it is:** stapling the two limits does **not** tighten either one. The value is a **per-star, two-modality statement**: "around star X, no 100–600 K swarm above f_X(T), **and** no narrowband transmitter above EIRP_X during the 2016–2019 cadences."
- **Who it is for:** anyone who believes energy-rich civilizations both build and transmit. For them it is a joint occupancy table.
- **Novelty:** I found no prior paper doing this for the Breakthrough Listen sample (§1.7, two searches). Treat the novelty as **probable, not proven** until a literature check on ADS is done.
- **Optional extension:** the Wlodarczyk-Sroka catalogue [33] extends the same idea to ~288 k field stars inside the GBT beams. That needs seti-hunter to compute field-star limits too, which is a scope decision (§9).

---

## 7. What would make it publishable

| Outcome | Form | Likely venue |
|---|---|---|
| **Negative result + limits** (expected) | Table of f_max(T) per star, a joint radio+IR table, the ladder Funnel counts, and the control outcomes (debris disks recovered, Hephaistos contaminants eliminated) | A short RNAAS note of its own, cross-citing seti-hunter's. RNAAS length rules **[unverified: check the AAS author guide; I believe ~1,000 words and 1 figure]** |
| **Warm-dust census by-product** | Any stars with W3/W4 excess not in the literature | The same note. Natural-dust discoveries are a legitimate, citable result even if every one is eliminated at ③ |
| **Survivor** (unlikely) | Private review → Codex → archival Spitzer → JWST/ALMA proposal | Never announced before JWST-class confirmation. Hephaistos IV is the cautionary tale [12] |
| **Section inside seti-hunter's RNAAS** | One paragraph + one table column | Possible only if the RNAAS length budget allows **[unverified]** |

**Knuth classification of this plan's claims:**
- **EMPIRICAL:** feasibility. The probe ran on all 1,133 stars, and the saturation and epoch snags were measured.
- **EMPIRICAL (toy model):** sensitivity. Blackbody energy balance, with a 10% floor inferred from 905 stars' colour spread. It must be re-measured by injection-recovery.
- **CONJECTURE:** novelty. Two literature searches only.
- **NULL expected:** detection. Every prior candidate has collapsed to natural or background explanations [9–12, 14, 17].

---

## 8. AutoResearch discipline record

### 8.1 Five reframes
1. **Original:** "find Dyson spheres in public IR data."
2. **Dual (what guarantees failure?):** repeat Hephaistos at scale on faint, distant stars, where background galaxies win [8–13]. → Avoid faint/distant samples and broad scans.
3. **Coordinate shift:** stop counting candidates and measure **how much light each star could be hiding** (a covering-fraction limit per star). This is the unlock: a limit is a publishable product even with zero candidates.
4. **Isomorphism:** this is the warm-debris-disk census problem [14, 21, 29] with one extra rung. All of debris-disk methodology (SED fits, NEOWISE stability, silicate features) transfers directly.
5. **Minimum viable:** the 1,133 Green Bank stars. Small, nearby, already radio-limited by seti-hunter, and the cross-match runs in seconds.

### 8.2 Foundation check
- **Is the premise sound?** Waste heat must be radiated (§2.1). WISE's sensitivity to it is enormous; its weakness is confusion and calibration.
- **The foundation holds for the nearby sample. It wobbles for the broad-scan version.**
- **Uncomfortable fact:** much of this sample is well studied for debris disks, which lowers discovery odds. In exchange, it gives ready-made positive controls and archival follow-up.

### 8.3 Aggressive falsification (each with a null)
| Claim tested | Null / falsifier | Outcome |
|---|---|---|
| "Saturation makes WISE useless for this sample" | If W3/W4 were also unusable, the clean count would be near 0 | **Partly true:** W1/W2 are saturated for 1,076 stars, but 905 have clean W3+W4. The claim is falsified for the 100–300 K regime |
| "Naive cone matching is good enough" | GJ 1002 should match within 30″ | **True falsifier:** its 2MASS counterpart is 40.8″ away. Proper-motion propagation is mandatory |
| "The colour test sees real dust" | A null colour test would flag nothing, or only artifacts | It flags η Crv, a known warm disk. Machinery sensitivity is **confirmed on one control**. Vega and Fomalhaut were not testable via Gaia within 20″ |
| "Background galaxies are negligible for this sample" | Chance count ≫ 1 would falsify | ~1 expected within 6″ across the sample **[computed]**, but concentrated on faint M dwarfs. **Not negligible for those**; rung ② stays |
| "The joint radio+IR limit is novel" | Any prior paper doing it | None found in two searches; **unresolved** until an ADS check |

### 8.4 External pressure-test
- **Blain 2024's critique** [13] (noise, confusion, selection, countermeasures) is answered in §5 and §6.1, except countermeasures, which no search can answer.
- **The [10] vs. [12] disagreement on candidate D** shows that archival rung ② will under-eliminate. The plan states this rather than hiding it.
- **Not done:** a Codex pressure-test, to keep this session bounded. **Recommended before freezing `ladder-ir-v1`**, via the `codex` skill, graded per the canon.

---

## 9. Decisions that are Ben's

1. **Shape:**
   - (a) a module inside seti-hunter (`ir/`) with its own short RNAAS note — **my recommendation**: the radio limits and the dashboard are already there;
   - (b) a fully separate project;
   - (c) one section of seti-hunter's RNAAS.
2. **Scope:**
   - 1,133 stars only — **recommended first**;
   - plus the ~288 k Wlodarczyk-Sroka field stars, which needs seti-hunter field-star EIRP limits too;
   - not a Hephaistos-scale scan (§4.3).
3. **Dashboard:** add an IR Funnel and an IR column to the Ledger on brokenbranch.dev/listen/, or keep IR off the live page until the note.
4. **Survivor policy:** reuse seti-hunter's private-review rule verbatim — **recommended**.
5. **When to start:**
   - now, in parallel; it is small and touches no seti-hunter code beyond reading its limits;
   - or after seti-hunter M5 (limits), when the joint table can be filled in.
   - Either way the IR side can be built and frozen first.
6. **Dimming channel:** wait for Gaia DR4 epoch photometry (ESA gives no date yet [24]), or drop it.
7. **Wording:** confirm "eliminated" applies to IR objects exactly as to radio signals. I have used it throughout.

---

## 10. Milestones (one bounded session each, no swarms)

| M | Deliverable | Done means |
|---|---|---|
| **M0** | `ladder-ir.yaml` draft + control lists + Codex pressure-test | Rungs, thresholds and controls are written down; Codex has graded them |
| **M1** | Identity + PM-correct cross-match table for 1,133 stars + Hephaistos A–J + controls | Every star has a Gaia (or Hipparcos) ID and a match per catalogue, or an explicit "Untested" |
| **M2** | Photosphere model + excess statistic + measured floor | Floor measured from the sample; η Crv, ε Eri and Vega behave as expected |
| **M3** | Ladder run, controls first | Positive controls flagged and eliminated at ③; Hephaistos D/E/G eliminated at ①/② (or the miss reported) |
| **M4** | Injection-recovery → per-star f_max(T) | A recovery curve per star; the 10% floor replaced by the measured one |
| **M5** | Joint table with seti-hunter's EIRP limits | Needs seti-hunter M5 |
| **M6** | RNAAS draft | Ben's call on venue (§9.1) |
| *opt.* | 288 k field-star extension; Gaia DR4 dimming check | After M6 |

**Recommended first step:** M0 + M1 in one session. That freezes the ladder before any real data is scored (seti-hunter's own rule) and builds the identity table that every later step needs.

---

## 11. Sources (all opened this session unless marked)

1. Carrigan 2009, ApJ 698, 2075. *IRAS-based whole-sky upper limit on Dyson Spheres.* https://arxiv.org/abs/0811.2376
2. Wright et al. 2014, ApJ 792, 26. *Ĝ I. Background and Justification.* https://arxiv.org/abs/1408.1133
3. Wright et al. 2014, ApJ 792, 27. *Ĝ II. Framework, Strategy, and First Result.* https://arxiv.org/abs/1408.1134
4. Griffith et al. 2015, ApJS 217, 25. *Ĝ III. The Reddest Extended Sources in WISE.* https://arxiv.org/abs/1504.03418
5. Wright et al. 2016, ApJ 816, 17. *Ĝ IV. Transiting Megastructures.* https://arxiv.org/abs/1510.04606
6. Suazo et al. 2022, MNRAS (doi 10.1093/mnras/stac280). *Project Hephaistos I.* https://arxiv.org/abs/2201.11123
7. Suazo et al. 2024, MNRAS (doi 10.1093/mnras/stae1186). *Project Hephaistos II.* https://arxiv.org/abs/2405.02927 — 7b: cut table and candidate table read from https://arxiv.org/html/2405.02927v1
8. Ren, Garrett & Siemion 2024. *Background Contamination of the Project Hephaistos Dyson Spheres Candidates* (preprint). https://arxiv.org/abs/2405.14921
9. Ren et al. 2025, MNRAS 538, L56. *High-resolution imaging of the radio source associated with Candidate G.* https://arxiv.org/abs/2501.05152
10. Ren et al. 2026, accepted MNRAS (doi 10.1093/mnras/stag1558). *Archival Diagnostics for Potential Background Contaminants.* https://arxiv.org/abs/2607.03619
11. Korn et al. 2026. *Project Hephaistos III* (preprint). https://arxiv.org/abs/2607.25701
12. Zackrisson et al. 2026. *Project Hephaistos IV. JWST Observations of Two Candidates* (preprint). https://arxiv.org/abs/2607.09460
13. Blain 2024. *Did WISE detect Dyson Spheres/Structures around Gaia-2MASS-selected stars?* (preprint). https://arxiv.org/abs/2409.11447
14. Contardo & Hogg 2024, AJ 168 (doi 10.3847/1538-3881/ad6b90). https://arxiv.org/abs/2403.18941
15. Boyajian et al. 2016, MNRAS (doi 10.1093/mnras/stw218). *Where's the Flux?* https://arxiv.org/abs/1509.03622
16. Marengo, Hulsebus & Willis 2015, ApJL 814, L15. https://arxiv.org/abs/1511.07908
17. Boyajian et al. 2018, ApJL (doi 10.3847/2041-8213/aaa405). *First Post-Kepler Brightness Dips.* https://arxiv.org/abs/1801.00732
18. Harp et al. 2016, ApJ 825, 155. *Radio SETI Observations of KIC 8462852.* https://arxiv.org/abs/1511.01606
19. Zackrisson et al. 2018, ApJ (doi 10.3847/1538-4357/aac386). *SETI with Gaia.* https://arxiv.org/abs/1804.08351
20. Amiri 2026, accepted *Universe*. *Dyson spheres on H-R diagram.* https://arxiv.org/abs/2602.23270
21. Luo & Liu 2026, accepted RAA. *Warm Debris Disk Candidates around Nearby FGK Stars from LAMOST DR12.* https://arxiv.org/abs/2602.23004
22. Lacki et al. 2021. *Breakthrough Listen exotica catalogue* (abstract only; object list not checked). https://arxiv.org/abs/2006.11304
23. Wright 2020, Serbian Astronomical Journal 200, 1. *Dyson Spheres* (review; abstract only). https://arxiv.org/abs/2006.16734
24. ESA, *Gaia DR4 content* (page updated 14 Sep 2026). https://www.cosmos.esa.int/web/gaia/dr4
25. Lacy et al. 2020, PASP. *VLASS science case and survey design.* https://arxiv.org/abs/1907.01981
26. Price et al. 2020, AJ 159, 86. *BL observations of 1327 nearby stars.* https://arxiv.org/abs/1906.07750
27. IRSA, *AllWISE data release* (747 M sources; W1/W2 saturation ~8/7 mag). https://irsa.ipac.caltech.edu/data/WISE/docs/release/AllWISE/
28. IRSA, *WISE All-Sky Explanatory Supplement §1.1* (FWHM 6.1/6.4/6.5/12.0″; 5σ 0.068/0.098/0.86/5.4 mJy). https://irsa.ipac.caltech.edu/data/WISE/docs/release/All-Sky/expsup/sec1_1.html
29. Lebreton et al. 2016, ApJ. *Models of the Eta Corvi debris disk.* https://arxiv.org/abs/1511.05207
30. Schlafly, Meisner & Green 2019. *The unWISE Catalog.* https://arxiv.org/abs/1901.03337
31. Marocco et al. 2021, ApJS. *The CatWISE2020 Catalog.* https://arxiv.org/abs/2012.13084
32. IRSA, *NEOWISE data release* (survey halted 1 Aug 2024; 1.998×10¹¹ single-exposure detections). https://irsa.ipac.caltech.edu/data/WISE/docs/release/NEOWISE/
33. Wlodarczyk-Sroka, Garrett & Siemion 2020, MNRAS 498, 5720. VizieR ReadMe J/MNRAS/498/5720. https://cdsarc.cds.unistra.fr/VizieR/ftp/J/MN/498/5720/ReadMe
34. Gaia DR3 documentation, cross-match tables (seen via search listing; column definitions **not opened**). https://gea.esac.esa.int/archive/documentation/GDR3/Gaia_archive/chap_datamodel/sec_dm_cross-matches/
35. Eisenhardt et al. 2012, ApJ 755, 173. *The First Hyper-Luminous Infrared Galaxy Discovered by WISE* (prototype W1W2-dropout / Hot DOG population, ~1,000 all-sky). https://arxiv.org/abs/1208.5517

**Not opened, cited as standard knowledge only:** Aumann et al. 1984 (Vega excess); the Fomalhaut disk; FIRST/NVSS; Hipparcos new reduction; TESS coverage; the RNAAS length limit; the W4 zero point (8.28 Jy).

**Probe scripts** (`cone_probe.py`, `xmatch_probe.py`, `physics.py`) live in this session's scratchpad and are not committed. Re-creating them is part of M1.
