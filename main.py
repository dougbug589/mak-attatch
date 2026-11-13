#!/usr/bin/env python3
"""Run the desktop GUI from a source checkout (installed command: mak-attatch)."""
import os
import sys

# Allow running from anywhere, e.g. /usr/lib/mak-attatch/main.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mak_attatch.main import main  # noqa: E402

if __name__ == "__main__":
    main()
