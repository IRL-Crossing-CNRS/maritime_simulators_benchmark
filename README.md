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

## benchmark_code

Contains the code to run benchmarks for all five simulators. Each simulator has its own subfolder with a README explaining how to install dependencies and run the benchmark.

See [`benchmark_code/README.md`](benchmark_code/README.md) for full protocol definitions and per-simulator setup.

## benchmark_results

Contains raw data, summary CSVs, and figures produced by each benchmark, organized by simulator.

- `holoocean/` — HoloOcean v2.3.0 results (Protocols A, B, D)
- `stonefish/` — Stonefish results (Protocols A, B, C, D)
- `gazebo_based/` — UUVSim (Protocols A, B, C, D), LOTUSim (Protocols A, B, C, D), LRAUVSim (Protocol A): raw data, per-simulator summaries, and cross-simulator comparisons

See [`benchmark_results/README.md`](benchmark_results/README.md) for details.
