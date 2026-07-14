import ast
from pathlib import Path
import unittest

from runtime.cu_runtime.accessibility import AX_DOM_IDENTIFIER_ATTRIBUTE


ROOT = Path(__file__).resolve().parents[2]


class PythonCompatibilityTest(unittest.TestCase):
    def test_runtime_sources_parse_with_minimum_supported_python_grammar(self):
        for source_path in (ROOT / "runtime").rglob("*.py"):
            source = source_path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(source_path), feature_version=10)

    def test_dom_identifier_attribute_has_old_pyobjc_fallback(self):
        self.assertEqual(AX_DOM_IDENTIFIER_ATTRIBUTE, "AXDOMIdentifier")


if __name__ == "__main__":
    unittest.main()
