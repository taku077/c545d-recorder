#!/usr/bin/env python3
"""Fast deterministic source-generation checks for the CI-only WinRT epoch guard.

No registry mutation, WinRT subscription, real package data or camera needed.
This exercises the actual dedicated source transformation with an in-memory
stub for the upstream GLib patcher; the full Windows integration CI separately
compiles and checks the resulting source.
"""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

import patch_glib_uwp_bridge_dedicated_integration_diagnostic as dedicated


def make_stub_source(bridge, *, missing_lookup_guard=False):
    lookup_guard = (
        "  if (!c545d_bridge_poll ())\n"
        "    return NULL; /* fail closed to original getter */\n"
        "  gchar *key = g_utf16_to_utf8"
    )
    if missing_lookup_guard:
        lookup_guard = lookup_guard.replace("c545d_bridge_poll", "broken_poll")
    return (
        "static gboolean c545d_bridge_poll (void);\n"
        + "static gunichar2 * c545d_cache_display_lookup(void) {\n"
        + lookup_guard + " (full_name, -1, NULL, NULL, NULL);\n"
        + "  g_free (key);\n"
        + "  if (result != NULL && !c545d_bridge_poll ())\n"
        + "    g_clear_pointer (&result, g_free);\n"
        + "  return result;\n}\n"
        + bridge
        + "\nvoid synthetic_getter(void) {\n"
        + "  guint64 c545d_before_getter_generation = 0;\n"
        + "  c545d_before_getter_generation = c545d_bridge_read_generation ();\n"
        + "  if (c545d_bridge_allow_store (c545d_before_getter_generation)) {}\n"
        + "}\n"
    )


class EpochSourceGuardTests(unittest.TestCase):
    def generate(self, missing_lookup_guard=False):
        with tempfile.TemporaryDirectory() as root:
            path = pathlib.Path(root) / "synthetic_gwin32packageparser.c"
            original_bridge = dedicated.original.BRIDGE

            def fake_upstream_patcher(p):
                p.write_text(make_stub_source(
                    dedicated.original.BRIDGE,
                    missing_lookup_guard=missing_lookup_guard,
                ), encoding="utf-8")

            try:
                with patch.object(dedicated.original, "main", side_effect=fake_upstream_patcher):
                    with patch.object(sys, "argv", ["dedicated.py", str(path)]):
                        dedicated.main()
                return path.read_text(encoding="utf-8")
            finally:
                dedicated.original.BRIDGE = original_bridge

    def test_both_package_generation_and_locale_guard_cache(self):
        s = self.generate()
        self.assertIn("previous.generation == c545d_bridge_generation", s)
        self.assertIn("previous.locale == c545d_bridge_locale", s)
        self.assertIn("c545d_bridge_allow_store (C545DBridgeEpoch pre_getter)", s)
        self.assertNotIn("c545d_bridge_allow_store (guint64 pre_getter)", s)

    def test_early_and_late_lookup_must_match_epoch(self):
        s = self.generate()
        self.assertIn("C545DBridgeEpoch before = c545d_bridge_read_epoch ();", s)
        self.assertIn("if (!before.valid)", s)
        self.assertIn("!c545d_bridge_epoch_still_valid (before)", s)
        self.assertNotIn("if (result != NULL && !c545d_bridge_poll ())", s)

    def test_getter_store_uses_full_epoch_not_only_generation(self):
        s = self.generate()
        self.assertIn("C545DBridgeEpoch c545d_before_getter_epoch", s)
        self.assertIn("c545d_bridge_allow_store (c545d_before_getter_epoch)", s)
        self.assertNotIn("c545d_before_getter_generation", s)

    def test_fail_closed_when_upstream_lookup_anchor_changes(self):
        with self.assertRaisesRegex(ValueError, "capture pre-lookup epoch"):
            self.generate(missing_lookup_guard=True)


if __name__ == "__main__":
    unittest.main()
