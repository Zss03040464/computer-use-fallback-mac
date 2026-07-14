from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class NoGlobalTargetingTest(unittest.TestCase):
    def test_production_action_paths_do_not_use_global_or_focus_stealing_fallbacks(self):
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for directory in [ROOT / "runtime", ROOT / "src"]
            for path in directory.rglob("*")
            if path.suffix in {".py", ".mjs"}
        )
        banned = [
            "CGEventPost(",
            "CGEventPostToPid(",
            "pyautogui.moveTo(",
            "pyautogui.click(",
            "pyautogui.scroll(",
            "pyautogui.dragTo(",
            '"AXRaise"',
            " to activate'",
            "activateWithOptions_",
        ]
        found = [needle for needle in banned if needle in sources]
        self.assertEqual([], found, f"unsafe global targeting remains: {found}")

    def test_ui_test_fixtures_do_not_raise_focus_activate_or_force_ordering(self):
        fixture_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                ROOT / "tests" / "fixtures" / "background_input_harness.py",
                ROOT / "tests" / "live" / "native-app-matrix.test.mjs",
            ]
        )
        banned = [
            "kAXRaiseAction",
            "kAXFocusedWindowAttribute",
            "kAXFocusedAttribute",
            "CGEventPostToPid",
            "activateWithOptions_",
            "activateTestApplication",
            "orderFrontRegardless",
        ]
        found = [needle for needle in banned if needle in fixture_sources]
        self.assertEqual([], found, f"focus-taking UI fixture behavior remains: {found}")

        native_fixture = (ROOT / "tests" / "live" / "native-app-matrix.test.mjs").read_text(encoding="utf-8")
        blocker_fixture = (ROOT / "tests" / "fixtures" / "background_input_harness.py").read_text(encoding="utf-8")
        self.assertIn("const originalTabs = edgeTabs(state)", native_fixture)
        self.assertIn("rightmostTabCloseButton", native_fixture)
        self.assertIn("originalTabTitles", native_fixture)
        self.assertIn("NSWindowStyleMaskNonactivatingPanel", blocker_fixture)
        self.assertIn("orderFront_(None)", blocker_fixture)


if __name__ == "__main__":
    unittest.main()
