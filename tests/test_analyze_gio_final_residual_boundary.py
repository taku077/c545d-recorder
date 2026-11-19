#!/usr/bin/env python3
"""Pure-Python regression of 256-cycle final-residual causal analyzer.

Synthetic machine-free logs: no user files, no Windows host, no registry writes.
The analyzer must distinguish control-subtracted memory from a leak *claim*.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ANALYZER = Path(__file__).with_name("analyze_gio_final_residual_boundary.py")
STAGES = ("cached_original", "no_displayname_getter", "skip_uwp_current")


def synthetic_probe(stage, scope, *, missing_vm=False,
                    settled_handle_change=0, bad_misses=False):
    registry = scope == "registry"
    rates = {
        "cached_original": (40960, 1024, 20480, 2),
        "no_displayname_getter": (32768, 0, 16384, 0),
        "skip_uwp_current": (16384, 0, 8192, 0),
    }
    private, busy, vm, blocks = rates[stage]
    if not registry:
        private = busy = vm = blocks = 0
    raw = []
    for i in range(257):
        phase = "baseline" if i == 0 else "cycle"
        count = i // 64
        raw.append(
            f"GIO_PROBE,{phase},{i},0,680,{10_000_000 + count*private}"
        )
        if i % 64 == 0:
            if not (missing_vm and i == 128):
                raw.append(
                    f"GIO_VM,{phase},{i},{20_000_000 + count*vm},"
                    "35000,45000,70,0"
                )
            raw.append(
                f"GIO_HEAP,{phase},{i},{2000 + count*blocks},"
                f"{2_000_000 + count*busy},4,0"
            )
    raw += [
        f"GIO_PROBE,settled_cleanup,258,0,"
        f"{680 + settled_handle_change},{10_000_000 + 4*private}",
        f"GIO_HEAP,settled_cleanup,258,{2000+4*blocks},"
        f"{2_000_000+4*busy},4,0",
        f"GIO_VM,settled_cleanup,258,{20_000_000+4*vm},35000,45000,70,0",
        "GIO_PROBE_DONE,cycles=256,notifications=0,reg_changes=1",
    ]
    if stage == "cached_original":
        misses = 33 if bad_misses else 32
        raw.append(
            f"C545D_DISPLAY_CACHE,hits={8224 if registry else 0},"
            f"misses={misses},entries=32"
        )
    return "\n".join(raw) + "\n"


class ResidualBoundaryAnalyzerTests(unittest.TestCase):
    def run_fixture(self, edits=None):
        edits = edits or {}
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp, "artifacts")
            art.mkdir()
            for stage in STAGES:
                for scope in ("nochange", "registry"):
                    options = edits.get((stage, scope), {})
                    (art / f"{stage}_{scope}_256.log").write_text(
                        synthetic_probe(stage, scope, **options),
                        encoding="utf-8"
                    )
            return subprocess.run(
                [sys.executable, str(ANALYZER)],
                cwd=tmp, capture_output=True, text=True, check=False
            )

    def test_valid_monotonic_residual_is_reported_not_called_cured(self):
        p = self.run_fixture()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("C545D_FINAL_RESIDUAL_BOUNDARY_PASS", p.stdout)
        self.assertIn("cached_private_last128=81920", p.stdout)
        self.assertIn("no_getter_private_last128=65536", p.stdout)
        self.assertIn("skip_uwp_private_last128=32768", p.stdout)
        self.assertNotIn("LEAK_FREE", p.stdout)

    def test_repeated_displayname_cache_miss_fails(self):
        p = self.run_fixture({
            ("cached_original", "registry"): {"bad_misses": True}
        })
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("unexpected repeated cache miss", p.stderr)

    def test_positive_retained_handles_fail(self):
        p = self.run_fixture({
            ("skip_uwp_current", "registry"): {"settled_handle_change": 9}
        })
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("positive retained handles", p.stderr)

    def test_released_handles_not_considered_leaked(self):
        p = self.run_fixture({
            ("skip_uwp_current", "registry"): {"settled_handle_change": -20}
        })
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_missing_vm_checkpoint_fails(self):
        p = self.run_fixture({
            ("no_displayname_getter", "registry"): {"missing_vm": True}
        })
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("Missing GIO_VM checkpoint 128", p.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
