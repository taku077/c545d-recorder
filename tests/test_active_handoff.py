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
          "### 2026-11-19 latest\n96.29% private improvement; regression tested by exact HEAD\nKey handles controlled by weakref and UTF16 allocation ownership fix\n"
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

    def test_oversized_handoff_keeps_newest_complete_sections(self):
        newest = ("### UPDATE 2026-11-19 latest\n96.29% verified\n"
                  + "Latest critical result in synthetic Windows CI.\n")
        old = "### UPDATE older\n" + "stale details in archived history.\n" * 900
        sample = ("<!-- CURRENT_HANDOFF_START: current -->\n"
                  + newest + old + "\n" + BOUNDARY)
        actual = module.extract_current(sample, BOUNDARY, "96.29%")
        self.assertIn("Latest critical result", actual)
        self.assertNotIn("stale details", actual)
        self.assertIn("Older UPDATE sections remain", actual)

    def test_oversized_newest_update_fails_closed(self):
        huge = ("<!-- CURRENT_HANDOFF_START: current -->\n"
                "### UPDATE 2026-11-19\n96.29%\n" + "x" * 23000
                + "\n" + BOUNDARY)
        with self.assertRaisesRegex(ValueError, "Newest UPDATE section"):
            module.extract_current(huge, BOUNDARY, "96.29%")

    def test_guard_from_older_current_section_survives_excerpt_rotation(self):
        # New updates are allowed to displace older proved experiments from
        # the 18K summary, but the exact-SHA source already confirmed their
        # presence. Keep the guard referent instead of freezing main forever.
        guard = "CORE_ONLY_MSVC_64_AB_VERIFIED"
        latest = ("### UPDATE 2026-11-21 newest\n"
                  + "current safe host plan and CI state.\n" * 490)
        older = ("### UPDATE 2026-11-20 older verified\n"
                 + guard + "\n"
                 + "historical details already verified.\n" * 310)
        sample = ("<!-- CURRENT_HANDOFF_START: current -->\n"
                  + latest + older + "\n" + BOUNDARY)
        result = module.extract_current(sample, BOUNDARY, guard)
        self.assertIn("### UPDATE 2026-11-21 newest", result)
        self.assertIn("Protected evidence exists in the exact-commit full", result)
        self.assertIn(guard, result)
        self.assertNotIn("historical details already verified.", result)

if __name__ == "__main__":
    unittest.main()
