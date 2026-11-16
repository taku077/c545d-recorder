import csv
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from tools.analyze_memory_trend import analyze, fit_slope


class MemoryTrendTests(unittest.TestCase):
    def test_slope_known_linear_growth(self):
        slope, r2 = fit_slope([(x, 600 + 6 * x) for x in range(12)])
        self.assertAlmostEqual(slope, 6.0, places=9)
        self.assertAlmostEqual(r2, 1.0, places=9)

    def test_plateau_is_zero_slope(self):
        slope, r2 = fit_slope([(x, 720.0) for x in range(12)])
        self.assertAlmostEqual(slope, 0.0, places=9)
        self.assertAlmostEqual(r2, 1.0, places=9)

    def test_latest_session_and_warmup(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "Memory_Trend.csv"
            base = datetime(2026, 1, 1)
            with p.open("w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=["Timestamp", "PID", "WorkingSet_MB", "Private_MB", "CPU_Percent"])
                w.writeheader()
                for h in range(12):
                    w.writerow({"Timestamp": (base + timedelta(hours=h)).strftime("%Y-%m-%d %H:%M:%S"),
                                "PID": "111", "WorkingSet_MB": 100, "Private_MB": 300 + 30 * h,
                                "CPU_Percent": "40"})
                for h in range(12):
                    w.writerow({"Timestamp": (base + timedelta(days=1, hours=h)).strftime("%Y-%m-%d %H:%M:%S"),
                                "PID": "222", "WorkingSet_MB": 200, "Private_MB": 600 + 6 * h,
                                "CPU_Percent": "20"})
            result = analyze(p)
            self.assertEqual(result["pid"], "222")
            self.assertAlmostEqual(result["slope_after_warmup_mb_per_hour"], 6.0, places=8)
            self.assertAlmostEqual(result["mean_cpu_percent"], 20.0)
            self.assertEqual(result["private_growth_mb"], 66.0)

    def test_multi_pid_aggregate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "Memory_Trend.csv"
            p.write_text("Timestamp,PID,WorkingSet_MB,Private_MB,CPU_Percent\n"
                         "2026-01-01 00:00:00,1;2,100,200,10\n"
                         "2026-01-01 01:00:00,1;2,100,205,10\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                analyze(p)


if __name__ == "__main__":
    unittest.main()
