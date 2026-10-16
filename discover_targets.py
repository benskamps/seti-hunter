import urllib.request
import json

targets = [
    ("Voyager1", "VOYAGER"),
    ("TabbysStar_KIC8462852", "KIC8462852"),
    ("Trappist1", "TRAPPIST"),
    ("Oumuamua", "OUMUAMUA"),
    ("ProximaCen_HIP70890", "HIP70890"),
    ("TauCeti_HIP8102", "HIP8102"),
    ("Ross128_HIP57548", "HIP57548"),
    ("EpsilonEridani_GJ144", "GJ144"),
    ("LuytenStar_HIP36208", "HIP36208"),
    ("Kapteyn_HIP24186", "HIP24186"),
    ("LHS_M_Dwarfs", "LHS"),
    ("Kepler", "KEPLER"),
    ("FRB", "FRB"),
    ("GalacticCenter_SGR", "SGR"),
    ("61Cygni_HIP104214", "HIP104214"),
    ("BarnardsStar_HIP87937", "HIP87937"),
    ("Wolf359", "WOLF"),
    ("Gliese", "GJ"),
]

for label, q in targets:
    url = f"http://seti.berkeley.edu/opendata/api/query-files?target={q}&limit=50"
    try:
        req = urllib.request.urlopen(url, timeout=15)
        data = json.loads(req.read().decode()).get("data", [])
        h5_fil = [f for f in data if f.get("file_type") in ("HDF5", "filterbank")]
        print(f"=== {label:24s} ({q}): {len(h5_fil)} HDF5/fil of {len(data)} returned ===")
        for f in h5_fil[:4]:
            sz_mb = f.get("size", 0) / (1024 * 1024)
            tname = str(f.get("target"))
            ftype = str(f.get("file_type"))
            cfreq = str(f.get("center_freq"))
            furl = str(f.get("url"))
            print(f"  {tname:22s} | {sz_mb:8.1f} MB | {ftype:10s} | {cfreq:8s} MHz | {furl}")
    except Exception as e:
        print(f"{label}: {e}")
