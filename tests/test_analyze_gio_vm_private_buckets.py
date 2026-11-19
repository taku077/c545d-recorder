#!/usr/bin/env python3
"""Fast, synthetic regression tests for the 384-cycle VM size analyzer.

Never touches Windows, registry, camera, ETL or actual user process memory.
"""
import contextlib
import io
import unittest

import analyze_gio_vm_private_buckets as sut


def fixture(scope, *, drop=None, duplicate=None, bad_sum=None,
            vm_error=None, handles=0, override_mode=None):
    lines = []
    for ix in (*sut.CHECKPOINTS, sut.SETTLED):
        label = ("baseline" if ix == 0 else
                 "settled_cleanup" if ix == sut.SETTLED else "cycle")
        bump = ((ix // 64) * 4096 if scope == "registry"
                and ix != sut.SETTLED else 0)
        small = 8192 + bump
        data = [
            f"GIO_PROBE,{label},{ix},0,{100 + (handles if ix == sut.SETTLED else 0)},{1000000 + bump}",
            f"GIO_VM,{label},{ix},{small + 65536},0,0,6,{int(ix == vm_error)}",
            f"GIO_VMCLASS,{label},{ix},{small + (1 if ix == bad_sum else 0)},65536,0,0,{small // 4096},1,0,0,0",
        ]
        for line in data:
            tag = line.split(",")[0]
            if drop == (tag, ix):
                continue
            lines.append(line)
            if duplicate == (tag, ix):
                lines.append(line)
    mode = int(scope == "registry") if override_mode is None else override_mode
    lines.append(f"GIO_PROBE_DONE,cycles=384,notifications=0,reg_changes={mode}")
    return "\n".join(lines) + "\n"


class VmBucketAnalyzerTests(unittest.TestCase):
    def load(self, scope="registry", **kwargs):
        return sut.parse_lines(fixture(scope, **kwargs), scope)

    def test_matched_control_subtraction_and_no_leak_certification(self):
        unchanged = self.load("nochange")
        changed = self.load("registry")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rows = sut.analyze(unchanged, changed)
        by_name = {row[0]: row for row in rows}
        self.assertEqual(8192, by_name["vm_private"][-1])
        self.assertEqual(8192, by_name["vm_4k"][-1])
        self.assertEqual(0, by_name["vm_4k_to_64k"][-1])
        self.assertIn("NOT_ALLOCATION_CAUSALITY", output.getvalue())
        self.assertEqual(8192, by_name["private_usage"][-1])

    def test_missing_vmclass_checkpoint_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing GIO_VMCLASS checkpoints"):
            self.load(drop=("GIO_VMCLASS", 128))

    def test_duplicate_vm_checkpoint_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate GIO_VM"):
            self.load(duplicate=("GIO_VM", 320))

    def test_bad_vmclass_sum_rejected(self):
        with self.assertRaisesRegex(ValueError, "bucket sum mismatch"):
            self.load(bad_sum=256)

    def test_incomplete_virtualquery_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete VirtualQuery census"):
            self.load(vm_error=192)

    def test_retained_handle_growth_rejected(self):
        with self.assertRaisesRegex(ValueError, "retained handle growth"):
            self.load(handles=5)

    def test_wrong_registry_mode_rejected(self):
        with self.assertRaisesRegex(ValueError, "wrong registry-change mode"):
            self.load(override_mode=0)

    def test_missing_completion_marker_rejected(self):
        s=fixture("registry").replace("GIO_PROBE_DONE,cycles=384", "GIO_PROBE_DONE,cycles=256")
        with self.assertRaisesRegex(ValueError, "missing/duplicate completion"):
            sut.parse_lines(s, "registry")

    def test_invalid_numeric_data_rejected(self):
        s=fixture("registry").replace("GIO_VM,cycle,64,", "GIO_VM,cycle,64,-", 1)
        with self.assertRaisesRegex(ValueError, "invalid numeric data"):
            sut.parse_lines(s, "registry")


if __name__ == "__main__":
    unittest.main()
