#!/usr/bin/env python3
"""Synthetic, camera-free regression for 512-cycle matched-control analyzer.

No real registry, heap, ETL, paths, handles, or media is used.
"""
import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SUT=Path(__file__).resolve().with_name("analyze_gio_cache_512_plateau.py")

def fixture(scope, absent=None, walk_error=None, impossible=False,
            known_count=4, handles=0):
    lines=[]
    for i in range(513):
        name="baseline" if i==0 else "cycle"
        delta=4096*(i//64) if scope=="registry" else 0
        lines.append(f"GIO_PROBE,{name},{i},0,100,{2000000+delta}")
        if i % 64:continue
        known=5 if impossible else known_count
        lines += [
            f"GIO_HEAP,{name},{i},200,50000,4,0",
            f"GIO_VM,{name},{i},{1800000+delta},1000,2000,10,0",
        ]
        if absent != i:
            lines.append(
              f"GIO_HEAPREGION,{name},{i},4,{known},"
              f"{700000+delta},0,10000,10,{int(walk_error==i)}")
    lines += [
        f"GIO_PROBE,settled_cleanup,514,0,{100+handles},2000000",
        "GIO_HEAP,settled_cleanup,514,200,50000,4,0",
        "GIO_VM,settled_cleanup,514,1800000,1000,2000,10,0",
        f"GIO_HEAPREGION,settled_cleanup,514,4,{known_count},700000,0,10000,10,0",
        "C545D_DISPLAY_CACHE,hits=16384,misses=32,entries=32",
        f"GIO_PROBE_DONE,cycles=512,notifications=0,reg_changes={int(scope=='registry')}",
    ]
    return "\n".join(lines)+"\n"

class AnalyzerTests(unittest.TestCase):
    def run_fixture(self,**kw):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"artifacts"
            p.mkdir()
            (p/"cache_nochange_512.log").write_text(fixture("nochange"),encoding="utf-8")
            (p/"cache_registry_512.log").write_text(fixture("registry",**kw),encoding="utf-8")
            result=subprocess.run([sys.executable,str(SUT)],cwd=tmp,
                                  capture_output=True,text=True,check=False)
            csvpath=p/"cache_512_aggregate.csv"
            rows=[]
            if csvpath.exists():
                with csvpath.open(encoding="utf-8",newline="") as f:
                    rows=list(csv.DictReader(f))
            return result,rows

    def test_matched_delta(self):
        result,records=self.run_fixture()
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertIn("complete_checkpoints=9/9",result.stdout)
        byname={r["metric"]:r for r in records}
        self.assertEqual("16384",byname["private_bytes"]["last256"])
        self.assertEqual("16384",byname["heap_region_committed"]["last256"])
        self.assertEqual("0",byname["busy_bytes"]["last256"])

    def test_missing_checkpoint_rejected(self):
        r,_=self.run_fixture(absent=256)
        self.assertEqual(2,r.returncode)
        self.assertIn("missing GIO_HEAPREGION checkpoints",r.stderr)

    def test_heapwalk_error_rejected(self):
        r,_=self.run_fixture(walk_error=320)
        self.assertEqual(2,r.returncode)
        self.assertIn("invalid GIO_HEAPREGION snapshot",r.stderr)

    def test_impossible_coverage_rejected(self):
        r,_=self.run_fixture(impossible=True)
        self.assertEqual(2,r.returncode)
        self.assertIn("invalid heap region coverage counts",r.stderr)

    def test_retained_handles_rejected(self):
        r,_=self.run_fixture(handles=5)
        self.assertEqual(2,r.returncode)
        self.assertIn("positive retained handles",r.stderr)

    def test_optional_region_commit_unavailable(self):
        r,_=self.run_fixture(known_count=0)
        self.assertEqual(0,r.returncode,r.stderr)
        self.assertIn("complete_checkpoints=0/9",r.stdout)
        self.assertIn("heap_region_committed_is_partial_if_coverage_incomplete=true",
                      r.stdout)

if __name__=="__main__":
    unittest.main()
