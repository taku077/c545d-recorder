#!/usr/bin/env python3
"""Repair one verified missing cleanup in upstream GLib Win32 AppInfo (test-only)."""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: apply_gio_friendly_free.py SOURCE/gio/gwin32appinfo.c")
p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
old = """  g_clear_pointer (&fallback_friendly_name, g_free);
  g_clear_pointer (&description, g_free);
  g_clear_pointer (&icon_source, g_free);
"""
new = """  g_clear_pointer (&fallback_friendly_name, g_free);
  /* LocalizedString was copied into app->localized_pretty_name above.
   * The temporary value returned by get_value_w() remains caller-owned. */
  g_clear_pointer (&friendly_name, g_free);
  g_clear_pointer (&description, g_free);
  g_clear_pointer (&icon_source, g_free);
"""
assert s.count(old) == 1, "Expected exactly one read_capable_app normal-exit cleanup block"
assert s.count("  friendly_name = NULL;") == 1, "Upstream source mismatch"
p.write_text(s.replace(old, new), encoding="utf-8", newline="\n")
print("GLIB_FRIENDLY_NAME_RELEASE_PATCH_APPLIED")
