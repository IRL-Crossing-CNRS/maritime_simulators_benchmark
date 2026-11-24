# Stonefish Benchmark Results

This folder contains the benchmark results for [Stonefish](https://stonefish.readthedocs.io/), using the BlueROV2 vehicle model. Results were generated with the C++ benchmark in [`benchmark_code/stonefish_benchmark/`](../../benchmark_code/stonefish_benchmark/).

## Folder structure

```text
stonefish/
├── data/
│   └── stonefish_repeats/                  # Five repeated runs at the limits (see its README)
├── process_stonefish_repeats.py            # Statistics over the repeated runs
├── results/
│   ├── benchmark_summary.csv               # Aggregated summary across all protocols and agent counts
│   ├── protocol_<P>_agents_<N>_rtf_<R>_steps.csv   # One file per run
│   └── stonefish_repeats_*.csv             # Per-run and summary statistics of the repeated runs
└── figures/
    ├── stonefish_protocol_A.eps / .pdf / .png
    ├── stonefish_protocol_B.eps / .pdf / .png
    ├── stonefish_protocol_C.eps / .pdf / .png
    └── stonefish_protocol_D.eps / .pdf / .png
```

## Data format

### Per-run CSVs (`results/protocol_*.csv`)

Each file corresponds to one simulation run (one protocol, one agent count, one RTF target). Columns:

| Column | Description |
|--------|-------------|
| `protocol` | Protocol tag (e.g. `A-human-loop`) |
| `agents` | Number of agents in the run |
| `wall_time_s` | Wall-clock timestamp (s) at each measurement |
| `sim_time_s` | Simulated time (s) at each measurement |
| `rtf` | Real-time factor at this step |
| `step_time_ms` | Physics step duration (ms) |
| `fps` | Render frames per second |

### Aggregated summary (`results/benchmark_summary.csv`)

One row per (protocol, agent count, RTF target). Columns:

| Column | Description |
|--------|-------------|
| `protocol` | Protocol tag |
| `agents` | Number of agents |
| `step_size_ms` | Configured physics step size (ms) |
| `target_rtf` | Target RTF (1 = real-time, 0 = uncapped) |
| `rendering` | Whether rendering was enabled |
| `mean_rtf` | Mean RTF over the run |
| `min_rtf` | Minimum RTF |
| `p95_rtf` | 95th-percentile RTF |
| `mean_step_ms` | Mean step duration (ms) |
| `p95_step_ms` | 95th-percentile step duration (ms) |
| `mean_fps` | Mean render FPS |
| `max_fps` | Maximum render FPS |
| `p95_fps` | 95th-percentile render FPS |
| `rtf_ok` | Whether the RTF target was met throughout |
| `status` | `ok` or `crash` |

## Benchmark protocols

| Protocol | Step | Rendering | Metric | Threshold |
|----------|------|-----------|--------|-----------|
| A | 200 ms | ON | mean step ≤ 200 ms | Human perception limit |
| B | 30 ms | ON | mean step ≤ 30 ms | Physics control loop |
| C | 30 ms | ON | RTF | Faster-than-real-time |
| D | 30 ms | OFF | RTF | Faster-than-real-time |

> Protocols A, B, and C crash at 9 agents due to an internal resource limit (`MAX_OCEAN_CURRENTS = 64`, 8 thrusters × 8 agents = 64 evaluations). Protocol D (headless) is unaffected and scales to 90 agents.

## Regenerating figures

```bash
cd benchmark_code/stonefish_benchmark
python3 analyse.py --csv ../../benchmark_results/stonefish/results/benchmark_summary.csv \
                   --outdir ../../benchmark_results/stonefish/figures
```
