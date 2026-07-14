import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


RUNTIME = Path(__file__).resolve().parents[2] / "runtime"
sys.path.insert(0, str(RUNTIME))

from virtual_cursor_overlay import (
    HOTSPOT_X,
    HOTSPOT_Y,
    WINDOW_HEIGHT,
    frame_origin_for_point,
    process_is_running,
    read_state,
    screen_geometry_for_frames,
)


class OverlayGeometryTest(unittest.TestCase):
    def test_quartz_mapping_uses_primary_screen_top_with_screen_above(self):
        frames = [
            (0.0, 0.0, 1440.0, 900.0),
            (0.0, 900.0, 1440.0, 900.0),
            (-1200.0, 0.0, 1200.0, 800.0),
            (1440.0, -200.0, 1000.0, 800.0),
        ]
        above = screen_geometry_for_frames(100, -450, frames)
        self.assertEqual(-900.0, above["top_y"])
        self.assertEqual(900.0, above["appkit_y"])
        self.assertEqual(
            (
                100.0 - HOTSPOT_X,
                900.0 - (-450.0) - WINDOW_HEIGHT + HOTSPOT_Y,
            ),
            frame_origin_for_point(100, -450, frames),
        )

        left = screen_geometry_for_frames(-100, 100, frames)
        self.assertEqual(-1200.0, left["appkit_x"])

        below_right = screen_geometry_for_frames(1500, 500, frames)
        self.assertEqual(-200.0, below_right["appkit_y"])

    def test_malformed_state_is_invalid_instead_of_origin_cursor(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cursor.json"
            path.write_text("not-json", encoding="utf-8")
            self.assertIsNone(read_state(path))
            path.write_text(json.dumps({"x": "bad", "y": 1}), encoding="utf-8")
            self.assertIsNone(read_state(path))

    def test_launchd_and_invalid_pids_are_never_overlay_owners(self):
        self.assertFalse(process_is_running(1))
        self.assertFalse(process_is_running(0))
        self.assertFalse(process_is_running(-1))


if __name__ == "__main__":
    unittest.main()
