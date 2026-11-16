"""Offline assessment of an existing C545D Memory_Trend.csv (no extra capture)."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean


def fit_slope(data):
    """Return least-squares slope (MB/hour) and R^2 for (hour, MB) points."""
    if len(data) < 2:
        raise ValueError("Need at least two samples")
    mx = mean(x for x, _ in data)
    my = mean(y for _, y in data)
    xx = sum((x - mx) ** 2 for x, _ in data)
    if xx == 0:
        raise ValueError("All timestamps are the same")
    xy = sum((x - mx) * (y - my) for x, y in data)
    slope = xy / xx
    yy = sum((y - my) ** 2 for _, y in data)
    r_squared = 1 - sum((y - (my + slope * (x - mx))) ** 2 for x, y in data) / yy if yy else 1.0
    return slope, max(0.0, min(1.0, r_squared))


def analyze(csv_path, pid=None, warmup_hours=6.0):
    """Analyze only a single process session; do not upload raw CSV to GitHub."""
    data = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                time = datetime.strptime(row["Timestamp"], "%Y-%m-%d %H:%M:%S")
                proc_id = row["PID"].strip()
                private_mb = float(row["Private_MB"])
                cpu = float(row["CPU_Percent"]) if row.get("CPU_Percent") else None
            except (KeyError, ValueError, TypeError):
                continue
            if not proc_id or ";" in proc_id:
                continue  # Avoid mixing multiple gst-launch processes.
            data.append((time, proc_id, private_mb, cpu))
    if not data:
        raise ValueError("No valid single-process records found")
    if pid is None:
        # Select the latest observed single PID rather than the longest old run.
        pid = max(data, key=lambda r: r[0])[1]
    session = sorted((r for r in data if r[1] == str(pid)), key=lambda r: r[0])
    if len(session) < 2:
        raise ValueError("Too few records for selected PID")
    t0 = session[0][0]
    hours = (session[-1][0] - t0).total_seconds() / 3600.0
    if hours < 1 / 60:
        raise ValueError("Sampling window is less than one minute")
    points = [((t - t0).total_seconds() / 3600, private_mb) for t, _, private_mb, _ in session]
    slope_all, r2_all = fit_slope(points)
    late = [(x, y) for x, y in points if x >= warmup_hours]
    slope_late, r2_late = fit_slope(late) if len(late) >= 2 else (None, None)
    cpus = [r[3] for r in session if r[3] is not None]
    return {
        "pid": str(pid),
        "samples": len(session),
        "duration_hours": hours,
        "private_start_mb": session[0][2],
        "private_end_mb": session[-1][2],
        "private_growth_mb": session[-1][2] - session[0][2],
        "slope_all_mb_per_hour": slope_all,
        "r2_all": r2_all,
        "warmup_hours": warmup_hours,
        "slope_after_warmup_mb_per_hour": slope_late,
        "r2_after_warmup": r2_late,
        "mean_cpu_percent": mean(cpus) if cpus else None,
    }


def main():
    p = argparse.ArgumentParser(description="Local-only C545D memory growth check; does not modify recording")
    p.add_argument("csv_path", type=Path)
    p.add_argument("--pid", help="Select PID, if the CSV contains several recording sessions")
    p.add_argument("--warmup-hours", type=float, default=6)
    args = p.parse_args()
    result = analyze(args.csv_path, args.pid, args.warmup_hours)
    for key, value in result.items():
        print(f"{key}: {value:.3f}" if isinstance(value, float) else f"{key}: {value}")
    print("NOTE: A positive slope is not by itself proof of a leak; verify on longer runs.")


if __name__ == "__main__":
    main()
