#!/usr/bin/env python3
"""Cheap synthetic ABI tests; no DLL execution or Windows runner needed."""
import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import analyze_c545d_gio_sdk_imports as m

class TestAbiImports(unittest.TestCase):
    def setUp(self):
        self.sdk = {b"g_app_info_get_all": 1, b"g_object_ref": 2}
        self.cand = dict(self.sdk)
        self.sdk_ord = {1: b"g_app_info_get_all", 2: b"g_object_ref"}
        self.cand_ord = dict(self.sdk_ord)

    def evaluate(self, entries):
        return m.validate_gio_imports(entries, self.sdk, self.cand,
                                      self.sdk_ord, self.cand_ord)

    def test_named_import_is_resolved(self):
        r = self.evaluate([(b"g_app_info_get_all", None)])
        self.assertEqual(r["gio_name_imports"], 1)
        self.assertEqual(r["candidate_unresolved_name_imports"], 0)

    def test_missing_name_is_detected(self):
        self.cand.pop(b"g_app_info_get_all")
        r = self.evaluate([(b"g_app_info_get_all", None)])
        self.assertEqual(r["candidate_unresolved_name_imports"], 1)

    def test_matching_ordinal_is_resolved(self):
        r = self.evaluate([(None, 1)])
        self.assertEqual(r["gio_ordinal_imports"], 1)
        self.assertEqual(r["candidate_mismatched_ordinal_imports"], 0)

    def test_ordinal_mapping_drift_is_detected(self):
        self.cand_ord[1] = b"wrong_function"
        r = self.evaluate([(None, 1)])
        self.assertEqual(r["candidate_mismatched_ordinal_imports"], 1)

    def test_missing_ordinal_is_detected(self):
        self.cand_ord.pop(1)
        r = self.evaluate([(None, 1)])
        self.assertEqual(r["candidate_unresolved_ordinal_imports"], 1)

    def test_missing_source_ordinal_is_detected(self):
        r = self.evaluate([(None, 99999)])
        self.assertEqual(r["sdk_unresolved_ordinal_imports"], 1)

if __name__ == "__main__":
    unittest.main()
