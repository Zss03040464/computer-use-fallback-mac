from io import BytesIO
import unittest
from unittest.mock import patch

from PIL import Image

from runtime.cu_runtime.cursor_feedback import (
    CURSOR_AQUA_RGBA,
    CURSOR_CORE_HEIGHT,
    CURSOR_CORE_WIDTH,
    CURSOR_FILL_RGBA,
    CURSOR_STYLE,
    PULSE_DURATION_MS,
    CursorFeedback,
    composite_cursor_png,
    cursor_visual,
    render_cursor_patch,
)
from runtime.cu_runtime.targets import TargetWindow


class CursorFeedbackTest(unittest.TestCase):
    def setUp(self):
        self.target = TargetWindow(
            app="Harness",
            bundle_id="com.example.harness",
            display_name="Harness",
            path="/tmp/Harness.app",
            pid=77,
            window_id=88,
            title="Target",
            x=100,
            y=200,
            width=200,
            height=100,
        )
        image = Image.new("RGBA", (400, 200), (0, 0, 0, 255))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        self.png = buffer.getvalue()

    @staticmethod
    def feedback(**overrides):
        value = {
            "displayX": 130,
            "displayY": 225,
            "targetBundleId": "com.example.harness",
            "targetPid": 77,
            "targetWindowId": 88,
            "action": "AXPress",
            "phase": "released",
            "updatedAtMs": 1_000,
        }
        value.update(overrides)
        return CursorFeedback.from_mapping(value)

    def test_rejects_incomplete_or_unknown_phase_records(self):
        self.assertIsNone(CursorFeedback.from_mapping({"displayX": 1}))
        self.assertIsNone(self.feedback(phase="unknown"))

    def test_release_pulse_decays_to_steady(self):
        feedback = self.feedback()
        self.assertGreater(cursor_visual(feedback, 1_000).pulse, 0.9)
        settled = cursor_visual(feedback, 1_000 + PULSE_DURATION_MS + 1)
        self.assertEqual(0.0, settled.pulse)
        self.assertEqual(PULSE_DURATION_MS + 1, settled.age_ms)

    def test_v2_style_contract_uses_physical_size_and_short_bloom_decay(self):
        self.assertEqual("aqua-glass-arrow-v2", CURSOR_STYLE)
        self.assertEqual(13, CURSOR_CORE_WIDTH)
        self.assertEqual(18, CURSOR_CORE_HEIGHT)
        self.assertGreaterEqual(CURSOR_FILL_RGBA[3], 70)
        self.assertLessEqual(CURSOR_FILL_RGBA[3], 100)
        self.assertLessEqual(CURSOR_AQUA_RGBA[3], 60)
        self.assertEqual(700, PULSE_DURATION_MS)

    def test_patch_has_antialiased_soft_bloom_and_pale_core(self):
        patch, hotspot = render_cursor_patch(1.0, 0.0)
        self.assertGreater(hotspot[0], 0)
        self.assertGreater(hotspot[1], 0)

        alpha = patch.getchannel("A")
        alpha_values = list(alpha.get_flattened_data())
        self.assertTrue(any(0 < value < 40 for value in alpha_values))
        self.assertTrue(any(120 < value < 220 for value in alpha_values))
        self.assertGreaterEqual(max(alpha_values), 220)

        core_mask = alpha.point(lambda value: 255 if value > 120 else 0)
        core_bounds = core_mask.getbbox()
        self.assertIsNotNone(core_bounds)
        self.assertLessEqual(core_bounds[2] - core_bounds[0], 17)
        self.assertLessEqual(core_bounds[3] - core_bounds[1], 22)

        pale_pixels = [
            pixel
            for pixel in patch.get_flattened_data()
            if pixel[3] > 120
        ]
        self.assertTrue(pale_pixels)
        self.assertTrue(all(max(pixel[:3]) - min(pixel[:3]) <= 115 for pixel in pale_pixels))
        self.assertGreaterEqual(
            sum(pixel[2] for pixel in pale_pixels),
            sum(pixel[0] for pixel in pale_pixels),
        )

    def test_pressed_phase_remains_emphasized(self):
        feedback = self.feedback(phase="pressed")
        self.assertEqual(1.0, cursor_visual(feedback, 9_000).pulse)

    def test_matching_target_is_composited_at_scaled_global_point(self):
        rendered, metadata = composite_cursor_png(
            self.png,
            self.feedback(),
            self.target,
            2.0,
            2.0,
            now_ms=1_100,
        )
        self.assertTrue(metadata["drawn"])
        self.assertEqual(CURSOR_STYLE, metadata["style"])
        self.assertEqual([60, 50], metadata["imagePoint"])
        self.assertEqual("released", metadata["phase"])
        before = Image.open(BytesIO(self.png)).convert("RGBA")
        after = Image.open(BytesIO(rendered)).convert("RGBA")
        self.assertNotEqual(before.tobytes(), after.tobytes())
        self.assertEqual(before.getpixel((350, 150)), after.getpixel((350, 150)))

    def test_mismatched_window_draws_nothing(self):
        rendered, metadata = composite_cursor_png(
            self.png,
            self.feedback(targetWindowId=99),
            self.target,
            2.0,
            2.0,
            now_ms=1_100,
        )
        self.assertFalse(metadata["drawn"])
        self.assertEqual("target_mismatch", metadata["reason"])
        self.assertEqual(self.png, rendered)

    def test_mismatched_pid_draws_nothing(self):
        rendered, metadata = composite_cursor_png(
            self.png,
            self.feedback(targetPid=999),
            self.target,
            2.0,
            2.0,
            now_ms=1_100,
        )
        self.assertFalse(metadata["drawn"])
        self.assertEqual("target_mismatch", metadata["reason"])
        self.assertEqual(self.png, rendered)

    def test_out_of_bounds_point_draws_nothing(self):
        rendered, metadata = composite_cursor_png(
            self.png,
            self.feedback(displayX=999),
            self.target,
            2.0,
            2.0,
            now_ms=1_100,
        )
        self.assertFalse(metadata["drawn"])
        self.assertEqual("out_of_bounds", metadata["reason"])
        self.assertEqual(self.png, rendered)

    def test_renderer_allocates_only_compact_cursor_layers(self):
        with patch(
            "runtime.cu_runtime.cursor_feedback.Image.new",
            wraps=Image.new,
        ) as image_new:
            rendered, metadata = composite_cursor_png(
                self.png,
                self.feedback(),
                self.target,
                2.0,
                2.0,
                now_ms=1_100,
            )
        self.assertTrue(metadata["drawn"])
        self.assertNotEqual(self.png, rendered)
        allocated_sizes = [call.args[1] for call in image_new.call_args_list]
        self.assertTrue(allocated_sizes)
        self.assertTrue(all(width <= 256 and height <= 256 for width, height in allocated_sizes))
        self.assertTrue(all((width, height) != (400, 200) for width, height in allocated_sizes))


if __name__ == "__main__":
    unittest.main()
