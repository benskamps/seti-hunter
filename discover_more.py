import urllib.request
import json

queries = [
    "target=VOYAGER&file-types=HDF5,filterbank",
    "target=KIC8462852&file-types=HDF5,filterbank&limit=100",
    "target=TRAPPIST&file-types=HDF5,filterbank&limit=100",
    "target=OUMUAMUA&file-types=HDF5,filterbank&limit=100",
    "target=GJ144&file-types=HDF5,filterbank&limit=100",
    "target=HIP36208&file-types=HDF5,filterbank&limit=100",
    "target=LHS292&file-types=HDF5,filterbank&limit=100",
    "target=KEPLER&file-types=HDF5,filterbank&limit=100",
    "target=SGR&file-types=HDF5,filterbank&limit=100",
    "target=ALPHA&file-types=HDF5,filterbank&limit=50",
    "target=CEN&file-types=HDF5,filterbank&limit=50",
    "target=ROSS&file-types=HDF5,filterbank&limit=50",
    "target=VEGA&file-types=HDF5,filterbank&limit=50",
    "target=SIRIUS&file-types=HDF5,filterbank&limit=50",
    "target=TAU&file-types=HDF5,filterbank&limit=50",
    "target=TEEGARDEN&file-types=HDF5,filterbank&limit=50",
    "target=51PEG&file-types=HDF5,filterbank&limit=50",
    "target=HD&file-types=HDF5,filterbank&limit=50",
]

for q in queries:
    url = f"http://seti.berkeley.edu/opendata/api/query-files?{q}"
    try:
        req = urllib.request.urlopen(url, timeout=15)
        data = json.loads(req.read().decode()).get("data", [])
        print(f"=== {q} -> {len(data)} files ===")
        for f in data[:8]:
            sz_mb = f.get("size", 0) / (1024 * 1024)
            print(f"  {str(f.get('target')):20s} | {sz_mb:8.1f} MB | {str(f.get('file_type')):10s} | {str(f.get('center_freq')):10s} | {f.get('url')}")
    except Exception as e:
        print(f"{q}: {e}")
