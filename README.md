# Benchmark of Maritime Robotic Simulators

This repository contains benchmarking code and results for five underwater robotics simulators: **HoloOcean**, **Stonefish**, **LOTUSim**, **UUVSim**, and **LRAUVSim**. Benchmarks use the BlueROV2 model (HoloOcean, Stonefish, UUVSim, LOTUSim) and the LRAUV model (LRAUVSim, LOTUSim), and evaluate multi-agent scalability across standardized protocols.

```text
├── benchmark_code
│   ├── holoocean_benchmark     # HoloOcean
│   ├── stonefish_benchmark     # Stonefish
│   ├── lotusim_benchmark       # LOTUSim
│   ├── lrauvsim_benchmark      # LRAUVSim 
│   └── uuv_benchmark           # UUVSim
└── benchmark_results
    ├── holoocean               # HoloOcean results and figures
    ├── stonefish               # Stonefish results and figures
    └── gazebo_based            # UUVSim, LOTUSim, LRAUVSim results and comparisons
```

## Cloning

```sh
git clone --recurse-submodules https://github.com/IRL-Crossing-CNRS/maritime_simulator_benchmark
```

Or after cloning:

```sh
git submodule update --init --recursive
```

## Benchmark Protocols

All simulators are evaluated against the same four protocols, differing in simulation step size, rendering, and intended use case:

| Protocol | Step | Rendering | Purpose | Key question |
|----------|------|-----------|---------|--------------|
| **A** | 200 ms | ON | Real-time HITL supervision | How many agents can a human operator monitor at 5 Hz? |
| **B** | 30 ms | ON | Autonomous control loop | How many agents fit a 33 Hz closed-loop controller? |
| **C** | 30 ms | ON | FTRT rendering simulation | What RTF does the simulator reach with rendering? |
| **D** | 30 ms | OFF | FTRT headless simulation | What RTF does the simulator reach without rendering? |

Protocol support per simulator:

| Simulator | A | B | C | D |
|-----------|---|---|---|---|
| HoloOcean | ✓ | ✓ | — | ✓ |
| Stonefish | ✓ | ✓ | ✓ | ✓ |
| LOTUSim   | ✓ | ✓ | ✓ | ✓ |
| UUVSim    | ✓ | ✓ | ✓ | ✓ |
| LRAUVSim  | ✓ | — | — | — |

> **LRAUVSim** is limited to Protocol A: its fixed 120 ms `update_rate` is incompatible with the 30 ms step budget required by Protocols B–D.
> **HoloOcean** does not support Protocol C: its lockstep architecture makes Protocol C structurally equivalent to Protocol B.

Protocols A and B measure **maximum swarm size** before a time budget is exceeded (200 ms for A, 30 ms for B). Protocols C and D measure the **Real-Time Factor (RTF)**: how many times faster than wall-clock the simulator runs. RTF > 1 means faster than real time (FTRT).

## Repeated runs

Each size below was run 5 times on the same host. A run is within budget if its mean step stays within the step + 2 %: 204 ms for A, 30.91 ms for B, and 122.4 ms for LRAUVSim (120 ms + 2 %). Values are mean ± 95 % confidence interval over the 5 runs (Student t), with the min–max of the run means in brackets.

### Protocols A and B: maximum swarm size

| Simulator | Prot. | Agents | Mean step (ms) | Runs within budget | p95 (ms) | p99 (ms) | max (ms) |
|---|---|---|---|---|---|---|---|
| HoloOcean | A | 3205 | 203.8 ± 0.8 (202.7–204.3) | 2/5 | 216.9 ± 1.3 | 236.6 ± 0.4 | 246.6 ± 4.3 |
| HoloOcean | A | 3210 | 202.6 ± 1.2 (201.3–203.8) | 5/5 | 216.4 ± 1.5 | 236.1 ± 2.1 | 245.4 ± 2.5 |
| HoloOcean | B | 10 | 31.3 ± 0.2 (31.1–31.4) | 0/5 | 36.6 ± 0.1 | 38.2 ± 0.2 | 40.9 ± 0.7 |
| Stonefish | A | 8 | 200.1 ± 0.0 | 5/5 | 200.2 ± 0.0 | 200.2 ± 0.0 | 200.5 ± 0.2 |
| Stonefish | A | 9 | crash (signal 11) | 0/5 | – | – | – |
| Stonefish | B | 8 | 30.3 ± 0.0 | 5/5 | 30.5 ± 0.0 | 30.6 ± 0.0 | 31.3 ± 0.3 |
| Stonefish | B | 9 | crash (signal 11) | 0/5 | – | – | – |
| LRAUVSim | A | 115 | 121.9 ± 0.1 (121.8–122.0) | 5/5 | 127.6 ± 0.3 | 130.6 ± 0.4 | 144.5 ± 8.1 |
| LRAUVSim | A | 120 | 123.8 ± 0.2 (123.7–124.1) | 0/5 | 131.4 ± 0.3 | 134.2 ± 0.5 | 145.3 ± 6.7 |
| UUVSim | A | 130 | 203.6 ± 1.2 (202.6–204.8) | 3/5 | 277.5 ± 1.1 | 292.4 ± 2.2 | 313.7 ± 12.9 |
| UUVSim | A | 135 | 216.9 ± 2.4 (214.4–219.5) | 0/5 | 293.7 ± 3.7 | 310.9 ± 4.4 | 324.3 ± 6.7 |
| UUVSim | B | 50 | 27.1 ± 0.2 (26.9–27.3) | 5/5 | 37.2 ± 0.5 | 43.7 ± 1.2 | 60.3 ± 3.9 |
| UUVSim | B | 55 | 31.5 ± 0.3 (31.1–31.7) | 0/5 | 41.3 ± 0.4 | 46.7 ± 1.2 | 63.4 ± 3.0 |
| LOTUSim (BlueROV2) | A | 390 | 193.0 (191.0–194.5) | 3/3 | 217.1 | – | – |
| LOTUSim (BlueROV2) | A | 400 | 202.5 ± 10.0 (189.8–216.3) | 4/6 | 226.8 ± 12.0 | – | – |
| LOTUSim (LRAUV) | A | 750 | 199.4 | 1/1 | 234.2 | – | – |
| LOTUSim (BlueROV2) | B | 50 | 30.2 (30.2–30.2) | 2/2 | 39.8 | – | – |
| LOTUSim (BlueROV2) | B | 55 | 32.7 | 0/1 | 43.3 | – | – |
| LOTUSim (LRAUV) | B | 85 | 30.3 | 1/1 | 40.8 | – | – |
| LOTUSim (LRAUV) | B | 90 | 32.9 | 0/1 | 43.8 | – | – |

