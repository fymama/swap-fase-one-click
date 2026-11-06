#!/usr/bin/env python3
"""App entrypoint — launches the guided local face-swap desktop app.

The app can be opened with no arguments; choose a target photo in the window.
For automated launches an optional photo may still be passed:

    python run.py --target path/to/face.jpg
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from swapfase.app import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
