"""Tests for lock-guarded UI state updates."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from swapfase.state import AppState  # noqa: E402


class AppStateTests(unittest.TestCase):
    def test_controls_and_status_can_be_updated(self) -> None:
        state = AppState()
        state.set_mirror(False)
        state.set_swap_enabled(False)
        state.set_status("CPUExecutionProvider", 4.5)

        self.assertEqual(state.snapshot_render_flags(), (False, False, None))
        self.assertEqual(state.status_snapshot(), ("CPUExecutionProvider", 4.5))


if __name__ == "__main__":
    unittest.main()