### Protocols C and D: real-time factor

| Simulator | Prot. | Agents | RTF | Runs above 2× |
|---|---|---|---|---|
| HoloOcean | D | 1 | 1.040 ± 0.007 (1.034–1.048) | – |
| Stonefish | D | 1 | 230.1 ± 8.7 (222.0–236.0) | – |
| Stonefish | D | 90 | 2.32 ± 0.02 (2.29–2.34) | 5/5 |
| UUVSim | C | 1 | 167.0 ± 2.0 (165.4–169.3) | – |
| UUVSim | C | 30 | 2.47 ± 0.05 (2.43–2.54) | 5/5 |
| UUVSim | C | 35 | 2.01 ± 0.03 (1.99–2.04) | 3/5 |
| UUVSim | D | 1 | 184.6 ± 1.5 (183.3–186.1) | – |
| UUVSim | D | 35 | 2.10 ± 0.07 (2.04–2.16) | 5/5 |
| UUVSim | D | 40 | 1.68 ± 0.02 (1.65–1.70) | 0/5 |
| LOTUSim (BlueROV2) | C | 1 | 11.2 ± 0.6 (10.4–11.7) | – |
| LOTUSim (LRAUV) | C | 1 | 16.4 ± 0.3 (16.1–16.7) | – |
| LOTUSim (BlueROV2) | D | 1 | 16.1 ± 0.5 (15.5–16.5) | – |
| LOTUSim (BlueROV2) | D | 23 | 1.96 ± 0.04 (1.92–2.01) | 1/5 |
| LOTUSim (BlueROV2) | D | 25 | 1.77 ± 0.02 (1.75–1.79) | 0/5 |

LOTUSim runs are still in progress (some A and B sizes have fewer than 5 runs). Its A and B mean step is the `Update (ms)` timing, and its p95 is the full step (`Preparation Update (ms)`).

UUVSim sizes were chosen by a single-run sweep (A: 130, 135; B: 30 to 55), then each was run 5 times.

Per-run values and traces: [HoloOcean](benchmark_results/holoocean/data/holoocean_repeats/README.md), [Stonefish](benchmark_results/stonefish/data/stonefish_repeats/README.md), [LRAUVSim](benchmark_results/gazebo_based/src/benchmark_results/benchmark_lrauv/results/lrauvsim_repeats_per_run.csv), [UUVSim](benchmark_results/gazebo_based/src/benchmark_results/benchmark_bluerov/data/uuvsim_repeats/README.md).

## benchmark_code

Contains the code to run benchmarks for all five simulators. Each simulator has its own subfolder with a README explaining how to install dependencies and run the benchmark.

See [`benchmark_code/README.md`](benchmark_code/README.md) for full protocol definitions and per-simulator setup.

## benchmark_results

Contains raw data, summary CSVs, and figures produced by each benchmark, organized by simulator.

- `holoocean/` — HoloOcean v2.3.0 results (Protocols A, B, D)
- `stonefish/` — Stonefish results (Protocols A, B, C, D)
- `gazebo_based/` — UUVSim (Protocols A, B, C, D), LOTUSim (Protocols A, B, C, D), LRAUVSim (Protocol A): raw data, per-simulator summaries, and cross-simulator comparisons

See [`benchmark_results/README.md`](benchmark_results/README.md) for details.
