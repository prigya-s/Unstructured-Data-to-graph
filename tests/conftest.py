"""Puts src/ on sys.path the same way src/main.py does, so tests can import
`config`, `providers`, `pipeline`, `review`, etc. as top-level packages."""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))
