import sys
from pathlib import Path

# Make the src-layout package importable when this file is run directly or
# double-clicked. Installing the project or setting PYTHONPATH is not required.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sharenet.app import main

if __name__ == "__main__":
    raise SystemExit(main())
