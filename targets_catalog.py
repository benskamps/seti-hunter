"""
Curated catalog of Breakthrough Listen Open Data Archive targets for SETI Weirdness Hunting.
Includes paired ON-target (A) and OFF-target (B/C/D) cadences where available, plus high-interest
exoplanet, interstellar object, and Galactic Center observations.
"""

STAGE1_CADENCES = [
    {
        "cadence_id": "tabbys_star_sband",
        "name": "Tabby's Star (KIC 8462852)",
        "category": "Megastructure / Dipper Anomaly Candidate",
        "description": "Boyajian's Star — famous F-type star exhibiting irregular 22% dimming depths. Green Bank Telescope S-band (2.27 GHz) ON/OFF pair.",
        "on_files": [
            {
                "label": "ON_1 (Scan 0031)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT17A_999_68/holding/spliced_blc2021222324252627_guppi_57898_22410_DIAG_KIC8462852_0031.gpuspec.0002.h5",
                "size_mb": 229.7,
            },
            {
                "label": "ON_2 (Scan 0033)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT17A_999_68/holding/spliced_blc2021222324252627_guppi_57898_23056_DIAG_KIC8462852_0033.gpuspec.0002.h5",
                "size_mb": 229.7,
            },
        ],
        "off_files": [
            {
                "label": "OFF_1 (Scan 0032)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT17A_999_68/holding/spliced_blc2021222324252627_guppi_57898_22733_DIAG_KIC8462852_OFF_0032.gpuspec.0002.h5",
                "size_mb": 230.0,
            },
            {
                "label": "OFF_2 (Scan 0034)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT17A_999_68/holding/spliced_blc2021222324252627_guppi_57898_23379_DIAG_KIC8462852_OFF_0034.gpuspec.0002.h5",
                "size_mb": 230.0,
            },
        ],
    },
    {
        "cadence_id": "oumuamua_interstellar",
        "name": "1I/'Oumuamua (Interstellar Visitor)",
        "category": "Interstellar Object",
        "description": "First detected interstellar object passing through the Solar System, exhibiting non-gravitational acceleration and extreme aspect ratio. GBT S-band (2.27 GHz) cadence.",
        "on_files": [
            {
                "label": "ON_1 (Scan 0011)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT17B_999_75/holding/spliced_blc0001020304050607_guppi_58100_78802_OUMUAMUA_0011.gpuspec.0002.h5",
                "size_mb": 230.1,
            },
            {
                "label": "ON_2 (Scan 0013)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT17B_999_75/holding/spliced_blc0001020304050607_guppi_58100_79430_OUMUAMUA_0013.gpuspec.0002.h5",
                "size_mb": 230.1,
            },
        ],
        "off_files": [
            {
                "label": "OFF_1 (Scan 0012)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT17B_999_75/holding/spliced_blc0001020304050607_guppi_58100_79116_OUMUAMUA_0012.gpuspec.0002.h5",
                "size_mb": 230.1,
            },
            {
                "label": "OFF_2 (Scan 0014)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT17B_999_75/holding/spliced_blc0001020304050607_guppi_58100_79744_OUMUAMUA_0014.gpuspec.0002.h5",
                "size_mb": 230.2,
            },
        ],
    },
    {
        "cadence_id": "trappist1_exoplanets",
        "name": "TRAPPIST-1 (7-Planet Resonant System)",
        "category": "Habitable-Zone Multi-Planet System",
        "description": "Ultracool dwarf 40 light-years away hosting seven temperate terrestrial planets (three in the habitable zone) in a tight orbital resonance chain.",
        "on_files": [
            {
                "label": "ON_1 (Scan 0015)",
                "url": "http://blpd0.ssl.berkeley.edu/trappist/blc00_guppi_57807_75725_DIAG_TRAPPIST1_0015.gpuspec.0002.fil",
                "size_mb": 13.8,
            },
            {
                "label": "ON_2 (Scan 0017)",
                "url": "http://blpd0.ssl.berkeley.edu/trappist/blc00_guppi_57807_75885_DIAG_TRAPPIST1_0017.gpuspec.0002.fil",
                "size_mb": 13.8,
            },
            {
                "label": "ON_3 (Scan 0020)",
                "url": "http://blpd0.ssl.berkeley.edu/trappist/blc00_guppi_57807_76582_DIAG_TRAPPIST1_0020.gpuspec.0002.fil",
                "size_mb": 13.8,
            },
        ],
        "off_files": [
            {
                "label": "OFF_1 (Scan 0016)",
                "url": "http://blpd0.ssl.berkeley.edu/trappist/blc00_guppi_57807_75805_DIAG_TRAPPIST1_OFF_0016.gpuspec.0002.fil",
                "size_mb": 13.8,
            },
            {
                "label": "OFF_2 (Scan 0018)",
                "url": "http://blpd0.ssl.berkeley.edu/trappist/blc00_guppi_57807_75965_DIAG_TRAPPIST1_OFF_0018.gpuspec.0002.fil",
                "size_mb": 13.8,
            },
            {
                "label": "OFF_3 (Scan 0021)",
                "url": "http://blpd0.ssl.berkeley.edu/trappist/blc00_guppi_57807_76662_DIAG_TRAPPIST1_OFF_0021.gpuspec.0002.fil",
                "size_mb": 13.8,
            },
        ],
    },
    {
        "cadence_id": "galactic_center_sgrb2",
        "name": "Galactic Center (Sagittarius B2)",
        "category": "Galactic Center Schelling Point",
        "description": "Massive molecular cloud complex near the supermassive black hole Sgr A* at the Milky Way's core — the premier gravitational/sky Schelling point for pan-galactic beacons.",
        "on_files": [
            {
                "label": "ON_1 (Scan 0013)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT18B_999_01/holding/spliced_blc0001020304050607_guppi_58331_12314_DIAG_SGR_B2_0013.gpuspec.0002.h5",
                "size_mb": 45.5,
            },
            {
                "label": "ON_2 (Scan 0013 Fine-Time)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT18B_999_01/holding/spliced_blc0001020304050607_guppi_58331_12314_DIAG_SGR_B2_0013.gpuspec.8.0001.h5",
                "size_mb": 206.2,
            },
        ],
        "off_files": [
            {
                "label": "REF_2 (Scan 0014)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT18B_999_01/holding/spliced_blc0001020304050607_guppi_58331_12383_DIAG_SGR_B2_0014.gpuspec.0002.h5",
                "size_mb": 461.7,
            }
        ],
    },
    {
        "cadence_id": "nearby_exoplanet_hosts",
        "name": "Epsilon Eridani (GJ 144) vs. LHS 292 (OFF)",
        "category": "Solar Neighborhood Exoplanet Host (10.5 ly)",
        "description": "Epsilon Eridani (10.5 ly, closest young solar analog with planet & debris belt) scored against an OFF scan of LHS 292 (nearby M-dwarf flare star) on the GBT S-band receiver. Caveat: the ON scan (MJD 57635, AGBT16B) and OFF scan (MJD 57842, AGBT17A) are ~207 days apart, so this is a cross-epoch pair, not a cadence; RFI present in only one epoch survives the veto.",
        # run_survey.py scores on_files[0] vs off_files[0] only; the Luyten's Star
        # scan below is listed but never downloaded or scored.
        "on_files": [
            {
                "label": "Epsilon Eridani (Scan 0003)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT16B_999_20/holding/spliced_blc0001020304050607_guppi_57635_34975_Gj144_0003.gpuspec.0002.h5",
                "size_mb": 251.6,
            },
            {
                "label": "Luyten's Star (Scan 0017)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT17A_999_14/holding/spliced_blc0001020304050607_guppi_57810_10031_HIP36208_0017.gpuspec.0002.h5",
                "size_mb": 257.3,
            },
        ],
        "off_files": [
            {
                "label": "LHS 292 Reference (Scan 0038)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT17A_999_36/holding/spliced_blc0001020304050607_guppi_57842_09544_LHS292_0038.gpuspec.0002.h5",
                "size_mb": 257.1,
            },
        ],
    },
    {
        "cadence_id": "kepler_transit_pair",
        "name": "Kepler-992b & Kepler-738b (L-Band Water Hole 1.475 GHz)",
        "category": "Kepler Transiting Exoplanets (Water Hole Band)",
        "description": "L-band observations centered at 1475 MHz right inside the 'Water Hole' (between the 1420 MHz H I neutral hydrogen line and 1665 MHz OH hydroxyl lines). Scored as a single ON/OFF pair: Kepler-992b scan 0010 vs. Kepler-738b scan 0011 (the second Kepler-992b scan is not used).",
        "on_files": [
            {
                "label": "Kepler-992b (Scan 0010)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT18A_999_30/holding/spliced_blc1011121314151617_guppi_58202_43003_kepler992b_0010.gpuspec.0002.h5",
                "size_mb": 233.0,
            },
            {
                "label": "Kepler-992b (Scan 0012)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT18A_999_30/holding/spliced_blc1011121314151617_guppi_58202_43848_kepler992b_0012.gpuspec.0002.h5",
                "size_mb": 234.3,
            },
        ],
        "off_files": [
            {
                "label": "Kepler-738b (Scan 0011)",
                "url": "https://bldata.berkeley.edu/pipeline/AGBT18A_999_30/holding/spliced_blc1011121314151617_guppi_58202_43360_kepler738b_0011.gpuspec.0002.h5",
                "size_mb": 233.2,
            },
        ],
    },
]

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
