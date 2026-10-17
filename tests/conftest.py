import sys
from pathlib import Path

# Let tests import the repo's packages however pytest is launched. The fixture
# helpers are imported by bare module name: blimpy installs a top-level `tests`
# package into site-packages, so `tests.fixtures` would resolve to blimpy's.
ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "tests" / "fixtures"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
