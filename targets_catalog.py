"""
Curated catalog of Breakthrough Listen Open Data Archive targets for SETI Weirdness Hunting.
Each Stage 1 entry lists its full ON/OFF cadence (A = target, B/C/D = OFF pointings) where the
archive has one, plus high-interest exoplanet, interstellar object, and Galactic Center observations.
"""


def _scan(role: str, label: str, url: str, size_mb: float) -> dict:
    return {"role": role, "label": label, "url": url, "size_mb": size_mb}


TABBY = "https://bldata.berkeley.edu/pipeline/AGBT17A_999_68/holding/spliced_blc2021222324252627_guppi_57898_"
OUMU = "https://bldata.berkeley.edu/pipeline/AGBT17B_999_75/holding/spliced_blc0001020304050607_guppi_58100_"
TRAP = "http://blpd0.ssl.berkeley.edu/trappist/blc00_guppi_57807_"
SGRB2 = "https://bldata.berkeley.edu/pipeline/AGBT18B_999_01/holding/spliced_blc0001020304050607_guppi_58331_"
EPSERI = "https://bldata.berkeley.edu/pipeline/AGBT16B_999_20/holding/spliced_blc0001020304050607_guppi_57635_"
KEPL = "https://bldata.berkeley.edu/pipeline/AGBT18A_999_30/holding/spliced_blc1011121314151617_guppi_58202_"

