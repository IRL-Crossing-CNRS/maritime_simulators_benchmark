# UUVSim repeated runs

Independent repetitions of the UUVSim (BlueROV2) configurations at the limits of each
protocol, to measure run-to-run variability. The reference runs are
[`../uuv/AB/`](../uuv/AB/) for protocols A and B and
[`../../../benchmark_accelerated_time/data/uuvsim/`](../../../benchmark_accelerated_time/data/uuvsim/)
for protocols C and D.

## Folder structure

```text
uuvsim_repeats/
├── protocol_A/
│   ├── 130/probe1, run1..run5   # ceiling of protocol A
│   └── 135/probe1, run1..run5   # next size above
├── protocol_B/
│   ├── 30, 35, 40, 45/probe1    # ceiling search, one run per size
│   ├── 50/probe1, run1..run5    # ceiling of protocol B
│   └── 55/probe1, run1..run5    # next size above
├── protocol_C/
│   └── 1/run1..run5             # RTF peak, rendering on
└── protocol_D/
    ├── 1/run1..run5             # RTF peak, headless
    ├── 35/run1..run5            # largest fleet above 2x
    └── 40/run1..run5            # next size above
```

`probe1` folders are the single runs of the ceiling search. They are not part of the five
runs of a point and are not read by `process_uuvsim_repeats.py`.

Each run folder contains:

- `update_times.csv`: duration of each `World::Update()` call (ms), whole run
- `benchmark_rtf.csv`, `rtf_samples.csv`: RTF from `/gazebo/performance_metrics`
- `render_fps.csv`: gzclient rendering rate (absent for protocol D, headless)
- `window.json`: measure window (simulated and wall time, line ranges of the CSV files)
- `physics.json`: step size and update rate loaded by Gazebo
- `positions.csv`: spawn poses drawn for the run (seed = run number)
- `metrics.txt`, `status.txt`: metrics of the run and how it ended
- `machine.csv`: fastest core clock, CPU package temperature, battery status, available
  memory and gzserver open files / RSS, sampled every 0.2 s with the run phase
  (`setup`, `measure`, `end`)
- `gzclient_window.txt`: display and gzclient window geometry (protocols A, B and C)

## Setup

| Specification | Value |
|---|---|
| Machine | ASUS ROG Strix G834JY (i9-13980HX, 62 GB, RTX 4090 Laptop 16 GB) |
| Operating system | Ubuntu 18.04.6 LTS, kernel 5.4.0-150 |
| NVIDIA driver | 525.105.17 (570.133.07 for the reference runs) |
| Gazebo / ROS | 9.19.0 / Melodic |
| uuv_simulator / bluerov2 | bfb40cb / 9652544 |

Conditions for all runs: on AC power, network disconnected, no other application open, one
display (internal panel, 2560×1600), NVIDIA PowerMizer set to maximum performance. The
gzclient window keeps its normal size.

Runs are started by
[`repeat_uuvsim.sh`](../../../../../../../benchmark_code/uuv_benchmark/repeat_uuvsim.sh), with
the worlds and launch file of
[`benchmark_code/uuv_benchmark/repeats/`](../../../../../../../benchmark_code/uuv_benchmark/repeats/):

- A: dt 0.2 s, update rate 5 Hz, RTF 1; B: dt 0.03 s, update rate 33.333 Hz, RTF 1;
  C and D: dt 0.03 s, RTF uncapped. Each run checks the values loaded (`physics.json`).
- Current of 0.5 m/s, agents spawned one every 2 s as `spawn_multiple_rovs.py`.
- The measure starts 10 s after `/gazebo/model_states` lists every agent and lasts 300 s
  of wall time. In the reference A/B sweep the spawn overlapped the measure window and the
  RTF was uncapped.
- Every process is killed and checked gone between two runs, followed by 15 s idle.

Campaigns of 2026-11-25: A 130, C and D from 11:39; B from 15:03; A 135 and B 55 from 16:32.
During the measurements the CPU package reached 90–100 °C (`machine.csv`).

## Statistics

```bash
cd benchmark_results/gazebo_based/src/benchmark_results/benchmark_bluerov
python3 process_uuvsim_repeats.py summary --repeats-dir data/uuvsim_repeats --out-dir results
```

writes `results/uuvsim_repeats_per_run.csv` (one row per run) and
`results/uuvsim_repeats_summary.csv` (mean, standard deviation, 95 % confidence interval
(Student t), 95 % prediction interval for a single run, min, max and reference value).

- `mean_step_ms`, `median_ms`, `p95_ms`, `p99_ms`, `max_ms`, `over_budget_pct`: `World::Update()`
  durations over the measure window.
- `t5_iqr_med_pct`, `t5_p95_med`, `t5_max_med`: dispersion ratios over the whole
  `update_times.csv` after the first 10 % of the steps.
- `mean_rtf`, `median_rtf`: `/gazebo/performance_metrics` over the window; `rtf_clock`:
  simulated time / wall time over the window.
- Verdict per run: protocol A passes if `mean_step_ms` ≤ 204 ms (200 ms step + 2 %),
  protocol B if `mean_step_ms` ≤ 30.91 ms (30.30 ms step + 2 %). C and D are compared with
  the reference RTF (±10 %); D at 35 agents must stay above 2x.

| Point | Runs | Result (mean ± 95 % CI, min–max) | Reference |
|---|---|---|---|
| A 130 | 5 | 203.56 ± 1.18 ms, 202.55–204.85 | – |
| A 135 | 5 | 216.86 ± 2.42 ms, 214.37–219.49 | – |
| B 50 | 5 | 27.06 ± 0.17 ms, 26.93–27.28 | – |
| B 55 | 5 | 31.52 ± 0.33 ms, 31.05–31.71 | – |
| C 1 | 5 | RTF 167.01 ± 1.99, 165.42–169.30 | 189.01 |
| D 1 | 5 | RTF 184.61 ± 1.51, 183.28–186.08 | 214.98 |
| D 35 | 5 | RTF 2.10 ± 0.07, 2.04–2.16 | 2.25 |
| D 40 | 5 | RTF 1.68 ± 0.02, 1.65–1.70 | 1.85 |
