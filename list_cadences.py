import urllib.request
import json

for q in ["KIC8462852", "OUMUAMUA", "TRAPPIST", "GJ144", "LHS292", "KEPLER", "SGR"]:
    url = f"http://seti.berkeley.edu/opendata/api/query-files?target={q}&file-types=HDF5,filterbank&limit=100"
    req = urllib.request.urlopen(url, timeout=15)
    data = json.loads(req.read().decode()).get("data", [])
    print(f"*** {q} ({len(data)} files) ***")
    for f in data:
        sz_mb = f.get("size", 0) / (1024 * 1024)
        if sz_mb < 2000:  # medium or intermediate resolution
            print(f"  {str(f.get('target')):22s} | {sz_mb:7.1f} MB | {f.get('url')}")
