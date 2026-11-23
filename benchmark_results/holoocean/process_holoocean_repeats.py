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
@file process_holoocean_repeats.py
@author IRL Crossing

@brief Summarise the repeated HoloOcean runs around the reference ceilings.

@details
Reads data/holoocean_repeats/protocol_<P>/<n>/run<k>/ (counted repetitions) and
data/holoocean_repeats/protocol_<P>/<n>/explore<k>/ (exploratory runs above the reference
ceiling, listed but not counted), and the single reference run
data/holoocean/protocol_<P>/<n>/ + results/benchmark_all_protocols.csv for comparison.

Two definitions are used, as in the benchmark script:
    - full_frame_ms and RTF of a run: the values of its benchmark_all_protocols.csv row,
      computed over ALL measured ticks (no slice), i.e.
          full_frame_ms = wall_elapsed_s * 1000 / ticks_done
          RTF           = ticks_done * dt_s / total_compute_s
      These are the definitions of the reference CSV; verdicts and the comparison with
      the reference run use them.
    - tick distribution (median / p95 / p99 / max of the per-tick full_frame_ms column of
      simulation_1_raw_metrics.csv): computed after discarding the first SLICE_INDEX = 400
      measured ticks, the window of simulation_1_summary.csv.

Verdict per run (mean full_frame_ms): A <= 204 ms (200 ms + 2 %), B <= 31 ms
(PRACTICAL_LIMIT_MS of analyse.py). D has no budget. Proportions are reported as they are.

Outputs:
    - results/holoocean_repeats_per_run.csv  one row per run (+ exploratory runs, + reference)
    - results/holoocean_repeats_summary.csv  mean, sd, 95 % CI (Student t), 95 % prediction
                                            interval for a single run, min, max and the
                                            reference value
"""

import csv
import os
import re

import numpy as np

REPEATS_DIR = os.path.join("data", "holoocean_repeats")
REFERENCE_DIR = os.path.join("data", "holoocean")
REFERENCE_CSV = os.path.join("results", "benchmark_all_protocols.csv")
OUT_RUNS = os.path.join("results", "holoocean_repeats_per_run.csv")
OUT_SUMMARY = os.path.join("results", "holoocean_repeats_summary.csv")
SLICE_INDEX = 400
LIMIT_MS = {"A": 204.0, "B": 31.0}
T_975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}
METRICS = ["full_frame_ms", "RTF", "median_tick_ms", "p95_tick_ms", "p99_tick_ms", "max_tick_ms"]


def _master_row(path, proto, n):
    if not os.path.isfile(path):
        return None
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row["protocol"] == proto and int(row["n"]) == n:
                return row
    return None


def run_metrics(master_csv, raw_csv, proto, n):
    """Metrics of one run, or None if it produced no result."""
    row = _master_row(master_csv, proto, n)
    if row is None or not os.path.isfile(raw_csv):
        return None
    with open(raw_csv, newline="") as f:
        ticks = np.array([float(r["full_frame_ms"]) for r in csv.DictReader(f)])
    w = ticks[SLICE_INDEX:]
    return {
        "full_frame_ms": float(row["full_frame_ms"]),
        "RTF": float(row["RTF"]),
        "median_tick_ms": float(np.median(w)),
        "p95_tick_ms": float(np.percentile(w, 95)),
        "p99_tick_ms": float(np.percentile(w, 99)),
        "max_tick_ms": float(w.max()),
        "ticks_done": int(row["ticks_done"]),
    }


def verdict(proto, m):
    if proto not in LIMIT_MS:
        return ""
    return "pass" if m is not None and m["full_frame_ms"] <= LIMIT_MS[proto] else "fail"


def summarise(proto, n, runs, ref):
    """Rows of the summary for the counted runs of one configuration."""
    ok = [m for m in runs if m is not None]
    n_pass = sum(verdict(proto, m) == "pass" for m in runs)
    print(f"\n  {proto} n={n}: {len(ok)}/{len(runs)} runs with a result"
          + (f", {n_pass}/{len(runs)} pass (<= {LIMIT_MS[proto]:g} ms)" if proto in LIMIT_MS else ""))
    k = len(ok)
    rows = []
    for metric in METRICS if k else []:
        a = np.array([m[metric] for m in ok])
        mean = a.mean()
        sd = a.std(ddof=1) if k > 1 else float("nan")
        tc = T_975.get(k - 1, 1.96)
        ci = tc * sd / np.sqrt(k) if k > 1 else float("nan")
        pi = tc * sd * np.sqrt(1 + 1 / k) if k > 1 else float("nan")
        rows.append({
            "protocol": proto, "n_agents": n, "metric": metric,
            "n_runs": len(runs), "n_pass": n_pass if proto in LIMIT_MS else "",
            "mean": round(mean, 4), "sd": round(sd, 4),
            "ci95_low": round(mean - ci, 4), "ci95_high": round(mean + ci, 4),
            "pi95_low": round(mean - pi, 4), "pi95_high": round(mean + pi, 4),
            "min": round(a.min(), 4), "max": round(a.max(), 4),
            "reference": round(ref[metric], 4) if ref else "",
        })
        print(f"    {metric:15s} {mean:9.3f} ± {ci:7.3f} (95% CI)  range [{a.min():.3f}, {a.max():.3f}]"
              + (f"   reference {ref[metric]:9.3f}" if ref else ""))
    return rows


def main():
    runs = []  # (proto, n, label, run folder)
    for pdir in sorted(os.listdir(REPEATS_DIR)):
        if not pdir.startswith("protocol_"):
            continue
        proto = pdir.split("_")[1]
        for n in sorted((d for d in os.listdir(os.path.join(REPEATS_DIR, pdir)) if d.isdigit()), key=int):
            for label in os.listdir(os.path.join(REPEATS_DIR, pdir, n)):
                if re.fullmatch(r"(run|explore)\d+", label):
                    runs.append((proto, int(n), label, os.path.join(REPEATS_DIR, pdir, n, label)))
    runs.sort(key=lambda r: (r[0], r[1], r[2].rstrip("0123456789"), int(re.sub(r"\D", "", r[2]))))

    per_run, summary = [], []
    for proto, n in sorted({(r[0], r[1]) for r in runs}):
        counted = []
        for _, _, label, folder in (r for r in runs if r[:2] == (proto, n)):
            m = run_metrics(os.path.join(folder, "benchmark_all_protocols.csv"),
                            os.path.join(folder, "simulation_1_raw_metrics.csv"), proto, n)
            is_counted = label.startswith("run")
            per_run.append({"protocol": proto, "n_agents": n, "run": label,
                            "counted": int(is_counted), "verdict": verdict(proto, m),
                            **{k: round(v, 4) for k, v in (m or {}).items()}})
            if is_counted:
                counted.append(m)

        ref_dir = os.path.join(REFERENCE_DIR, f"protocol_{proto}", str(n))
        ref = run_metrics(REFERENCE_CSV, os.path.join(ref_dir, "simulation_1_raw_metrics.csv"), proto, n)
        if ref:
            per_run.append({"protocol": proto, "n_agents": n, "run": "reference",
                            "counted": 0, "verdict": verdict(proto, ref),
                            **{k: round(v, 4) for k, v in ref.items()}})

        if counted:
            summary += summarise(proto, n, counted, ref)

    os.makedirs("results", exist_ok=True)
    for path, rows in ((OUT_RUNS, per_run), (OUT_SUMMARY, summary)):
        fields = []
        for r in rows:
            fields += [k for k in r if k not in fields]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved {path}")


if __name__ == "__main__":
    main()
