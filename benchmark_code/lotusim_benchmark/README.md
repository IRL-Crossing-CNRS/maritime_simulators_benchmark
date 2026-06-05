# LOTUSim Multi-Agent Benchmark

This folder contains resources to run the multi-agent benchmark for **LOTUSim**, a Unity-based underwater simulator. Two deployment options are available: a pre-built Docker image (recommended) or a Linux native executable.

**Requirements**: Linux host with Docker installed and an X server running (for GUI display).

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
| Gazebo Version | Harmonic |
| ROS Distribution | ROS 2 Humble |

```text
├── linux_executable/       # Prebuilt Linux executable (Unity)
│   └── Benchmark.x86_64
└── README.md
```

---

## Option 1 — Docker (recommended)

### Why Docker

The Docker image is designed to:

- **Simplify the setup** of LOTUSim and ROS 2 dependencies — no local installation required
- **Provide a preconfigured runtime** for running the benchmark out of the box
- **Ensure reproducible experiments** across different systems

### 1. Get the Docker image

Either pull it from Docker Hub:

```bash
docker pull juliettegrosset/lotusim_scenario:mas_benchmark
```

Or, if you have a saved image as a `.tar` file, load it directly:

```bash
docker load -i lotusim_benchmark.tar
```

### 2. Allow X server access

Before running the container, allow local GUI applications to connect to your X server:

```bash
xhost +
```

### 3. Run the container

```bash
docker run -it \
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    --network host \
    lotusim_scenario:mas_benchmark
```

### 4. Attach to the container from VS Code (optional)

To edit files, run scripts, and debug interactively inside the container:

1. Open VS Code
2. Install the **Dev Containers** extension (formerly *Remote - Containers*)
3. Use **Attach to Running Container** and select `lotusim_scenario:mas_benchmark`

### 5. Configure the benchmark

Before running, adjust the simulation parameters in:

```
lotusim_generic_scenario/src/benchmark_mas/executable/benchmark.sh
```

All available configuration files are located in `lotusim-generic-scenario/simulation_run/config/`.

```sh
# -------------------- Configuration --------------------

# List of configuration JSON files
#CONFIG_FILES=("lrauv_sensors.json")         # Gazebo rendering
CONFIG_FILES=("lrauv_sensors_unity.json")    # Unity rendering (see Option 2 below)

# Uncomment to run multiple configs:
# CONFIG_FILES=("bluerov_gui.json" "bluerov_no-gui.json" "bluerov_sensors.json" ...)

# Agent model type: "lrauv" or "bluerov"
MODEL_TYPE="lrauv"

# Dynamics config: "lrauv-ekman.yml" or "BlueROV2.yml"
YML_FILE="lrauv-ekman.yml"

# Number of agents per simulation run
AGENT_COUNTS=(5)

# Maximum simulation time in seconds
MAX_SIM_TIME=20
```

- Set `CONFIG_FILES` to select which scenarios to run
- Set `MODEL_TYPE` and `YML_FILE` to match the vehicle being benchmarked
- Adjust `AGENT_COUNTS` and `MAX_SIM_TIME` to control scale and duration

---

## Option 2 — Linux Executable (Unity visualization)

Use this option if you want Unity as the renderer alongside the Docker container.

### 1. Make the executable runnable

```bash
chmod +x linux_executable/Benchmark.x86_64
```

### 2. Launch the Unity executable on the host

```bash
./linux_executable/Benchmark.x86_64
```

### 3. Run the benchmark inside Docker

Before launching a benchmark run:

- Close all other windows and applications
- Disconnect from the internet
- Disconnect any additional display (second screen...)
- Set the GPU through NVIDIA to performance mode
- Once LOTUSim opens, extend it to full screen (required for consistent FPS measurement)

With the Unity executable running on the host, start `benchmark.sh` inside the container (step 5 above), using `lrauv_sensors_unity.json` as the config file.

> Unity must be launched **before** the benchmark script — the script connects to it on startup.

Once the benchmark is running, click the Unity window to see the simulation updates.

---

## Collecting benchmark data

LOTUSim writes one subfolder per agent count inside the container, named after the active config file (without `.json`). For example, running with `lrauv_sensors_unity.json` and 10 agents produces:

```
/benchmark_results/lrauv_sensors_unity/10/
    ├── benchmark_results.csv
    ├── config.json
    ├── simulation_1_raw_metrics.csv
    └── simulation_1_summary.csv
```

Copy the results out of the container and into the benchmark results folder. The destination depends on the vehicle model being benchmarked:

```bash
CONFIG=lrauv_sensors_unity   # config file name without .json

# For LRAUV comparisons (LRAUVSim vs LOTUSim)
docker cp <container_id>:/benchmark_results/$CONFIG \
  benchmark_results/gazebo_based/src/benchmark_results/benchmark_lrauv/data/lotusim/$CONFIG

# For BlueROV2 comparisons (UUVSim vs LOTUSim)
docker cp <container_id>:/benchmark_results/$CONFIG \
  benchmark_results/gazebo_based/src/benchmark_results/benchmark_bluerov/data/lotusim/$CONFIG

# For accelerated-time comparisons (Protocols C & D)
docker cp <container_id>:/benchmark_results/$CONFIG \
  benchmark_results/gazebo_based/src/benchmark_results/benchmark_accelerated_time/data/lotusim/$CONFIG
```

> The config name used as the destination folder must match exactly what `statistics_unity_bluerov.py`, `statistics_unity_lrauv.py`, and `statistics_accelerated_time.py` expect. See [`benchmark_results/gazebo_based/README.md`](../../benchmark_results/gazebo_based/README.md) for the expected config names per analysis script.
