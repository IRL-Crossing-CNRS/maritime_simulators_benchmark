# Gazebo-Based Simulator Benchmark Results

This folder contains benchmark results and analysis scripts for three Gazebo-based simulators: **LOTUSim**, **UUVSim**, and **LRAUVSim**. All benchmarks use the BlueROV2 underwater vehicle model.

## Folder structure

```text
gazebo_based/
├── pyproject.toml          # Python package configuration
├── requirements.txt        # Python dependencies (matplotlib, numpy, pandas, scipy)
├── uv.lock                 # Dependency lock file
└── src/
    └── benchmark_results/
        ├── benchmark_accelerated_time/   # Cross-simulator accelerated-time comparisons
        ├── benchmark_bluerov/            # BlueROV2 results: UUVSim vs LOTUSim
        └── benchmark_lrauv/             # LRAUV results: LRAUVSim vs LOTUSim
```

**Inside each subfolder**:

- `data/` — raw input CSV files from benchmark runs
  - `data/lotusim/<config>/` — LOTUSim per-agent raw metrics; the folder name matches the JSON config filename used at run time (without `.json`)
  - `data/lrauvsim/` — LRAUVSim per-agent raw CSVs (`real_update.csv`, `rtf.csv`, `render_fps.csv`)
  - `data/uuv/AB/` — UUVSim per-agent raw CSVs (`update_times.csv`, `benchmark_rtf.csv`, `render_fps.csv`)
  - `data/LRAUVSim_results.csv` / `data/UUVSim_results.csv` — pre-processed summary CSVs (auto-generated)
- `results/` — generated summary CSVs and plots (EPS, PDF, and PNG)
- Python scripts to process raw data and generate plots

### LOTUSim config folder names

Each analysis script expects specific LOTUSim config names under `data/lotusim/`:

| Script | Expected config folder(s) | Protocol |
|--------|--------------------------|---------|
| `benchmark_bluerov/statistics_unity_bluerov.py` | any subfolder of `data/lotusim/` (all loaded automatically) | A & B |
| `benchmark_lrauv/statistics_unity_lrauv.py` | any subfolder of `data/lotusim/` (all loaded automatically) | A |
| `benchmark_accelerated_time/statistics_accelerated_time.py` | `bluerov_sensors_bridge`, `bluerov_sensors_headless_ai`, `lrauv_sensors_bridge_gui` | C & D |

These names correspond to the LOTUSim JSON configuration files used at benchmark time (see [`benchmark_code/lotusim_benchmark/README.md`](../../benchmark_code/lotusim_benchmark/README.md)).

## Simulators covered

| Subfolder | Simulators compared | Vehicle |
|-----------|---------------------|---------|
| `benchmark_accelerated_time/` | LOTUSim, UUVSim, LRAUVSim | BlueROV2 and LRAUV |
| `benchmark_bluerov/` | UUVSim, LOTUSim | BlueROV2 |
| `benchmark_lrauv/` | LRAUVSim, LOTUSim | LRAUV |

## Setup

```bash
cd gazebo_based
pip install -r requirements.txt
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
cd gazebo_based
uv sync
```

## Running the analysis scripts

### Step 1 — Process raw UUVSim / LRAUVSim data (run once after new benchmark data is added)

```bash
# Re-generate UUVSim summary CSV from raw data
cd gazebo_based/src/benchmark_results/benchmark_bluerov
python process_uuvsim.py

# Re-generate LRAUVSim summary CSV from raw data
cd ../benchmark_lrauv
python process_lrauvsim.py
```

### Step 2 — Generate comparison plots

```bash
# Cross-simulator BlueROV2 comparison (UUVSim vs LOTUSim — Protocols A & B)
cd gazebo_based/src/benchmark_results/benchmark_bluerov
python statistics_unity_bluerov.py

# Cross-simulator LRAUV comparison (LRAUVSim vs LOTUSim — Protocol A)
cd ../benchmark_lrauv
python statistics_unity_lrauv.py

# Accelerated-time comparison (UUVSim vs LOTUSim — Protocols C & D)
cd ../benchmark_accelerated_time
python statistics_accelerated_time.py
```

### Additional analysis scripts (LOTUSim-only)

`benchmark_bluerov/` and `benchmark_lrauv/` each contain a second statistics script that analyses LOTUSim data in isolation (no cross-simulator comparison):

| Script | Purpose |
|--------|---------|
| `benchmark_bluerov/statistics_bluerov.py` | Update-time and CPU/GPU statistics across all LOTUSim BlueROV2 configs |
| `benchmark_lrauv/statistics_lrauv.py` | Update-time and CPU/GPU statistics across all LOTUSim LRAUV configs |

These scripts are **not used to generate article figures** — they were used during data exploration to compare different LOTUSim sensor configurations. The cross-simulator figures used in the paper are produced by the `statistics_unity_*.py` scripts above.
