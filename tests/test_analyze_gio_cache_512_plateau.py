#!/usr/bin/env python3
"""Pure synthetic regression of 512-cycle memory-slope/handle parser.
No Windows data, camera or machine paths; no long-running measurement.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PARSER=Path(__file__).with_name("analyze_gio_cache_512_plateau.py")

def generate(scope, *, handle_growth=0, bad_misses=False,
             missing_vm=False, missing_cycle=False, persistent=False):
    changing=scope=="registry"
    rows=[]
    for i in range(513):
        if i==0: phase="baseline"
        else: phase="cycle"
        if missing_cycle and i==412:
            continue
        count=i//64
        growth=(count*98304 if persistent else min(count,4)*32768) if changing else 0
        rows.append(f"GIO_PROBE,{phase},{i},0,678,{8000000+growth}")
        if i%64==0:
            blocks=2000+ (count*10 if changing else 0)
            busy=2000000+ (count*2048 if changing else 0)
            rows.append(f"GIO_HEAP,{phase},{i},{blocks},{busy},4,0")
            if not (missing_vm and i==320):
                rows.append(f"GIO_VM,{phase},{i},{8500000+growth},20000,30000,60,0")
    rows += [
        f"GIO_PROBE,settled_cleanup,514,0,{678+handle_growth},8200000",
        "GIO_HEAP,settled_cleanup,514,2050,2010240,4,0",
        "GIO_VM,settled_cleanup,514,9000000,20000,30000,60,0",
        "GIO_PROBE_DONE,cycles=512,notifications=0,reg_changes=1",
        f"C545D_DISPLAY_CACHE,hits={16416 if changing else 0},"
        f"misses={33 if bad_misses else 32},entries=32",
    ]
    return "\n".join(rows)+"\n"

class Cache512Tests(unittest.TestCase):
    def invoke(self,changes=None):
        changes=changes or {}
        with tempfile.TemporaryDirectory() as td:
            p=Path(td,"artifacts");p.mkdir()
            for mode in ("registry","nochange"):
                (p/f"cache_{mode}_512.log").write_text(
                    generate(mode,**changes.get(mode,{})),encoding="utf-8")
            return subprocess.run([sys.executable,str(PARSER)],cwd=td,
                                  text=True,capture_output=True,check=False)

    def test_late_plateau_observed_but_not_certified(self):
        result=self.invoke()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("last256=0",result.stdout)
        self.assertIn("SHORT_WINDOW_PLATEAU_CANDIDATE",result.stdout)
        self.assertIn("NOT_ZERO_LEAK_PROOF",result.stdout)

    def test_persistent_growth_reported_not_hidden(self):
        result=self.invoke({"registry":{"persistent":True}})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("RESIDUAL_GROWTH_REQUIRES_INVESTIGATION",result.stdout)

    def test_repeated_cache_miss_rejected(self):
        result=self.invoke({"registry":{"bad_misses":True}})
        self.assertNotEqual(result.returncode,0)
        self.assertIn("cache not bounded",result.stderr)

    def test_positive_handle_growth_rejected(self):
        result=self.invoke({"registry":{"handle_growth":11}})
        self.assertNotEqual(result.returncode,0)
        self.assertIn("positive retained handles",result.stderr)

    def test_incomplete_cycle_detected(self):
        result=self.invoke({"registry":{"missing_cycle":True}})
        self.assertNotEqual(result.returncode,0)
        self.assertIn("expected 512 reports",result.stderr)

    def test_missing_vm_snapshot_detected(self):
        result=self.invoke({"registry":{"missing_vm":True}})
        self.assertNotEqual(result.returncode,0)
        self.assertIn("missing GIO_VM checkpoints",result.stderr)

if __name__=="__main__":
    unittest.main(verbosity=2)
