#!/usr/bin/env python3
"""Synthetic-only regression tests for cache refresh A/B analyzer.

No real recorder logs or installed package names are stored in this repo.
Tests the previous false-positive (normal mode scans=0), NULL-HSTRING refill,
handle growth rejection, and exact expected synthetic refresh census.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("analyze_gio_cache_refresh.py")


def make_log(*, mode, scope, misses=None, resets=None, handles=0,
             bad_null=False):
    cached = mode == "cache"
    changed = scope == "registry"
    scans = (0 if cached else 18 if changed else 1)
    actual_resets = (0 if cached or not changed else 4)
    if resets is not None:
        actual_resets = resets
    hits = (544 if cached and changed else
            416 if changed else 0)
    miss_count = (32 if cached or not changed else 160)
    if misses is not None:
        miss_count = misses
    empty = (1 if cached or not changed else 5)
    if bad_null:
        empty = 1
    dprivate = 0 if not changed else (266240 if cached else 679936)
    dbusy = -80 if not changed else (7168 if cached else 39396)
    dblocks = -2 if not changed else (3 if cached else 384)

    lines = [
        "GIO_PROBE,baseline,0,0,678,5000000",
        "GIO_HEAP,baseline,0,20000,1000000,4,0",
        "GIO_VM,baseline,0,100000,110000,120000,0,0",
    ]
    for i in range(16):
        lines.append(f"GIO_PROBE,cycle,{i+1},0,678,5000000")
    lines.extend([
        f"GIO_PROBE,settled_cleanup,18,0,{678+handles},{5000000+dprivate}",
        f"GIO_HEAP,settled_cleanup,18,{20000+dblocks},{1000000+dbusy},4,0",
        "GIO_VM,settled_cleanup,18,100000,110000,120000,0,0",
        "GIO_PROBE_DONE,cycles=16,notifications=0,reg_changes=1",
        f"C545D_DISPLAY_CACHE,hits={hits},misses={miss_count},entries=32",
        f"C545D_DISPLAY_CACHE_REFRESH,scans={scans},resets={actual_resets}",
        f"C545D_DISPLAY_CACHE_NULL_HSTRING_RETURNS={empty}",
    ])
    return "\n".join(lines)+"\n"


class CacheAnalyzerTests(unittest.TestCase):
    def run_case(self, changes=()):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "artifacts"
            root.mkdir()
            for mode in ("cache", "refresh"):
                for scope in ("nochange", "registry"):
                    opts = dict(next((v for m, s, v in changes
                                     if m == mode and s == scope), {}))
                    (root / f"{mode}_{scope}_16.log").write_text(
                        make_log(mode=mode, scope=scope, **opts), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT)],
                cwd=t, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False)

    def test_complete_valid_fixture_and_zero_disabled_scan(self):
        p = self.run_case()
        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
        self.assertIn("C545D_GLIB_CACHE_FORCED_REFRESH_PASS", p.stdout)
        self.assertIn("cache,private_bytes=", p.stdout)
        self.assertIn("refresh,private_bytes=", p.stdout)

    def test_missing_refetch_after_invalidation_rejected(self):
        p = self.run_case([("refresh", "registry", {"misses": 128})])
        self.assertNotEqual(p.returncode, 0)

    def test_empty_hstring_refetch_count_rejected(self):
        p = self.run_case([("refresh", "registry", {"bad_null": True})])
        self.assertNotEqual(p.returncode, 0)

    def test_invalid_refresh_count_rejected(self):
        p = self.run_case([("refresh", "registry", {"resets": 0})])
        self.assertNotEqual(p.returncode, 0)

    def test_new_total_handle_growth_rejected(self):
        p = self.run_case([("refresh", "registry", {"handles": 9})])
        self.assertNotEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
