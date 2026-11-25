# HoloOcean Benchmark

This folder contains the Python benchmark code for [HoloOcean](https://holoocean.readthedocs.io/), an Unreal Engine-based underwater simulator. Benchmarks evaluate multi-agent scalability using the BlueROV2 vehicle model across three protocols (A, B, D).

The results produced by these scripts are stored in [`benchmark_results/holoocean/`](../../benchmark_results/holoocean/).

## Folder structure

```text
holoocean_benchmark/
├── benchmark_2.3.0.py     # Benchmark script for HoloOcean v2.3.0 (used for the paper)
├── benchmark_2.2.0.py     # Benchmark script for HoloOcean v2.2.0 (kept for reference)
├── analyse.py             # Reads the summary CSV and generates figures
├── agent_counts.json      # Agent counts to test per protocol
└── setup.sh               # Creates conda environment and installs HoloOcean
```

> The results in `benchmark_results/holoocean/` were produced with `benchmark_2.3.0.py`. `benchmark_2.2.0.py` is kept for reference in case you need to reproduce earlier results with the v2.2.0 API.

## Simulation Configuration

All benchmarks were run with the following hardware and software:

| **Specification** | **Value** |
|--------------------|-----------|
| Operating System | Ubuntu 22.04.5 LTS |
| Processor | 13th Gen Intel(R) Core(TM) i9-13980HX |
| RAM | 64 GB |
| GPU | NVIDIA GeForce RTX 4090 Laptop (16 GB VRAM) |
| NVIDIA Driver | 570.133.07 |
| CUDA Version | 13.0 |
| Python Version | 3.10.12 |

## Benchmark protocols

| Protocol | Step | Rendering | Description |
|----------|------|-----------|-------------|
| A | 200 ms | ON | Real-time HITL — measures the maximum swarm size sustainable for human supervision |
| B | 30 ms  | ON | Autonomous control — measures the maximum swarm size for a 33 Hz control loop |
| D | 30 ms  | OFF | Headless AI training — measures training throughput (RTF) vs. agent count |

## Setup

**Requirements**: conda, Python 3.10, Linux, a GitHub account with access to the [HoloOcean repository](https://github.com/byu-holoocean/HoloOcean).

Run the setup script to create a conda environment (`benchmark_holoocean`) and install HoloOcean:

```bash
bash setup.sh
```

This script:
1. Creates a conda environment named `benchmark_holoocean` with Python 3.10
2. Clones and installs the HoloOcean Python client from source
3. Downloads the `Ocean` world binaries required by the benchmark

Once complete, activate the environment before running any benchmark script:

```bash
conda activate benchmark_holoocean
```

## Running the benchmark

Before launching a benchmark run:

- Close all other windows and applications
- Disconnect from the internet
- Disconnect any additional display (second screen...)
- Set the GPU through NVIDIA to performance mode

```bash
conda activate benchmark_holoocean
python benchmark_2.3.0.py --protocol A
python benchmark_2.3.0.py --protocol B --agents 10
python benchmark_2.3.0.py --protocol D --agents 5
```

Raw per-tick data and episode summaries are written to `benchmark_results/holoocean/data/` and `benchmark_results/holoocean/results/`.

## Generating figures

```bash
conda activate benchmark_holoocean
python analyse.py --csv ../../benchmark_results/holoocean/results/benchmark_all_protocols.csv \
                  --outdir ../../benchmark_results/holoocean/figures
```
