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
@file process_stonefish_repeats.py
@author IRL Crossing

@brief Summarise the repeated Stonefish runs at the reference points.

@details
Reads <repeats>/protocol_<P>/<n>/run<k>/ (one Benchmark run each: benchmark_summary.csv and
protocol_<P>_agents_<n>_rtf_<target>_steps.csv) and, for comparison, the reference run of the
same (protocol, agents, target RTF) in results/benchmark_summary.csv and its _steps.csv.

Two definitions are used, as in the benchmark:
    - mean_step_ms, mean_rtf and mean_fps of a run: the values of its benchmark_summary.csv
      row, over all measured steps, as in the reference results. Verdicts and the comparison
      with the reference use them.
    - step distribution (median / p95 / p99 / max of step_time_ms, and the dispersion ratios
      IQR/median, p95/median, max/median): computed after discarding the first
      SLICE_FRACTION = 10 % of the measured steps.

Verdict per run (mean step): A <= 204 ms, B <= 30.91 ms (step + 2 %). D has no budget.
A run that crashes before the end of its measurement has no metrics and fails. A run whose
per-step trace is complete but that crashes on exit, before writing its summary row, gets
the status crash_on_exit and the metrics of its trace, computed as the benchmark does
(means of the per-step columns).

Outputs (in --out-dir):
    - stonefish_repeats_per_run.csv  one row per run (+ the reference run)
    - stonefish_repeats_summary.csv  mean, sd, 95 % CI (Student t), 95 % prediction interval
                                     for a single run, min, max and the reference value
