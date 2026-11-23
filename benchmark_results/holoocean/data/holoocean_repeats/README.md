# HoloOcean repeated runs

Independent repetitions of the HoloOcean v2.3.0 configurations at the limits reported in
[`../../results/benchmark_all_protocols.csv`](../../results/benchmark_all_protocols.csv), to
measure run-to-run variability. The reference runs are in [`../holoocean/`](../holoocean/).

## Folder structure

```text
holoocean_repeats/
├── protocol_A/
│   ├── 3205/run1..run5      # ceiling of protocol A
│   ├── 3210/run1..run5      # next size above (+ explore1)
│   └── 3250/explore1
├── protocol_B/
│   └── 10/run1..run5        # ceiling of protocol B
└── protocol_D/
    └── 1/run1..run5         # RTF peak of protocol D
```

`run<k>` folders are counted repetitions. `explore<k>` folders are single runs above the
ceiling; they are listed in the per-run results but not included in the statistics.

Each run folder contains:

- `simulation_1_raw_metrics.csv`, `simulation_1_summary.csv`: same files as a reference run
- `benchmark_all_protocols.csv`: the aggregated row of the run
- `agent_counts.json`: the configuration the run was started with

## Setup

Same machine and software as the reference runs: ASUS ROG Strix G834JY (i9-13980HX, 64 GB,
RTX 4090 Laptop), NVIDIA driver 580.126.09, Ubuntu 22.04.5, Python 3.11.15, HoloOcean 2.3.0.
Benchmark script: the script of the reference runs, identical to
[`benchmark_2.3.0.py`](../../../../benchmark_code/holoocean_benchmark/benchmark_2.3.0.py) except
for docstrings and one debug print.

Conditions for all counted runs: on AC power, network disconnected, no other application
open, one display (internal panel, 2560×1600, 60 Hz). For protocols A and B, the HoloOcean
window is kept at its default opening size (not full screen), as for the reference runs.

Each run is started in its own folder, with an `agent_counts.json` holding only the
configuration of that run.

## Statistics

```bash
cd benchmark_results/holoocean
python process_holoocean_repeats.py
```

writes `results/holoocean_repeats_per_run.csv` (one row per run, plus the reference run) and
`results/holoocean_repeats_summary.csv` (mean, standard deviation, 95 % confidence interval
(Student t), 95 % prediction interval for a single run, min, max and reference value).

- `full_frame_ms` and `RTF`: values of the run's aggregated row, over all measured ticks,
  as in the reference results.
- `median_tick_ms`, `p95_tick_ms`, `p99_tick_ms`, `max_tick_ms`: per-tick `full_frame_ms`
  after the first 400 measured ticks, as in `simulation_1_summary.csv`.
- Verdict per run: protocol A passes if `full_frame_ms` ≤ 204 ms (200 ms step + 2 %),
  protocol B if `full_frame_ms` ≤ 31 ms.