# Each cadence lists its scans in observing order, found with the BL open-data API
# (query-files?target=...) and the archive's holding/ directory listings on 2026-10-16.
# Stage 1 scores the first ON scan against the first OFF scan; the cadence check
# (cadence_check.py) then tests every Stage 1 candidate in every scan listed here.
# "cadence" is "ABABAB" (3 ON / 3 OFF), "ABAB" (2 ON / 2 OFF) or "single-pointing" (no OFF).
STAGE1_CADENCES = [
    {
        "cadence_id": "tabbys_star_sband",
        "name": "Tabby's Star (KIC 8462852)",
        "category": "Megastructure / Dipper Anomaly Candidate",
        "description": "Boyajian's Star, the F-type star with irregular dimming up to 22%. GBT S-band (2.27 GHz), full 6-scan ON/OFF cadence (scans 0031-0036, MJD 57898).",
        "cadence": "ABABAB",
        # OFF-present carrier from the 2026-10-15 run (OFF SNR 3897, zero drift); the cadence
        # check must call it RFI. Each target also gets its strongest OFF_1 carrier as a control.
        "known_rfi": [{"peak_freq_mhz": 2193.5658, "drift_rate_hz_s": 0.0}],
        "scans": [
            _scan("ON", "ON_1 (Scan 0031)", TABBY + "22410_DIAG_KIC8462852_0031.gpuspec.0002.h5", 229.7),
            _scan("OFF", "OFF_1 (Scan 0032)", TABBY + "22733_DIAG_KIC8462852_OFF_0032.gpuspec.0002.h5", 230.0),
            _scan("ON", "ON_2 (Scan 0033)", TABBY + "23056_DIAG_KIC8462852_0033.gpuspec.0002.h5", 229.7),
            _scan("OFF", "OFF_2 (Scan 0034)", TABBY + "23379_DIAG_KIC8462852_OFF_0034.gpuspec.0002.h5", 230.0),
            _scan("ON", "ON_3 (Scan 0035)", TABBY + "23702_DIAG_KIC8462852_0035.gpuspec.0002.h5", 231.1),
            _scan("OFF", "OFF_3 (Scan 0036)", TABBY + "24026_DIAG_KIC8462852_OFF_0036.gpuspec.0002.h5", 230.3),
        ],
    },
    {
        "cadence_id": "oumuamua_interstellar",
        "name": "1I/'Oumuamua (Interstellar Visitor)",
        "category": "Interstellar Object",
        "description": "First known interstellar object in the Solar System, with non-gravitational acceleration and an extreme aspect ratio. GBT S-band (2.27 GHz), full 6-scan cadence (scans 0011-0016, MJD 58100). The .h5 file names do not say OFF, but the archive's .fil copies label 0012/0014/0016 OFF and their RA/Dec are offset from the tracked object.",
        "cadence": "ABABAB",
        "scans": [
            _scan("ON", "ON_1 (Scan 0011)", OUMU + "78802_OUMUAMUA_0011.gpuspec.0002.h5", 230.1),
            _scan("OFF", "OFF_1 (Scan 0012)", OUMU + "79116_OUMUAMUA_0012.gpuspec.0002.h5", 230.1),
            _scan("ON", "ON_2 (Scan 0013)", OUMU + "79430_OUMUAMUA_0013.gpuspec.0002.h5", 230.1),
            _scan("OFF", "OFF_2 (Scan 0014)", OUMU + "79744_OUMUAMUA_0014.gpuspec.0002.h5", 230.2),
            _scan("ON", "ON_3 (Scan 0015)", OUMU + "80058_OUMUAMUA_0015.gpuspec.0002.h5", 230.0),
            _scan("OFF", "OFF_3 (Scan 0016)", OUMU + "80372_OUMUAMUA_0016.gpuspec.0002.h5", 230.1),
        ],
    },
    {
        "cadence_id": "trappist1_exoplanets",
        "name": "TRAPPIST-1 (7-Planet Resonant System)",
        "category": "Habitable-Zone Multi-Planet System",
        "description": "Ultracool dwarf 40 light-years away with seven temperate terrestrial planets (three in the habitable zone) in a resonance chain. GBT 2.16 GHz (compute node blc00), 4-scan ON/OFF/ON/OFF cadence (scans 0015-0018, MJD 57807). The session moved to 3.06 GHz after scan 0018, so there is no third ON at this frequency.",
        "cadence": "ABAB",
        "scans": [
            _scan("ON", "ON_1 (Scan 0015)", TRAP + "75725_DIAG_TRAPPIST1_0015.gpuspec.0002.fil", 13.8),
            _scan("OFF", "OFF_1 (Scan 0016)", TRAP + "75805_DIAG_TRAPPIST1_OFF_0016.gpuspec.0002.fil", 13.8),
            _scan("ON", "ON_2 (Scan 0017)", TRAP + "75885_DIAG_TRAPPIST1_0017.gpuspec.0002.fil", 13.8),
            _scan("OFF", "OFF_2 (Scan 0018)", TRAP + "75965_DIAG_TRAPPIST1_OFF_0018.gpuspec.0002.fil", 13.8),
        ],
    },
    {
        "cadence_id": "galactic_center_sgrb2",
        "name": "Galactic Center (Sagittarius B2)",
        "category": "Galactic Center Schelling Point",
        "description": "Massive molecular cloud complex near Sgr A* at the Milky Way's core, a Schelling point for pan-galactic beacons. GBT S-band (2.27 GHz). No cadence: scans 0013 (~1 min) and 0014 (~20 min) point at the same RA/Dec, and the archive has no OFF scan for this session. Nothing here can be sky-localized, so every candidate is UNTESTED.",
        "cadence": "single-pointing",
        "scans": [
            _scan("ON", "ON_1 (Scan 0013)", SGRB2 + "12314_DIAG_SGR_B2_0013.gpuspec.0002.h5", 45.5),
            _scan("ON", "ON_2 (Scan 0014, same pointing)", SGRB2 + "12383_DIAG_SGR_B2_0014.gpuspec.0002.h5", 461.7),
        ],
    },
    {
        "cadence_id": "nearby_exoplanet_hosts",
        "name": "Epsilon Eridani (GJ 144)",
        "category": "Solar Neighborhood Exoplanet Host (10.5 ly)",
        "description": "Epsilon Eridani (10.5 ly), the closest young solar analog with a planet and a debris belt. GBT S-band (2.30 GHz), full ABACAD cadence on MJD 57635: GJ 144 scans 0003/0005/0007, with HIP 15477, HIP 15480 and HIP 15598 as the three OFF pointings. Before 2026-10-16 this entry paired GJ 144 with a scan of LHS 292 taken ~207 days later.",
        "cadence": "ABABAB",
        "scans": [
            _scan("ON", "GJ 144 (Scan 0003)", EPSERI + "34975_Gj144_0003.gpuspec.0002.h5", 251.6),
            _scan("OFF", "HIP 15477 (Scan 0004)", EPSERI + "35316_Hip15477_0004.gpuspec.0002.h5", 251.5),
            _scan("ON", "GJ 144 (Scan 0005)", EPSERI + "35657_Gj144_0005.gpuspec.0002.h5", 251.5),
            _scan("OFF", "HIP 15480 (Scan 0006)", EPSERI + "35998_Hip15480_0006.gpuspec.0002.h5", 251.6),
            _scan("ON", "GJ 144 (Scan 0007)", EPSERI + "36340_Gj144_0007.gpuspec.0002.h5", 251.3),
            _scan("OFF", "HIP 15598 (Scan 0008)", EPSERI + "36680_Hip15598_0008.gpuspec.0002.h5", 251.3),
        ],
    },
    {
        "cadence_id": "kepler_transit_pair",
        "name": "Kepler-992b vs. Kepler-738b (L-Band Water Hole 1.475 GHz)",
        "category": "Kepler Transiting Exoplanets (Water Hole Band)",
        "description": "L-band observations centered at 1475 MHz inside the 'Water Hole' (between the 1420 MHz H I line and the 1665 MHz OH lines). 4-scan cadence on MJD 58202: Kepler-992b scans 0010/0012 as ON, interleaved with Kepler-738b scans 0011/0013 as OFF. The session moved to Kepler-1039b after scan 0013, so there is no third ON.",
        "cadence": "ABAB",
        "scans": [
            _scan("ON", "Kepler-992b (Scan 0010)", KEPL + "43003_kepler992b_0010.gpuspec.0002.h5", 233.0),
            _scan("OFF", "Kepler-738b (Scan 0011)", KEPL + "43360_kepler738b_0011.gpuspec.0002.h5", 233.2),
            _scan("ON", "Kepler-992b (Scan 0012)", KEPL + "43848_kepler992b_0012.gpuspec.0002.h5", 234.3),
            _scan("OFF", "Kepler-738b (Scan 0013)", KEPL + "44201_kepler738b_0013.gpuspec.0002.h5", 234.0),
        ],
    },
]