"""

import argparse
import contextlib
import csv
import os
import re

import numpy as np

REFERENCE_CSV = os.path.join("results", "benchmark_summary.csv")
SLICE_FRACTION = 0.10
LIMIT_MS = {"A": 200.0 * 1.02, "B": 1000.0 / 33.0 * 1.02}
PROTOCOL_NAMES = {"A": "A-human-loop", "B": "B-control", "C": "C-ai-render", "D": "D-ai-headless"}
STEPS_PER_SECOND = {"A": 5, "B": 33, "C": 33, "D": 33}
RENDERING = {"A": True, "B": True, "C": True, "D": False}
T_975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}
METRICS = ["mean_step_ms", "mean_rtf", "mean_fps", "median_step_ms", "p95_step_ms",
           "p99_step_ms", "max_step_ms", "iqr_over_median_pct", "p95_over_median",
           "max_over_median"]


def rtf_token(target):
    """Target RTF as written in the Benchmark file names (250 -> 250p000000)."""
    return f"{target:.6f}".replace(".", "p")


def summary_row(path, proto, n):
    """Last row of a benchmark_summary.csv for this protocol and agent count."""
    if not os.path.isfile(path):
        return None
    found = None
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row["protocol"] == PROTOCOL_NAMES[proto] and int(row["agents"]) == n:
                found = row
    return found


def config_of(folder):
    """Target RTF and measured seconds of the run started in this folder."""
    with open(os.path.join(folder, "config.json")) as f:
        text = f.read()
    target = float(re.search(r'"target_rtf":\s*([0-9.]+)', text).group(1))
    seconds = float(re.search(r'"measure_seconds":\s*([0-9.]+)', text).group(1))
    return target, seconds


def read_steps(steps_csv):
    if not os.path.isfile(steps_csv):
        return []
    with open(steps_csv, newline="") as f:
        return list(csv.DictReader(f))


def row_from_trace(proto, steps):
    """Summary row of a run that crashed on exit, from its complete per-step trace."""
    mean = lambda col: float(np.mean([float(r[col]) for r in steps]))
    return {
        "status": "crash_on_exit",
        "rendering": "true" if RENDERING[proto] else "false",
        "mean_step_ms": mean("step_time_ms"),
        "mean_rtf": mean("rtf"),
        "mean_fps": mean("fps") if RENDERING[proto] else 0.0,
    }


def run_metrics(row, steps_csv):
    """Metrics of one run, or None if it produced no result."""
    if row is None or row["status"] not in ("ok", "crash_on_exit"):
        return None
    m = {"mean_step_ms": float(row["mean_step_ms"]), "mean_rtf": float(row["mean_rtf"])}
    if row["rendering"] == "true":
        m["mean_fps"] = float(row["mean_fps"])
    steps = [float(r["step_time_ms"]) for r in read_steps(steps_csv)]
    if steps:
        w = np.array(steps[int(len(steps) * SLICE_FRACTION):])
        med = float(np.median(w))
        q1, q3 = np.percentile(w, [25, 75])
        m.update({
            "median_step_ms": med,
            "p95_step_ms": float(np.percentile(w, 95)),
            "p99_step_ms": float(np.percentile(w, 99)),
            "max_step_ms": float(w.max()),
            "iqr_over_median_pct": 100.0 * float(q3 - q1) / med,
            "p95_over_median": float(np.percentile(w, 95)) / med,
            "max_over_median": float(w.max()) / med,
            "steps_done": len(steps),
        })
    return m


def verdict(proto, m):
    if proto not in LIMIT_MS:
        return "" if m is not None else "crash"
    return "pass" if m is not None and m["mean_step_ms"] <= LIMIT_MS[proto] else "fail"


def summarise(proto, n, target, runs, ref, ref_status=None):
    """Rows of the summary for the counted runs of one point, printed as they are built."""
    ok = [m for m in runs if m is not None]
    n_pass = sum(verdict(proto, m) == "pass" for m in runs)
    print(f"\n  {proto} n={n} target_rtf={target:g}: {len(ok)}/{len(runs)} runs with a result"
          + (f", {n_pass}/{len(runs)} pass (<= {LIMIT_MS[proto]:.2f} ms)" if proto in LIMIT_MS else ""))
    rows = []
    if not ok:
        rows.append({
            "protocol": proto, "n_agents": n, "target_rtf": f"{target:g}", "metric": "status",
            "n_runs": len(runs), "n_result": 0, "n_pass": n_pass if proto in LIMIT_MS else "",
            "reference": ref_status or "",
        })
        print(f"    no run reached the end of its measurement (reference: {ref_status})")
    for metric in METRICS:
        values = [m[metric] for m in ok if metric in m]
        if not values:
            continue
        a = np.array(values)
        k = len(a)
        mean = a.mean()
        sd = a.std(ddof=1) if k > 1 else float("nan")
        tc = T_975.get(k - 1, 1.96)
        ci = tc * sd / np.sqrt(k) if k > 1 else float("nan")
        pi = tc * sd * np.sqrt(1 + 1 / k) if k > 1 else float("nan")
        reference = ref.get(metric) if ref else None
        rows.append({
            "protocol": proto, "n_agents": n, "target_rtf": f"{target:g}", "metric": metric,
            "n_runs": len(runs), "n_result": len(ok),
            "n_pass": n_pass if proto in LIMIT_MS else "",
            "mean": round(mean, 4), "sd": round(sd, 4),
            "ci95_low": round(mean - ci, 4), "ci95_high": round(mean + ci, 4),
            "pi95_low": round(mean - pi, 4), "pi95_high": round(mean + pi, 4),
            "min": round(a.min(), 4), "max": round(a.max(), 4),
            "reference": round(reference, 4) if reference is not None else "",
        })
        print(f"    {metric:20s} {mean:10.4f} ± {ci:8.4f} (95% CI)  range [{a.min():.4f}, {a.max():.4f}]"
              + (f"   reference {reference:10.4f}" if reference is not None else ""))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("@details")[0])
    parser.add_argument("--repeats-dir", default=os.path.join("data", "stonefish_repeats"))
    parser.add_argument("--reference-csv", default=REFERENCE_CSV)
    parser.add_argument("--out-dir", default="results")
    parser.add_argument("--point", help="only print the summary of this point, e.g. A:8")
    args = parser.parse_args()
    ref_dir = os.path.dirname(args.reference_csv)

    runs = []  # (proto, n, k, folder)
    for pdir in sorted(os.listdir(args.repeats_dir)):
        if not re.fullmatch(r"protocol_[ABCD]", pdir):
            continue
        proto = pdir[-1]
        for n in (d for d in os.listdir(os.path.join(args.repeats_dir, pdir)) if d.isdigit()):
            for label in os.listdir(os.path.join(args.repeats_dir, pdir, n)):
                if re.fullmatch(r"run\d+", label):
                    runs.append((proto, int(n), int(label[3:]), os.path.join(args.repeats_dir, pdir, n, label)))
    runs.sort()

    per_run, summary = [], []
    for proto, n in sorted({r[:2] for r in runs}):
        counted, target = [], None
        for _, _, k, folder in (r for r in runs if r[:2] == (proto, n)):
            target, seconds = config_of(folder)
            row = summary_row(os.path.join(folder, "benchmark_summary.csv"), proto, n)
            steps = os.path.join(folder, f"protocol_{proto}_agents_{n}_rtf_{rtf_token(target)}_steps.csv")
            if row is not None and row["status"] != "ok":
                trace = read_steps(steps)
                if len(trace) == round(seconds * STEPS_PER_SECOND[proto]):
                    row = row_from_trace(proto, trace)
            m = run_metrics(row, steps)
            per_run.append({"protocol": proto, "n_agents": n, "target_rtf": f"{target:g}",
                            "run": f"run{k}", "counted": 1,
                            "status": row["status"] if row else "no_result",
                            "verdict": verdict(proto, m),
                            **{key: round(v, 4) for key, v in (m or {}).items()}})
            counted.append(m)

        ref_row = None
        with open(args.reference_csv, newline="") as f:
            for row in csv.DictReader(f):
                if (row["protocol"] == PROTOCOL_NAMES[proto] and int(row["agents"]) == n
                        and float(row["target_rtf"]) == target):
                    ref_row = row
        ref_steps = os.path.join(ref_dir, f"protocol_{proto}_agents_{n}_rtf_{rtf_token(target)}_steps.csv")
        ref = run_metrics(ref_row, ref_steps)
        per_run.append({"protocol": proto, "n_agents": n, "target_rtf": f"{target:g}",
                        "run": "reference", "counted": 0,
                        "status": ref_row["status"] if ref_row else "no_result",
                        "verdict": verdict(proto, ref),
                        **{key: round(v, 4) for key, v in (ref or {}).items()}})

        if args.point and args.point != f"{proto}:{n}":
            with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
                summary += summarise(proto, n, target, counted, ref, ref_row and ref_row["status"])
        else:
            summary += summarise(proto, n, target, counted, ref, ref_row and ref_row["status"])

    os.makedirs(args.out_dir, exist_ok=True)
    for name, rows in (("stonefish_repeats_per_run.csv", per_run),
                       ("stonefish_repeats_summary.csv", summary)):
        fields = []
        for r in rows:
            fields += [k for k in r if k not in fields]
        path = os.path.join(args.out_dir, name)
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        if not args.point:
            print(f"Saved {path}")


if __name__ == "__main__":
    main()
