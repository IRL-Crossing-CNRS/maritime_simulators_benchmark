#!/usr/bin/env python3
#
# Copyright (c) 2026 IRL Crossing
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0
#
"""
@file process_uuvsim_repeats.py
@brief Statistics of the repeated UUVSim runs (standard library only: runs with the
Python 3.6 of Ubuntu 18.04, no numpy or pandas needed).

Layout read: <repeats-dir>/protocol_<P>/<agents>/run<k>/ with update_times.csv,
render_fps.csv, rtf_samples.csv, window.json, physics.json and status.txt
(written by benchmark_code/uuv_benchmark/repeat_uuvsim.sh).

Definitions (same as the HoloOcean, LRAUVSim and Stonefish repeats):
    - measure window: the --measure-seconds written once every agent is in Gazebo
      (window.json). The mean step, median, p95, p99, max and the fraction of steps
      over the budget are computed over the update_times.csv lines of that window.
    - Dispersion ratios (IQR/median, p95/median, max/median): over the whole
      update_times.csv with the first 10 % of the steps discarded, as in the reference analysis.
    - RTF: mean of /gazebo/performance_metrics samples in the window (as the
      reference benchmark_rtf.csv), and simulated time / wall time over the window.
    - summary per point: mean, sd, 95 % CI (Student t, n - 1 dof), 95 % prediction
      interval, min, max over the finished runs, and the reference value.

Usage:
    process_uuvsim_repeats.py run <run_dir> --protocol B
    process_uuvsim_repeats.py machine <machine.csv>
    process_uuvsim_repeats.py summary --repeats-dir <dir> [--out-dir <dir>] [--point B:150]
"""

import argparse
import csv
import json
import math
import os
import re
import statistics
import sys

BUDGET_MS = {"A": 200.0, "B": 1000.0 / 33.0, "C": 1000.0 / 33.0, "D": 1000.0 / 33.0}
PERCEPTION_MS = 200.0

# Reference values recomputed from the published traces:
#   A/B: mean step (ms) of data/uuv/AB/<n> over the post-spawn window of
#        process_uuvsim.py (one sweep serves A and B in the reference).
#   C/D: mean RTF of benchmark_accelerated_time/data/uuvsim/benchmark_rtf_<n>_{agents,headless}.csv
#        after the 10 % skip of statistics_accelerated_time.py.
REFERENCE = {
    ("A", 150): 16.20, ("A", 162): 82.10,
    ("B", 150): 16.20, ("B", 162): 82.10,
    ("C", 1): 189.01,
    ("D", 1): 214.98, ("D", 35): 2.25, ("D", 40): 1.85,
}
T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262]


def percentile(sorted_vals, q):
    """Linear interpolation between closest ranks (numpy's default)."""
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def read_column(path, col=0, skip_header=True):
    vals = []
    if not os.path.isfile(path):
        return vals
    with open(path) as f:
        for i, line in enumerate(f):
            if skip_header and i == 0:
                continue
            parts = line.strip().split(",")
            try:
                vals.append(float(parts[col]))
            except (ValueError, IndexError):
                vals.append(None)
    return vals


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def fmt(v, nd=3):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    return ("%." + str(nd) + "f") % v


