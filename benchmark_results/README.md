# Benchmark Results

This folder contains the benchmark results for all five simulators, organized by simulator family.

## Folder structure

```text
benchmark_results/
├── holoocean/          # HoloOcean v2.3.0 — BlueROV2 benchmark (Protocols A, B, D)
├── stonefish/          # Stonefish — BlueROV2 benchmark (Protocols A, B, C, D)
└── gazebo_based/       # LOTUSim, UUVSim, LRAUVSim — cross-simulator comparisons
```

## Per-simulator folders

### `holoocean/`

Results from the HoloOcean v2.3.0 benchmark using the BlueROV2 vehicle model.

- `data/` — raw per-tick CSV files, organized by protocol and agent count
- `results/` — aggregated summary CSV (`benchmark_all_protocols.csv`)
- `figures/` — generated plots for Protocols A, B, and D

See [`holoocean/README.md`](holoocean/README.md) for details.

### `stonefish/`

Results from the Stonefish benchmark using the BlueROV2 vehicle model.

- `results/` — per-run CSV files and aggregated summary (`benchmark_summary.csv`)
- `figures/` — generated plots for Protocols A, B, C, and D

See [`stonefish/README.md`](stonefish/README.md) for details.

### `gazebo_based/`

Results and analysis scripts for the three Gazebo-based simulators: LOTUSim, UUVSim, and LRAUVSim.

- Includes a Python package with processing scripts and comparative plots (RTF, update times)
- Covers BlueROV2 and LRAUV vehicle models

See [`gazebo_based/README.md`](gazebo_based/README.md) for details.
