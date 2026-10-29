"""Make the mounted pipeline scripts importable before test-module collection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