def run_metrics(run_dir, protocol):
    m = {"status": "missing"}
    try:
        with open(os.path.join(run_dir, "status.txt")) as f:
            m["status"] = f.read().split()[0]
    except (OSError, IndexError):
        pass
    win = load_json(os.path.join(run_dir, "window.json"))
    phys = load_json(os.path.join(run_dir, "physics.json"))
    m["time_step"] = phys.get("time_step")
    m["max_update_rate"] = phys.get("max_update_rate")
    m["spawn_s"] = win.get("spawn_seconds")
    m["agents_end"] = win.get("agents_at_end")
    m["wall_s"] = win.get("wall_seconds")
    m["sim_s"] = win.get("sim_seconds")
    m["rtf_clock"] = (win["sim_seconds"] / win["wall_seconds"]) if win.get("wall_seconds") else None

    budget = BUDGET_MS[protocol]
    upd_all = read_column(os.path.join(run_dir, "update_times.csv"))
    if win and upd_all:
        a, b = win["update_times_lines"]
        # lines (a, b] of the file, header = line 1 -> values index a-1 .. b-2
        window = [v * 1000.0 for v in upd_all[max(a - 1, 0):max(b - 1, 0)] if v is not None and v > 0]
    else:
        window = []
    m["n_steps"] = len(window)
    if window:
        s = sorted(window)
        med = percentile(s, 50)
        m.update(mean_step_ms=statistics.mean(window), median_ms=med,
                 p95_ms=percentile(s, 95), p99_ms=percentile(s, 99), max_ms=s[-1],
                 over_budget_pct=100.0 * sum(1 for v in window if v > budget) / len(window),
                 over_200ms_pct=100.0 * sum(1 for v in window if v > PERCEPTION_MS) / len(window))
    full = [v * 1000.0 for v in upd_all if v is not None and v > 0]
    if len(full) > 10:
        s = sorted(full[int(0.10 * len(full)):])
        med = percentile(s, 50)
        if med > 0:
            m.update(t5_iqr_med_pct=100.0 * (percentile(s, 75) - percentile(s, 25)) / med,
                     t5_p95_med=percentile(s, 95) / med, t5_max_med=s[-1] / med)

    rtf = [r for r in read_column(os.path.join(run_dir, "rtf_samples.csv"), col=2) if r is not None]
    m["mean_rtf"] = statistics.mean(rtf) if rtf else None
    m["median_rtf"] = statistics.median(rtf) if rtf else None

    fps_all = read_column(os.path.join(run_dir, "render_fps.csv"), col=1)
    if win and fps_all:
        a, b = win["render_fps_lines"]
        fps = [v for v in fps_all[max(a - 1, 0):max(b - 1, 0)] if v is not None and v > 0]
        m["mean_fps"] = statistics.mean(fps) if fps else None
    return m


RUN_FIELDS = ["status", "time_step", "max_update_rate", "spawn_s", "agents_end", "wall_s", "sim_s",
              "rtf_clock", "mean_rtf", "median_rtf", "n_steps", "mean_step_ms", "median_ms", "p95_ms",
              "p99_ms", "max_ms", "over_budget_pct", "over_200ms_pct", "t5_iqr_med_pct", "t5_p95_med",
              "t5_max_med", "mean_fps"]


