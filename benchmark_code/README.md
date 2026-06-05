# Benchmark Code

This folder contains the benchmark code for five underwater robotics simulators. Each benchmark evaluates multi-agent scalability using standardized protocols; the vehicle model varies per simulator.

## Simulators

| Subfolder | Simulator | Vehicle(s) | Notes |
|-----------|-----------|------------|-------|
| `holoocean_benchmark/` | [HoloOcean](https://holoocean.readthedocs.io/) (Unreal Engine) | BlueROV2 | Results from v2.3.0 |
| `stonefish_benchmark/` | [Stonefish](https://stonefish.readthedocs.io/) | BlueROV2 | Requires Stonefish workspace |
| `lotusim_benchmark/` | [LOTUSim](https://github.com/naval-group/LOTUSim) | BlueROV2, LRAUV | Unity Linux executable |
| `lrauvsim_benchmark/` | [LRAUVSim](https://github.com/osrf/lrauv) (Gazebo Garden) | LRAUV | ROS 2 colcon workspace |
| `uuv_benchmark/` | [UUVSim](https://github.com/uuvsimulator/uuv_simulator) (Gazebo 9) | BlueROV2 | catkin workspace |

## Benchmark protocols

All simulators are evaluated using standardized protocols:

| Protocol | Step | Rendering | Description |
|----------|------|-----------|-------------|
| A | 200 ms | ON  | Real-time HITL — maximum swarm size for human supervision |
| B | 30 ms  | ON  | Autonomous control — maximum swarm size for a 33 Hz control loop |
| C | 30 ms  | ON  | FTRT rendering simulation — max RTF with rendering |
| D | 30 ms  | OFF | FTRT headless simulation — max RTF without rendering |

Each subfolder contains a README with simulator-specific setup and usage instructions.

## Results

Benchmark results (raw data, summary CSVs, and figures) are stored in [`benchmark_results/`](../benchmark_results/).
