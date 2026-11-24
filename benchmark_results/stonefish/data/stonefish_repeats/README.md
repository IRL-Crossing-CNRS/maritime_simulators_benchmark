# Stonefish repeated runs

Independent repetitions of the Stonefish configurations at the limits reported in
[`../../results/benchmark_summary.csv`](../../results/benchmark_summary.csv), to measure
run-to-run variability. The reference runs are the `protocol_*_steps.csv` files of
[`../../results/`](../../results/).

## Folder structure

```text
stonefish_repeats/
├── protocol_A/
│   ├── 8/run1..run5         # ceiling of protocol A
│   └── 9/run1..run5         # next size above (crashes at start-up)
├── protocol_B/
│   ├── 8/run1..run5         # ceiling of protocol B
│   └── 9/run1..run5         # next size above (crashes at start-up)
└── protocol_D/
    ├── 1/run1..run5         # RTF peak of protocol D (target RTF 1000)
    └── 90/run1..run5        # largest fleet of protocol D (target RTF 5)
```

Each run folder contains:

- `config.json`: the configuration the run was started with
- `benchmark_summary.csv`: the aggregated row of the run, as in the reference summary
- `protocol_<P>_agents_<N>_rtf_<R>_steps.csv`: per-step metrics, same format as a reference run
  (absent when the run crashed before its measurement)
- `machine.csv` (protocol D, and run5 of B at 8 agents): fastest core clock, CPU package
  temperature and battery status sampled every 0.2 s, with the phase of the run
  (`setup`, `measure`, `end`)

## Setup

Same machine and software as the reference runs: ASUS ROG Strix G834JY (i9-13980HX, 64 GB,
RTX 4090 Laptop), Ubuntu 24.04.4, kernel 6.17.0-29, Stonefish 1.6.0 (commit 09208f9) built in
Release with GCC 13.3, benchmark code of
[`benchmark_code/stonefish_benchmark/`](../../../../benchmark_code/stonefish_benchmark/).
The NVIDIA driver is 595.99.02 (595.71.05 for the reference runs); protocol D runs headless
and does not use it.

Conditions for all runs: on AC power, network disconnected, no other application open, one
display (internal panel, 2560×1600), power profile `performance`. The battery was full for
protocol D and run5 of B at 8 agents (`machine.csv`); it was not recorded for the other runs.
For protocols A and B, the Stonefish window keeps the size set by the benchmark
(960 × 540), as for the reference runs.

Each run is started in its own folder by
[`repeat_stonefish.sh`](../../../../benchmark_code/stonefish_benchmark/repeat_stonefish.sh),
with a `config.json` holding only the configuration of that run. Protocols A and B were run
on 2026-11-24 from 17:03, run5 of B at 8 agents at 23:52, and protocol D at 23:21.

Run5 of B at 8 agents completed its measurement (9900 steps, full per-step trace) and then
crashed on exit (signal 11), before writing its summary row. Its metrics are computed from
its trace, as the benchmark computes them, and its status is `crash_on_exit`.

During protocol D the CPU package reached 96–99 °C and the fastest core ran at 5.0–5.3 GHz
during the measurements (maximum 5.6 GHz), see `machine.csv`. Across the runs at 1 agent,
the RTF is proportional to that clock (44.3–44.6 RTF per GHz).

## Statistics

```bash
cd benchmark_results/stonefish
python process_stonefish_repeats.py
```

writes `results/stonefish_repeats_per_run.csv` (one row per run, plus the reference run) and
`results/stonefish_repeats_summary.csv` (mean, standard deviation, 95 % confidence interval
(Student t), 95 % prediction interval for a single run, min, max and reference value).

- `mean_step_ms`, `mean_rtf` and `mean_fps`: values of the run's aggregated row, over all
  measured steps, as in the reference results.
- `median_step_ms`, `p95_step_ms`, `p99_step_ms`, `max_step_ms` and the ratios
  `iqr_over_median_pct`, `p95_over_median`, `max_over_median`: per-step `step_time_ms` after
  the first 10 % of the measured steps. The reference per-step trace of A at 8 agents is
  empty, so these reference values are blank for that point.
- Verdict per run: protocol A passes if `mean_step_ms` ≤ 204 ms (200 ms step + 2 %),
  protocol B if `mean_step_ms` ≤ 30.91 ms (30.30 ms step + 2 %). A run that crashes before the
  end of its measurement fails.
