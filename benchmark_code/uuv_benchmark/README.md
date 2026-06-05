# UUVSim Benchmark

This folder contains the benchmarking code to evaluate the performance of [UUV Simulator (UUVSim)](https://github.com/uuvsimulator/uuv_simulator) using the BlueROV2 underwater vehicle model. Each scenario simulates multiple BlueROV2 agents under a Gaussian underwater current of 0.5 m/s.

Four benchmark protocols are defined:

- **Protocol A** — Real-time (RTF = 1), physics timestep dt = 200 ms, rendering ON
- **Protocol B** — Real-time (RTF = 1), physics timestep dt = 30 ms, rendering ON
- **Protocol C** — Accelerated-time (RTF uncapped), dt = 30 ms, rendering ON
- **Protocol D** — Accelerated-time (RTF uncapped), dt = 30 ms, headless (no rendering)

The `gz_sim_source_files/` folder contains modified Gazebo 9 source files required to export per-step metrics. The `uuv_ws/catkin_ws/` folder contains the ROS workspace with the benchmark package and the UUVSim submodules.

```text
├── gz_sim_source_files/        # Modified Gazebo 9 source files
│   ├── MainWindow.cc / .hh     # GUI modifications (fps logging)
│   ├── World.cc                # Physics engine modifications (rtf, update_times logging)
│   └── WorldPrivate.hh
└── uuv_ws/
    ├── requirements.txt        # Python dependencies
    └── catkin_ws/src/
        ├── benchmark_bluerov2/ # ROS benchmark package (our code)
        │   └── src/
        │       ├── run_benchmark_uuv.py       # Main benchmark runner
        │       ├── benchmark_subscriber.py    # ROS subscriber for metrics
        │       └── spawn_multiple_rovs.py     # Vehicle spawner
        ├── bluerov2/           # BlueROV2 URDF model (submodule)
        ├── uuv_simulator/      # UUVSim (submodule)
        └── gazebo_ros_pkgs/    # Gazebo ROS packages (submodule)
```

---

## Summary

- [1. Simulation Configuration](#1-simulation-configuration)
- [2. Installation](#2-installation)
- [3. Benchmark Protocols](#3-benchmark-protocols)
- [4. Launch UUV Benchmark](#4-launch-uuv-benchmark)

---

## 1. Simulation Configuration

All benchmarks were run with the following hardware and software:

| **Specification** | **Value** |
|--------------------|-----------|
| Operating System | Ubuntu 18.04.6 LTS |
| Processor | 13th Gen Intel(R) Core(TM) i9-13980HX |
| RAM | 64 GB |
| GPU | NVIDIA GeForce RTX 4090 Laptop (16 GB VRAM) |
| NVIDIA Driver | 570.133.07 |
| CUDA Version | 13.0 |
| Python Version | 2.7.17 |
| Gazebo Version | 9 |
| ROS Distribution | ROS 1 Melodic |

---

## 2. Installation

### 2.1 Install ROS Melodic

Follow the [official ROS Melodic installation guide](http://wiki.ros.org/melodic/Installation/Ubuntu) for Ubuntu 18.04. The `ros-melodic-desktop-full` package includes Gazebo 9.

```bash
sudo sh -c 'echo "deb http://packages.ros.org/ros/ubuntu bionic main" > /etc/apt/sources.list.d/ros-latest.list'
curl -s https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc | sudo apt-key add -
sudo apt update
sudo apt install ros-melodic-desktop-full
```

Add ROS to your shell:

```bash
echo "source /opt/ros/melodic/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

### 2.2 Initialize the submodules

The workspace depends on three submodules: `uuv_simulator`, `bluerov2`, and `gazebo_ros_pkgs`. If you cloned the repository without `--recurse-submodules`, initialize them now:

```bash
# From the root of the repository
git submodule update --init --recursive
```

### 2.3 Install Python dependencies

```bash
cd benchmark_code/uuv_benchmark/uuv_ws
pip install -r requirements.txt
```

### 2.4 Modify and rebuild Gazebo 9 from source

Gazebo must be recompiled with modified source files so that it exports per-step metrics (`rtf.csv`, `update_times.csv`, `fps.csv`) to `~/.ros/` during simulation.

**Step 1** — Clone the Gazebo 9 source:

```bash
git clone https://github.com/osrf/gazebo.git
cd gazebo
git checkout gazebo9
```

**Step 2** — Copy the modified files from this repository into the Gazebo source tree, replacing the originals:

| File | Destination in Gazebo source |
|------|------------------------------|
| `gz_sim_source_files/MainWindow.cc` | `gazebo/gui/MainWindow.cc` |
| `gz_sim_source_files/MainWindow.hh` | `gazebo/gui/MainWindow.hh` |
| `gz_sim_source_files/World.cc` | `gazebo/physics/World.cc` |
| `gz_sim_source_files/WorldPrivate.hh` | `gazebo/physics/WorldPrivate.hh` |

```bash
cp <path_to_repo>/benchmark_code/uuv_benchmark/gz_sim_source_files/MainWindow.cc gazebo/gui/
cp <path_to_repo>/benchmark_code/uuv_benchmark/gz_sim_source_files/MainWindow.hh gazebo/gui/
cp <path_to_repo>/benchmark_code/uuv_benchmark/gz_sim_source_files/World.cc     gazebo/physics/
cp <path_to_repo>/benchmark_code/uuv_benchmark/gz_sim_source_files/WorldPrivate.hh gazebo/physics/
```

**Step 3** — Build and install Gazebo:

```bash
cd gazebo
mkdir build && cd build
cmake ..
make
sudo make install
```

> After this setup, Gazebo will write three CSV files to `~/.ros/` during each simulation run:
> - `rtf.csv` — real-time factor at each simulation step
> - `update_times.csv` — physics engine update frequency
> - `fps.csv` — frames per second at each step

**Step 4** — Add the following lines to your `~/.bashrc` so that the system uses the recompiled Gazebo:

```bash
source /opt/ros/melodic/setup.bash
source /usr/local/share/gazebo/setup.sh
export CMAKE_PREFIX_PATH=/usr/local:$CMAKE_PREFIX_PATH
export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
export PATH=/usr/local/bin:$PATH
```

Then reload your shell:

```bash
source ~/.bashrc
```

---

## 3. Benchmark Protocols

Four protocols are defined to evaluate UUVSim performance and compare it with LOTUSim. To match the LOTUSim comparison setup, all sensors and actuators except the IMU are disabled in the BlueROV2 URDF files:

```
uuv_ws/catkin_ws/src/bluerov2/bluerov2_description/urdf/
```

| Protocol | Physics dt | RTF | Rendering | Description |
|----------|-----------|-----|-----------|-------------|
| **A** | 200 ms | 1 (real-time) | ON | Real-time, large timestep |
| **B** | 30 ms  | 1 (real-time) | ON | Real-time, physics timestep |
| **C** | 30 ms  | uncapped | ON | Accelerated-time, with rendering |
| **D** | 30 ms  | uncapped | OFF | Accelerated-time, headless |

Before each run, open the world file and set the `<physics>` block according to the desired protocol:

```
uuv_ws/catkin_ws/src/uuv_simulator/uuv_gazebo_worlds/worlds/empty_underwater.world
```

### Protocol A — Real-time, dt = 200 ms

```xml
<max_step_size>0.2</max_step_size>
<real_time_factor>1</real_time_factor>
<real_time_update_rate>5</real_time_update_rate>
```

### Protocol B — Real-time, dt = 30 ms

```xml
<max_step_size>0.03</max_step_size>
<real_time_factor>1</real_time_factor>
<real_time_update_rate>33.333</real_time_update_rate>
```

### Protocol C — Accelerated-time, dt = 30 ms, rendering ON

```xml
<max_step_size>0.03</max_step_size>
<real_time_factor>0</real_time_factor>
<real_time_update_rate>0</real_time_update_rate>
```

### Protocol D — Accelerated-time, dt = 30 ms, headless

Same world file settings as Protocol C:

```xml
<max_step_size>0.03</max_step_size>
<real_time_factor>0</real_time_factor>
<real_time_update_rate>0</real_time_update_rate>
```

Rendering is disabled at launch time — add `gui:=false` to the `roslaunch` command in `run_benchmark_uuv.py` (see [Section 4](#4-launch-uuv-benchmark)).

---

## 4. Launch UUV Benchmark

Before launching a benchmark run:

- Close all other windows and applications
- Disconnect from the internet
- Disconnect any additional display (second screen...)
- Set the GPU through NVIDIA to performance mode
- Once Gazebo opens, extend it to full screen (required for consistent FPS measurement)

Open three terminals:

### Terminal 1 — Start ROS

```bash
roscore
```

> To kill all ROS processes at the end of a run: `pkill -f roslaunch && pkill -f gz && killall python`

### Terminal 2 — Build and run the benchmark

```bash
cd benchmark_code/uuv_benchmark/uuv_ws/catkin_ws
catkin_make
source devel/setup.bash
rosrun benchmark_bluerov2 run_benchmark_uuv.py
```

> `catkin_make` is only needed the first time or after modifying source files.

**Protocol D only (headless)** — edit the `roslaunch` line in `run_benchmark_uuv.py` to add `gui:=false`:

```python
gz_proc = subprocess.Popen(["roslaunch", "uuv_gazebo_worlds", "empty_underwater_world.launch", "gui:=false"])
```

### Terminal 3 — Apply underwater current

```bash
cd benchmark_code/uuv_benchmark/uuv_ws/catkin_ws
source devel/setup.bash
rosservice call /hydrodynamics/set_current_velocity "velocity: 0.5
horizontal_angle: 0.0
vertical_angle: 0.0"
```

### Collecting benchmark data

After each simulation run, three CSV files are written to `~/.ros/` by the modified Gazebo 9 build:

- `update_times.csv` — one physics update duration per line (seconds), no header
- `render_fps.csv` — columns `WallTime(s),FPS`

The benchmark runner (`run_benchmark_uuv.py`) also writes:

- `benchmark_rtf.csv` — one RTF sample per line, no header (written to the current working directory)

Collect these three files into the benchmark results folder, organised by agent count:

```bash
N=<n_agents>   # replace with the number of BlueROV2 agents spawned
DEST=benchmark_results/gazebo_based/src/benchmark_results/benchmark_bluerov/data/uuv/AB/$N

mkdir -p $DEST
cp ~/.ros/update_times.csv ~/.ros/render_fps.csv $DEST/
cp benchmark_rtf.csv $DEST/
```

Once data is collected for all agent counts, regenerate the summary CSV:

```bash
cd benchmark_results/gazebo_based/src/benchmark_results/benchmark_bluerov
python process_uuvsim.py
```

### Log cleanup

After many runs, the `~/.ros/log/` folder can become large:

```bash
rosclean check   # check how much space the logs take
rosclean purge   # delete the logs
```
