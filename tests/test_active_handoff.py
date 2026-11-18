"""No-network regression tests: an old handoff must never replace newer active evidence."""
import importlib.util
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "tools/refresh_active_handoff.py"
spec = importlib.util.spec_from_file_location("refresh_active_handoff", SRC)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

BOUNDARY = "## CURRENT 2026-11-18 JST — ETL自動オフライン解析ツール完成、実機レポート待ち"
SAMPLE = ("# project\n<!-- CURRENT_HANDOFF_START: current -->\n"
          "### 2026-11-19 latest\n96.29% private improvement\nKey handles controlled\n"
          + BOUNDARY + "\nOLD: ETL WAIT\n")

class TestHandoff(unittest.TestCase):
    def test_current_excludes_stale_archive(self):
        actual = module.extract_current(SAMPLE, BOUNDARY, "96.29%")
        self.assertIn("96.29%", actual)
        self.assertNotIn("ETL WAIT", actual)

    def test_missing_verified_evidence_fails_closed(self):
        with self.assertRaises(ValueError):
            module.extract_current(SAMPLE.replace("96.29%", "unknown"), BOUNDARY, "96.29%")

    def test_missing_archive_boundary_fails_closed(self):
        with self.assertRaises(ValueError):
            module.extract_current(SAMPLE, "nonexistent", "96.29%")

    def test_missing_current_marker_fails_closed(self):
        with self.assertRaises(ValueError):
            module.extract_current("old docs only", BOUNDARY, "96.29%")

if __name__ == "__main__":
    unittest.main()
