#
# Copyright (c) 2025 IRL Crossing
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0
#
"""
@file process_lrauvsim_repeats.py
@author IRL Crossing

@brief Summarise the repeated LRAUVSim runs around 115 and 120 agents.

@details
Reads data/lrauvsim_repeats/<n_agents>/run<k>/{real_update,rtf,render_fps}.csv and the
single reference run data/lrauvsim/<n_agents>/ for comparison. Statistics use the same
filter as process_lrauvsim.py (RealUpdateDuration > 0) restricted to 0 < SimTime <= 330 s
so that every run covers the same simulated window.

Outputs:
    - results/lrauvsim_repeats_per_run.csv  one row per run (+ the reference run)
    - results/lrauvsim_repeats_summary.csv  mean, sd, 95 % CI (Student t) over the repeats,
                                           95 % prediction interval for a single run,
                                           and the reference value
"""

import csv
import os

import numpy as np

REPEATS_DIR = os.path.join("data", "lrauvsim_repeats")
REFERENCE_DIR = os.path.join("data", "lrauvsim")
OUT_RUNS = os.path.join("results", "lrauvsim_repeats_per_run.csv")
OUT_SUMMARY = os.path.join("results", "lrauvsim_repeats_summary.csv")
SIM_WINDOW_S = 330.0
LATE_MS = 132.0  # 10 % above the nominal 120 ms /stats interval
T_975 = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}
METRICS = ["mean_update_ms", "median_update_ms", "p95_update_ms", "p99_update_ms",
           "max_update_ms", "late_pct", "mean_rtf", "mean_fps"]


def _load(path):
    t, v = [], []
    with open(path) as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            try:
                t.append(float(row[0]))
                v.append(float(row[1]))
            except (ValueError, IndexError):
                continue
    return np.array(t), np.array(v)


def run_metrics(folder):
    """Return the metrics of one run folder."""
    t, upd = _load(os.path.join(folder, "real_update.csv"))
    upd = upd[(upd > 0) & (t <= SIM_WINDOW_S)] * 1000.0
    tr, rtf = _load(os.path.join(folder, "rtf.csv"))
    rtf = rtf[(rtf > 0) & (tr <= SIM_WINDOW_S)]
    _, fps = _load(os.path.join(folder, "render_fps.csv"))
    return {
        "mean_update_ms": upd.mean(),
        "median_update_ms": float(np.median(upd)),
        "p95_update_ms": float(np.percentile(upd, 95)),
        "p99_update_ms": float(np.percentile(upd, 99)),
        "max_update_ms": upd.max(),
        "late_pct": 100.0 * float((upd > LATE_MS).mean()),
        "mean_rtf": rtf.mean(),
        "mean_fps": fps.mean(),
        "n_samples": int(upd.size),
    }


def main():
    per_run, summary = [], []
    for n in sorted((d for d in os.listdir(REPEATS_DIR) if d.isdigit()), key=int):
        runs = sorted(r for r in os.listdir(os.path.join(REPEATS_DIR, n))
                      if r.startswith("run") and r[3:].isdigit())
        if len(runs) < 2:
            continue
        values = [run_metrics(os.path.join(REPEATS_DIR, n, r)) for r in runs]
        for r, m in zip(runs, values):
            per_run.append({"n_agents": int(n), "run": r, **{k: round(m[k], 4) for k in m}})
        pub_dir = os.path.join(REFERENCE_DIR, n)
        pub = run_metrics(pub_dir) if os.path.isdir(pub_dir) else None
        if pub:
            per_run.append({"n_agents": int(n), "run": "reference", **{k: round(pub[k], 4) for k in pub}})

        k = len(values)
        tc = T_975[k - 1]
        for metric in METRICS:
            a = np.array([m[metric] for m in values])
            mean, sd = a.mean(), a.std(ddof=1)
            ci = tc * sd / np.sqrt(k)
            pi = tc * sd * np.sqrt(1 + 1 / k)
            summary.append({
                "n_agents": int(n), "metric": metric, "n_runs": k,
                "mean": round(mean, 4), "sd": round(sd, 4),
                "ci95_low": round(mean - ci, 4), "ci95_high": round(mean + ci, 4),
                "pi95_low": round(mean - pi, 4), "pi95_high": round(mean + pi, 4),
                "min": round(a.min(), 4), "max": round(a.max(), 4),
                "reference": round(pub[metric], 4) if pub else "",
            })
            print(f"  {n:>3s} agents  {metric:17s} {mean:9.3f} ± {ci:6.3f} (95% CI)"
                  + (f"   reference {pub[metric]:9.3f}" if pub else ""))

    os.makedirs("results", exist_ok=True)
    for path, rows in ((OUT_RUNS, per_run), (OUT_SUMMARY, summary)):
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved {path}")


if __name__ == "__main__":
    main()
