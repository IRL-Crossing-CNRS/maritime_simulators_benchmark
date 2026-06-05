# HoloOcean Benchmark Results

This folder contains the benchmark results for [HoloOcean](https://holoocean.readthedocs.io/) v2.3.0, using the BlueROV2 underwater vehicle model. Results were generated with the script [`benchmark_code/holoocean_benchmark/benchmark_2.3.0.py`](../../benchmark_code/holoocean_benchmark/benchmark_2.3.0.py).

## Folder structure

```text
holoocean/
├── data/
│   └── holoocean/
│       ├── protocol_A/    # Real-time HITL — 41 agent counts tested (5 to 3205)
│       ├── protocol_B/    # Autonomous control — 14 agent counts tested (1 to 20)
│       └── protocol_D/    # Headless AI training — 12 agent counts tested (1 to 12)
├── results/
│   └── benchmark_all_protocols.csv   # Aggregated summary across all protocols
└── figures/
    ├── holoocean_protocol_A.eps / .pdf / .png
    ├── holoocean_protocol_B.eps / .pdf / .png
    └── holoocean_protocol_D.eps / .pdf / .png
```

## Data organization

Each protocol folder contains one subfolder per agent count tested. Each subfolder contains two files:

- `simulation_1_raw_metrics.csv` — per-tick measurements (release latency, step time, CPU/GPU usage, etc.)
- `simulation_1_summary.csv` — aggregated statistics for the run (mean, median, RTF, tick rate, etc.)

## Benchmark protocols

| Protocol | Step | Rendering | Description |
|----------|------|-----------|-------------|
| A | 200 ms | ON | Real-time HITL — measures the maximum swarm size sustainable for human supervision |
| B | 30 ms | ON | Autonomous control — measures the maximum swarm size for a 33 Hz control loop |
| D | 30 ms | OFF | FTRT headless — measures RTF vs. agent count |

## Regenerating figures

To regenerate the figures from the aggregated summary:

```bash
cd benchmark_code/holoocean_benchmark
python analyse.py --csv ../../benchmark_results/holoocean/results/benchmark_all_protocols.csv \
                  --outdir ../../benchmark_results/holoocean/figures
```