def machine_summary(path):
    """Median fastest-core clock, max package temperature, battery states and the
    minimum available memory over the measure phase (whole run if none)."""
    rows = []
    try:
        with open(path) as f:
            rows = list(csv.DictReader(f))
    except OSError:
        pass
    sel = [r for r in rows if r.get("phase") == "measure"] or rows
    if not sel:
        return "- - - -"
    mhz = sorted(int(r["max_core_mhz"]) for r in sel)
    temp = max(int(r["pkg_temp_c"]) for r in sel)
    bat = "+".join(sorted(set(r["battery"] for r in sel)))
    mem = min(int(r["mem_available_mb"]) for r in sel)
    return "%d %d %s %d" % (mhz[(len(mhz) - 1) // 2], temp, bat, mem)


def describe(vals):
    n = len(vals)
    if n == 0:
        return {"n": 0}
    mean = statistics.mean(vals)
    d = {"n": n, "mean": mean, "min": min(vals), "max": max(vals)}
    if n > 1:
        sd = statistics.stdev(vals)
        t = T95[n - 2] if n - 1 <= len(T95) else 1.96
        d.update(sd=sd, ci95=t * sd / math.sqrt(n), pi95=t * sd * math.sqrt(1 + 1.0 / n))
    return d


def iter_runs(repeats_dir):
    for pdir in sorted(os.listdir(repeats_dir)):
        mt = re.match(r"^protocol_([ABCD])$", pdir)
        if not mt:
            continue
        p = mt.group(1)
        base = os.path.join(repeats_dir, pdir)
        for n in sorted((d for d in os.listdir(base) if d.isdigit()), key=int):
            for r in sorted((d for d in os.listdir(os.path.join(base, n)) if re.match(r"^run\d+$", d)),
                            key=lambda x: int(x[3:])):
                yield p, int(n), int(r[3:]), os.path.join(base, n, r)


def summary(args):
    rows = []
    for p, n, k, d in iter_runs(args.repeats_dir):
        if args.point and args.point != "%s:%d" % (p, n):
            continue
        m = run_metrics(d, p)
        m.update(protocol=p, agents=n, run=k)
        rows.append(m)
    if not rows:
        print("  no run found in %s" % args.repeats_dir)
        return
    out = args.out_dir or args.repeats_dir
    suffix = "" if not args.point else "_" + args.point.replace(":", "_")
    per_run = os.path.join(out, "uuvsim_repeats_per_run%s.csv" % suffix)
    with open(per_run, "w") as f:
        w = csv.writer(f)
        w.writerow(["protocol", "agents", "run"] + RUN_FIELDS)
        for m in rows:
            w.writerow([m["protocol"], m["agents"], m["run"]] +
                       [fmt(m.get(x), 6) if isinstance(m.get(x), float) else ("-" if m.get(x) is None else m.get(x))
                        for x in RUN_FIELDS])

    points = sorted(set((m["protocol"], m["agents"]) for m in rows))
    summ = os.path.join(out, "uuvsim_repeats_summary%s.csv" % suffix)
    with open(summ, "w") as f:
        w = csv.writer(f)
        w.writerow(["protocol", "agents", "metric", "runs", "runs_finished", "mean", "sd", "ci95_low",
                    "ci95_high", "pi95_low", "pi95_high", "min", "max", "reference"])
        for p, n in points:
            runs = [m for m in rows if (m["protocol"], m["agents"]) == (p, n)]
            done = [m for m in runs if m["status"] == "ok"]
            metrics = (["mean_step_ms", "median_ms", "p95_ms", "p99_ms", "max_ms", "over_budget_pct",
                        "over_200ms_pct", "t5_iqr_med_pct", "t5_p95_med", "t5_max_med", "rtf_clock", "mean_fps"]
                       if p in "AB" else ["mean_rtf", "median_rtf", "rtf_clock", "mean_step_ms", "mean_fps"])
            for metric in metrics:
                vals = [m[metric] for m in done if m.get(metric) is not None]
                d = describe(vals)
                ref = REFERENCE.get((p, n)) if metric == ("mean_step_ms" if p in "AB" else "mean_rtf") else None
                w.writerow([p, n, metric, len(runs), len(done), fmt(d.get("mean")), fmt(d.get("sd")),
                            fmt(d["mean"] - d["ci95"]) if "ci95" in d else "-",
                            fmt(d["mean"] + d["ci95"]) if "ci95" in d else "-",
                            fmt(d["mean"] - d["pi95"]) if "pi95" in d else "-",
                            fmt(d["mean"] + d["pi95"]) if "pi95" in d else "-",
                            fmt(d.get("min")), fmt(d.get("max")), fmt(ref, 2)])
            main = "mean_step_ms" if p in "AB" else "mean_rtf"
            d = describe([m[main] for m in done if m.get(main) is not None])
            unit = "ms" if p in "AB" else "x"
            line = "  %s %3d agents: %d/%d runs finished" % (p, n, len(done), len(runs))
            if d["n"]:
                line += ", %s %s %s" % (main, fmt(d["mean"], 2), unit)
                if "ci95" in d:
                    line += " ± %s (95 %% CI), min–max %s–%s" % (fmt(d["ci95"], 2), fmt(d["min"], 2), fmt(d["max"], 2))
            ref = REFERENCE.get((p, n))
            if ref is not None:
                line += "; reference %s %s" % (fmt(ref, 2), unit)
            if p in "AB":
                p95 = describe([m["p95_ms"] for m in done if m.get("p95_ms") is not None])
                mx = describe([m["t5_max_med"] for m in done if m.get("t5_max_med") is not None])
                if p95["n"]:
                    line += "; p95 %s ms" % fmt(p95["mean"], 2)
                if mx["n"]:
                    line += "; max/med %s×" % fmt(mx["mean"], 1)
            print(line)
    print("  wrote %s and %s" % (per_run, summ))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("run_dir")
    r.add_argument("--protocol", required=True, choices="ABCD")
    mc = sub.add_parser("machine")
    mc.add_argument("path")
    s = sub.add_parser("summary")
    s.add_argument("--repeats-dir", required=True)
    s.add_argument("--out-dir")
    s.add_argument("--point")
    args = ap.parse_args()
    if args.cmd == "run":
        m = run_metrics(args.run_dir, args.protocol)
        # key=value pairs on one line for repeat_uuvsim.sh
        print(" ".join("%s=%s" % (k, fmt(m.get(k), 6) if isinstance(m.get(k), float)
                                  else ("-" if m.get(k) is None else m.get(k))) for k in RUN_FIELDS))
    elif args.cmd == "machine":
        print(machine_summary(args.path))
    elif args.cmd == "summary":
        summary(args)
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
