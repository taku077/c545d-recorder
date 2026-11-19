#!/usr/bin/env python3
"""Synthetic-only safety regression for dedicated WinRT MTA cache A/B analyzer.
No Windows measurement, no actual packages and no recorder data.
"""
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

ANALYZER=Path(__file__).with_name("analyze_gio_dedicated_mta_overhead_256.py")
MODES=("cache_only","mta_watch")

def synthetic(mode,scope, *, wrong_scans=False,bad_misses=False,handle_growth=0,
              large_busy=False,missing_vm=False):
    changing=scope=="registry"
    p=10000 if mode=="cache_only" else 20000
    busy_step=(300000 if large_busy else 16000) if changing else 0
    p=p if changing else 0
    rows=[]
    for i in range(257):
        phase="baseline" if i==0 else "cycle"
        count=i//64
        rows.append(f"GIO_PROBE,{phase},{i},0,678,{10_000_000+count*p}")
        if i%64==0:
            rows.append(f"GIO_HEAP,{phase},{i},{2000+count*4 if changing else 2000},"
                        f"{2_000_000+count*busy_step},4,0")
            if not (missing_vm and i==128):
                rows.append(f"GIO_VM,{phase},{i},{8_000_000+count*p},30000,40000,70,0")
    rows.extend([
       f"GIO_PROBE,settled_cleanup,258,0,{678+handle_growth},"
       f"{10_000_000+4*p}",
       f"GIO_HEAP,settled_cleanup,258,{2016 if changing else 2000},"
       f"{2_000_000+4*busy_step},4,0",
       f"GIO_VM,settled_cleanup,258,{8_000_000+4*p},30000,40000,70,0",
       "GIO_PROBE_DONE,cycles=256,notifications=0,reg_changes=1",
       f"C545D_DISPLAY_CACHE,hits={8224 if changing else 0},"
       f"misses={33 if bad_misses else 32},entries=32",
    ])
    if mode=="mta_watch":
        scans=(258 if changing else 1)
        if wrong_scans:scans=0
        rows.append(f"C545D_WINRT_BRIDGE,scans={scans},injections=0,"
                    f"evictions=0,errors=0,ready=1")
    return "\n".join(rows)+"\n"

class DedicatedMTAAnalyzerTests(unittest.TestCase):
    def run_fixture(self,edits=None):
        edits=edits or {}
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp,"artifacts");d.mkdir()
            for mode in MODES:
                for scope in ("nochange","registry"):
                    options=edits.get((mode,scope),{})
                    (d/f"{mode}_{scope}_256.log").write_text(
                       synthetic(mode,scope,**options),encoding="utf-8")
            return subprocess.run([sys.executable,str(ANALYZER)],cwd=tmp,
                                  text=True,capture_output=True,check=False)

    def test_unmodified_control_one_scan_is_accepted(self):
        p=self.run_fixture()
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn("C545D_MTA_WATCH_256_DIAGNOSTIC_PASS",p.stdout)

    def test_broken_control_watcher_rejected(self):
        p=self.run_fixture({("mta_watch","nochange"):{"wrong_scans":True}})
        self.assertNotEqual(p.returncode,0)
        self.assertIn("dedicated watcher unhealthy",p.stderr)

    def test_broken_registry_watcher_rejected(self):
        p=self.run_fixture({("mta_watch","registry"):{"wrong_scans":True}})
        self.assertNotEqual(p.returncode,0)

    def test_repeated_displayname_getter_rejected(self):
        p=self.run_fixture({("cache_only","registry"):{"bad_misses":True}})
        self.assertNotEqual(p.returncode,0)

    def test_positive_handles_rejected(self):
        p=self.run_fixture({("mta_watch","registry"):{"handle_growth":9}})
        self.assertNotEqual(p.returncode,0)

    def test_large_retained_heap_growth_rejected(self):
        p=self.run_fixture({("mta_watch","registry"):{"large_busy":True}})
        self.assertNotEqual(p.returncode,0)
        self.assertIn("512 KiB",p.stderr)

    def test_missing_vm_checkpoint_rejected(self):
        p=self.run_fixture({("mta_watch","registry"):{"missing_vm":True}})
        self.assertNotEqual(p.returncode,0)

if __name__=="__main__":
    unittest.main(verbosity=2)
