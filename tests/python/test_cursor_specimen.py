from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "render-cursor-specimen.py"


class CursorSpecimenTest(unittest.TestCase):
    def test_script_renders_six_panel_production_cursor_specimen(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "cursor-specimen.png"
            subprocess.run(
                [sys.executable, str(SCRIPT), str(output)],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            image = Image.open(output).convert("RGB")
            self.assertEqual((900, 360), image.size)
            self.assertNotEqual(image.getpixel((75, 180)), image.getpixel((150, 180)))
            self.assertNotEqual(image.getpixel((375, 180)), image.getpixel((450, 180)))
            self.assertNotEqual(image.getpixel((675, 180)), image.getpixel((750, 180)))


if __name__ == "__main__":
    unittest.main()
