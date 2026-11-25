# Stonefish Benchmark

This folder contains the C++ benchmark code for evaluating the [Stonefish](https://stonefish.readthedocs.io/) simulator using the BlueROV2 underwater vehicle model. Benchmarks cover four protocols (A, B, C, D) and measure multi-agent scalability.

The results produced by this benchmark are stored in [`benchmark_results/stonefish/`](../../benchmark_results/stonefish/).

## Folder structure

- `Tests/` — benchmark source code, meant to be added to the Stonefish `Tests` workspace
- `Tests/Data/bluerov2/` — BlueROV2 mesh and texture assets used by the benchmark scenario
- `analyse.py` — reads the summary CSV from `benchmark_results/stonefish/` and generates figures

## Configuration

| **Specification** | **Value** |
|--------------------|-----------|
| Operating System | Ubuntu 24.04 LTS |
| Processor | 13th Gen Intel(R) Core(TM) i9-13980HX |
| RAM | 64 GB |
| GPU | NVIDIA GeForce RTX 4090 Laptop (16 GB VRAM) |
| NVIDIA Driver | 595.71.05 |
| CUDA Version | 13.2 |
| Python Version | 3.12.3 |

## Installation

### 1. Install Stonefish

Follow the [official Stonefish installation guide](https://stonefish.readthedocs.io/en/latest/install.html) to build and install Stonefish from source (or commands down below). The benchmark requires the Stonefish test environment (`Tests/`) to be present.

**Requirements**: Ubuntu 24.04+, CMake, OpenGL 4.3+, a dedicated GPU.

```bash
# Requirements for Stonefish
sudo apt update && sudo apt install git build-essential cmake gcc libglm-dev libsdl2-dev libfreetype6-dev libpcl-dev nlohmann-json3-dev

# Clone Stonefish
git clone https://github.com/patrykcieslak/stonefish.git
```

### 2. Integrate the benchmark into the Stonefish workspace

Copy the contents of this repository's `Tests/` folder into a `Benchmark/` subfolder inside the Stonefish `Tests/` directory:

```text
stonefish/
└── Tests/
    └── Benchmark/
        ├── main.cpp
        ├── BenchmarkManager.cpp / .h
        ├── BenchmarkApp.cpp / .h
        ├── BenchmarkConsoleApp.cpp / .h
        ├── benchmark_config.json
        └── Data/
            └── bluerov2/
```

### 3. Update the Stonefish CMakeLists

Add the following block to `stonefish/Tests/CMakeLists.txt`:

```cmake
add_executable(Benchmark
    Benchmark/main.cpp
    Benchmark/BenchmarkManager.cpp
    Benchmark/BenchmarkApp.cpp
    Benchmark/BenchmarkConsoleApp.cpp
)
target_link_libraries(Benchmark Stonefish_test)
add_definitions(-DDATA_DIR_PATH=\"${CMAKE_CURRENT_SOURCE_DIR}/Benchmark/Data/\")
```

> If you copy the files directly into `Tests/` without a `Benchmark/` subfolder, adjust the `DATA_DIR_PATH` accordingly.

### 4. Build

```bash
cd stonefish
mkdir -p build && cd build
cmake -DBUILD_TESTS=ON -DBUILD_TESTING=ON ..
cmake ..
make -j$(nproc)
```

The `Benchmark` executable is produced in the `build/` directory.

## Benchmark protocols

| Protocol | Step | Rendering | Description |
|----------|------|-----------|-------------|
| A | 200 ms | ON | Real-time HITL — maximum swarm size for human supervision |
| B | 30 ms  | ON | Autonomous control — maximum swarm size for a 33 Hz control loop |
| C | 30 ms  | ON | AI training with rendering |
| D | 30 ms  | OFF | Headless AI training — maximum training throughput |

> Protocols A, B, and C crash at 8 agents due to a rendering constraint. Protocol D (headless) scales to 90+ agents.

## Running the benchmark

Before launching a benchmark run:

- Close all other windows and applications
- Disconnect from the internet
- Disconnect any additional display (second screen...)
- Set the GPU through NVIDIA to performance mode

Each simulation run produces results for **one specific combination of (protocol, agent count, target RTF)**.
To reproduce the complete dataset, run the benchmark individually for every data point listed below.

If you are re-running the full benchmark from scratch on a new machine, clear the previous results first to avoid stale data points from the old run mixing with the new ones:

```bash
rm -rf results/
mkdir results
```

### JSON config format

The recommended way to launch a run is via a JSON config file:

```bash
./Tests/Benchmark --config my_config.json
```

A config file has the following structure:

```json
{
  "output_dir": "results",
  "warmup_steps": 50,
  "measure_seconds": 300,
  "runs": [
    { "protocol": "A", "agents": [1] }
  ]
}
```

| Field | Description |
|-------|-------------|
| `output_dir` | Folder where CSV results are written (created if absent) |
| `warmup_steps` | Number of physics steps discarded before measurement starts (default: 50) |
| `measure_seconds` | Duration of the measurement window in seconds (default: ~300 s) |
| `runs` | List of simulations to execute sequentially (see below) |

Each entry in `runs` specifies one simulation:

| Field | Description |
|-------|-------------|
| `protocol` | `"A"`, `"B"`, `"C"`, or `"D"` |
| `agents` | Array of agent counts — one simulation is launched per value |
| `target_rtf` | *(optional)* Target real-time factor; if omitted, uses the protocol default (RTF = 1 for A and B) |

The recommended approach is to run **one simulation at a time** — one JSON file, one agent count, one `target_rtf`. This makes it easy to monitor progress, re-run a single failed point, and stop between runs if needed.

### How results accumulate

Each completed run is **upserted** into `results/benchmark_summary.csv` keyed on
`(protocol, agents, target_rtf)`. Re-running the same combination overwrites the old result —
no duplicates are created. You can interrupt and resume at any time without losing data.

Raw per-step data is written to individual files (`results/protocol_A_agents_1_steps.csv`, etc.)
and overwritten on each re-run.

---

### Full reproduction — all data points

The sections below list every simulation that was originally run to produce the reference dataset.
**Run them in order, one config file at a time.** All commands assume you are in the `build/` directory.

```bash
mkdir -p results
```

---

#### Protocol A — HITL scalability (rendering ON, step = 200 ms, RTF = 1)

One run per agent count. The run at 8 agents is expected to crash (`signal_11`) —
this is recorded automatically.

Run agent counts one by one:

```bash
# 1 agent
./Tests/Benchmark --config ../Tests/Benchmark/configs/protocol_A_agents_1.json

# 2 agents
./Tests/Benchmark --config ../Tests/Benchmark/configs/protocol_A_agents_2.json

# ... repeat up to 8 agents
```

Example config for **1 agent** (`protocol_A_agents_1.json`):

```json
{
  "output_dir": "results",
  "warmup_steps": 50,
  "measure_seconds": 300,
  "runs": [
    { "protocol": "A", "agents": [1] }
  ]
}
```

Change `"agents": [1]` to `[2]`, `[3]`, … `[8]` for the other runs and launch each config separately. It is possible to list all agent counts in a single JSON file, but this is not recommended — a crash or interruption mid-run makes it harder to track which points have been completed.

---

#### Protocol B — Physics control loop (rendering ON, step = 30 ms, RTF = 1)

Same structure as Protocol A — only the protocol letter changes. One JSON per agent count, from 1 to 8.

```json
{
  "output_dir": "results",
  "warmup_steps": 50,
  "measure_seconds": 300,
  "runs": [
    { "protocol": "B", "agents": [1] }
  ]
}
```

---

#### Protocol C — FTRT rendering (rendering ON, step = 30 ms, RTF uncapped)

For each agent count, the goal is to find the **maximum stable `target_rtf`** by trial: start with a value, run it, then go higher or lower depending on whether it succeeded or crashed (`signal_11`). Each trial is one JSON run.

```json
{
  "output_dir": "results",
  "warmup_steps": 50,
  "measure_seconds": 300,
  "runs": [
    { "protocol": "C", "agents": [1], "target_rtf": 121 }
  ]
}
```

---

#### Protocol D — FTRT headless (rendering OFF, step = 30 ms, RTF uncapped)

Same principle as Protocol C: for each agent count, find the maximum stable `target_rtf` by trial.
Scales to 90 agents (no rendering crash).

```json
{
  "output_dir": "results",
  "warmup_steps": 50,
  "measure_seconds": 300,
  "runs": [
    { "protocol": "D", "agents": [1], "target_rtf": 183 }
  ]
}
```

The reference measurements covered agents 1 to 90, with `target_rtf` values ranging from ~3× (at 90 agents) up to ~183× (at 1 agent). Use those as a starting point and adjust based on your hardware.

---

### Copying results back to the repository

Once all runs are complete, copy the outputs into the repository:

```bash
REPO=/path/to/maritime_simulator_benchmark   # set this to your local clone

cp results/benchmark_summary.csv \
   $REPO/benchmark_results/stonefish/results/benchmark_summary.csv

cp results/protocol_*_steps.csv \
   $REPO/benchmark_results/stonefish/results/
```

## Generating figures

```bash
# SINSTALL PYTHON : https://www.python.org/ftp/python/3.12.3/Python-3.12.3.tar.xz
tar -xf Python-3.12.3.tar.xz
cd Python-3.12.3
./configure --enable-optimizations

sudo apt install python3.12-venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install pandas numpy matplotlib

python3.12 analyse.py \
  --csv ../../benchmark_results/stonefish/results/benchmark_summary.csv \
  --outdir ../../benchmark_results/stonefish/figures
```