def scans_with_role(cadence: dict, role: str) -> list[dict]:
    return [s for s in cadence["scans"] if s["role"] == role]


# Stage 2 Heavy Fine-Resolution Targets (14-16 GB per file, Hz-level spectral resolution)
STAGE2_FINE_RES_QUEUE = [
    {
        "name": "Proxima Centauri (Parkes UWB Fine-Res 3.0 GHz)",
        "on_url": "http://blpd8.ssl.berkeley.edu/dl2/Parkes_57941_36956_PROXCEN_S_fine.h5",
        "off_url": "http://blpd8.ssl.berkeley.edu/dl2/Parkes_57941_37302_PROXCEN_R_fine.h5",
        "size_mb": 14258.0,
    },
    {
        "name": "Alpha Centauri (Parkes UWB Fine-Res 3.0 GHz)",
        "on_url": "http://blpd8.ssl.berkeley.edu/dl2/Parkes_57943_36900_ALPHACEN_S_fine.h5",
        "off_url": "http://blpd8.ssl.berkeley.edu/dl2/Parkes_57943_37242_ALPHACEN_R_fine.h5",
        "size_mb": 14707.0,
    },
    {
        "name": "Tau Ceti / HIP 8102 (Parkes Fine-Res 3.0 GHz)",
        "on_url": "http://blpd8.ssl.berkeley.edu/dl2/Parkes_58031_47052_HIP8102_S_fine.h5",
        "off_url": "http://blpd8.ssl.berkeley.edu/dl2/Parkes_58031_47392_HIP8102_R_fine.h5",
        "size_mb": 14370.1,
    },
    {
        "name": "TRAPPIST-1 Fine-Resolution Filterbank (GBT 2.16 GHz)",
        "on_url": "http://blpd0.ssl.berkeley.edu/trappist/blc00_guppi_57807_75725_DIAG_TRAPPIST1_0015.gpuspec.0000.fil",
        "off_url": "http://blpd0.ssl.berkeley.edu/trappist/blc00_guppi_57807_75805_DIAG_TRAPPIST1_OFF_0016.gpuspec.0000.fil",
        "size_mb": 768.0,
    },
    {
        "name": "Tabby's Star Fine-Resolution (GBT 2.27 GHz)",
        "on_url": "https://bldata.berkeley.edu/pipeline/AGBT17A_999_68/holding/spliced_blc2021222324252627_guppi_57898_22410_DIAG_KIC8462852_0031.gpuspec.0000.h5",
        "off_url": "https://bldata.berkeley.edu/pipeline/AGBT17A_999_68/holding/spliced_blc2021222324252627_guppi_57898_22733_DIAG_KIC8462852_OFF_0032.gpuspec.0000.h5",
        "size_mb": 14894.5,
    },
]
