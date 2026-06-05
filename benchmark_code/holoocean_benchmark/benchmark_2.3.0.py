"""
HoloOcean BlueROV2 — Three-Protocol Multi-Agent Benchmark
==========================================================

Protocol A — Real-time HITL  (dt=200ms, TPS=5, rendering ON)
    FPS uncapped. Fixed tick count (5 × 300s = 1500 ticks).
    Stop when full_frame_ms >= 200ms.
    Measures: max swarm size sustainable for human supervision.

Protocol B — Autonomous control  (dt=30ms, TPS=33, rendering ON)
    FPS uncapped. Fixed tick count (33 × 300s = 9900 ticks).
    Stop when full_frame_ms >= 30ms.
    Measures: max swarm size for a 33Hz autonomous control loop.

Protocol D — Headless AI training  (dt=30ms, TPS=33, rendering OFF)
    Rendering disabled via set_render_quality(0) + should_render_viewport(False).
    Fixed tick count (33 × 300s = 9900 ticks). No early stop.
    Uses tps=33 so physics dt=1/33s is correct and agents move under currents.
    RTF = (ticks_done × dt_s) / total_compute_s
    Measures: headless training throughput vs agent count.
    Note: RTF < 1 is expected — Unreal Engine's synchronous tick architecture
    retains overhead even without rendering. This is a platform characteristic,
    not a failure condition.

METRIC REFERENCE
================
MEASURED:
  release_latency_ms   — sem_wait duration = UE overhead to Release().
                         Does NOT include physics, sensors, or render.
  current_injection_ms — Python set_ocean_currents() wall time.
  step_ms              — release_latency + current_injection.
  wall_elapsed_s       — total episode wall time.
  ticks_done           — env.tick() calls completed.
  cpu_pct, gpu_pct     — sampled after each Release().

CALCULATED:
  full_frame_ms        — wall_elapsed_s * 1000 / ticks_done.
                         True average frame time: includes sleep, physics,
                         sensors, and render.
  post_release_work_ms — full_frame_ms - mean_release_latency_ms.
  RTF                  — (ticks_done * dt_s) / total_compute_s,
                         where total_compute_s = sum(full_frame_ms) / 1000.
                         Excludes OS sleep from wall_elapsed.
                         > 1.0 means faster than real time.
  tick_rate_hz         — ticks_done / wall_elapsed_s.
  render_fps_estimate  — 1000 / full_frame_ms (lower bound). NaN if headless.
"""

import os
import gc
import glob
import json
import math
import time
import csv
import resource
import subprocess, signal
import numpy as np
import psutil
import GPUtil
import argparse
import holoocean
from dataclasses import dataclass, field
from scipy.stats import skew, kurtosis


# ─────────────────────────────────────────────────────────────────────────────
# OS file-descriptor limit
# ─────────────────────────────────────────────────────────────────────────────

def _raise_fd_limit() -> None:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    print(f"  [fd] current limits — soft={soft}  hard={hard}")
    if soft < hard:
        resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
        print(f"  [fd] limit raised: {soft} → {hard}")
    else:
        print(f"  [fd] limit already sufficient: {soft}")


def _cleanup_shm(prefix: str = "HOLODECK_MEM") -> int:
    removed = 0
    try:
        for path in glob.glob(f"/dev/shm/{prefix}*"):
            try:
                os.unlink(path)
                removed += 1
            except OSError:
                pass
        if removed:
            print(f"  [shm] cleaned up {removed} leaked segment(s)")
    except OSError as e:
        print(f"  [shm] WARNING: could not scan /dev/shm: {e}")
    return removed


def _kill_holodeck(sleep_s: float = 3.0) -> None:
    try:
        out = subprocess.check_output(["pgrep", "-f", "Holodeck"], text=True)
        for pid in out.strip().splitlines():
            os.kill(int(pid), signal.SIGKILL)
            print(f"  [cleanup] killed Holodeck pid {pid}")
    except subprocess.CalledProcessError:
        pass
    _cleanup_shm()
    time.sleep(sleep_s)

# ─────────────────────────────────────────────────────────────────────────────
# Budget thresholds
# ─────────────────────────────────────────────────────────────────────────────

BUDGET_200_MS = 200.0   # Protocol A: user-perception limit
BUDGET_30_MS  =  30.0   # Protocol B: physics control-loop limit


# ─────────────────────────────────────────────────────────────────────────────
# Protocol definitions
# ─────────────────────────────────────────────────────────────────────────────

PROTOCOLS: dict = {
    "A": {
        "label":         "Protocol A — Real-time HITL (dt=200ms, rendering ON)",
        "tps":           5,
        "show_viewport": True,
        "budget_ms":     BUDGET_200_MS,
        "sim_time_s":    300,
        "agent_counts":  [],
    },
    "B": {
        "label":         "Protocol B — Autonomous control (dt=30ms, rendering ON)",
        "tps":           33,
        "show_viewport": True,
        "budget_ms":     BUDGET_30_MS,
        "sim_time_s":    300,
        "agent_counts":  [],
    },
    "D": {
        "label":         "Protocol D — Headless AI training (dt=30ms, rendering OFF)",
        "tps":           33,
        "show_viewport": False,
        "budget_ms":     BUDGET_30_MS,
        "sim_time_s":    300,
        "agent_counts":  [],
    },
}


def load_agent_counts(path: str = "agent_counts.json") -> None:
    """
    Load per-protocol agent sweep lists from a JSON file.

    Expected format:
        {
            "A": [5, 50, 100, 200, ...],
            "B": [5, 10, 20, 30, ...],
            "D": [5, 50, 100, 200, ...]
        }
    Unknown keys are silently ignored.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Agent counts config not found: '{path}'\n"
            f"Create agent_counts.json alongside this script."
        )
    with open(path) as f:
        counts = json.load(f)
    for key, value in counts.items():
        if key in PROTOCOLS:
            PROTOCOLS[key]["agent_counts"] = value


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BenchmarkConfig:
    """Runtime parameters for a full benchmark run (spawn geometry, currents, paths, protocols)."""
    # Agent spawn geometry
    rov_x:   float = 10.0
    rov_z:   float = -2.0
    spacing: float =  4.0

    # Vortex current field parameters
    vortex_strength: float = 5.0
    vortex_z_amp:    float = 0.2
    vortex_z_freq:   float = 0.1

    # Warm-up and statistics
    warmup_s:    int = 10
    slice_index: int = 400   # ticks to discard before computing summary stats

    # Output paths
    data_dir:    str = "data/holoocean"
    results_dir: str = "results"

    # Protocols to run (order is preserved)
    run_protocols: list = field(default_factory=lambda: ["A", "B", "D"])


# ─────────────────────────────────────────────────────────────────────────────
# Physics helpers
# ─────────────────────────────────────────────────────────────────────────────

def vortex_field(loc: list, cfg: BenchmarkConfig) -> list:
    """Return vortex current vector [dx, dy, dz] at position loc."""
    x, y, z = loc
    if z > 0:
        return [0.0, 0.0, 0.0]
    r_sq = x**2 + y**2 + 1e-5
    dx   = -y / r_sq * cfg.vortex_strength
    dy   =  x / r_sq * cfg.vortex_strength
    dz   =  cfg.vortex_z_amp * np.cos(cfg.vortex_z_freq * r_sq)
    return [3.0 * dx, 3.0 * dy, 3.0 * dz]


def extract_position(pose: np.ndarray) -> list:
    return [float(pose[0, 3]), float(pose[1, 3]), float(pose[2, 3])]


def get_gpu_usage() -> float:
    try:
        gpus = GPUtil.getGPUs()
        return gpus[0].load * 100.0 if gpus else 0.0
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Scenario builder
# ─────────────────────────────────────────────────────────────────────────────

def spawn_location(idx: int, total: int, cfg: BenchmarkConfig) -> list:
    """Return [x, y, z] for agent idx, centred on the X-axis with equal spacing."""
    y = (idx - (total - 1) / 2.0) * cfg.spacing
    return [cfg.rov_x, y, cfg.rov_z]


def build_scenario(count: int, proto_key: str, cfg: BenchmarkConfig) -> dict:
    """Build the HoloOcean scenario dict for `count` BlueROV2 agents under protocol `proto_key`."""
    p = PROTOCOLS[proto_key]
    return {
        "name":           f"benchmark_{proto_key}_{count}agents",
        "package_name":   "Ocean",
        "world":          "SimpleUnderwater",
        "ticks_per_sec":  p["tps"],
        "frames_per_sec": False,
        "current":        {"vehicle_debugging": True},
        "agents": [
            {
                "agent_name":     f"auv{i}",
                "agent_type":     "BlueROV2",
                "sensors":        [{"sensor_type": "PoseSensor"}],
                "control_scheme": 0,
                "location":       spawn_location(i, count, cfg),
                "rotation":       [0, 0, 0],
            }
            for i in range(count)
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────────────

def metric_stats(arr: np.ndarray, name: str) -> dict:
    if len(arr) == 0:
        return {k: 0 for k in
                ["Metric", "Mean", "Median", "Standard Deviation",
                 "Variance", "Min", "Max", "Skewness", "Kurtosis"]} | {"Metric": name}
    return {
        "Metric":             name,
        "Mean":               round(float(np.mean(arr)),   4),
        "Median":             round(float(np.median(arr)), 4),
        "Standard Deviation": round(float(np.std(arr)),    4),
        "Variance":           round(float(np.var(arr)),    4),
        "Min":                round(float(np.min(arr)),    4),
        "Max":                round(float(np.max(arr)),    4),
        "Skewness":           round(float(skew(arr)),      4),
        "Kurtosis":           round(float(kurtosis(arr)),  4),
    }


def build_summary(
    release_latency_list: list,
    current_ms_list: list,
    step_ms_list: list,
    full_frame_ms_list: list,
    post_release_ms_list: list,
    cpu_list: list,
    gpu_list: list,
    rtf: float,
    tick_rate_hz: float,
    render_fps_est: float,
    slice_index: int,
) -> list[dict]:
    """
    Compute per-metric statistics from raw measurement lists, discarding the first
    `slice_index` samples (warmup). Returns one stats dict per metric, ready for CSV.
    """
    def clean(arr):
        a = np.array(arr[slice_index:], dtype=float)
        return a[~np.isnan(a)]

    rl  = clean(release_latency_list)
    ci  = clean(current_ms_list)
    st  = clean(step_ms_list)
    ff  = clean(full_frame_ms_list)
    pr  = clean(post_release_ms_list)
    cpu = clean(cpu_list)
    gpu = clean(gpu_list)
    n   = max(len(rl), 1)

    return [
        metric_stats(rl,                      "release_latency_ms  [MEASURED]   sem_wait duration"),
        metric_stats(ci,                      "current_inject_ms   [MEASURED]   set_ocean_currents() wall time"),
        metric_stats(st,                      "step_ms             [MEASURED]   release_latency + current_injection"),
        metric_stats(ff,                      "full_frame_ms       [CALCULATED] time between Release() calls"),
        metric_stats(pr,                      "post_release_ms     [CALCULATED] full_frame - release_latency"),
        metric_stats(np.full(n, rtf),         "RTF                 [CALCULATED] (ticks*dt_s)/total_compute_s"),
        metric_stats(np.full(n, tick_rate_hz),"tick_rate_hz        [CALCULATED] ticks/wall_elapsed"),
        metric_stats(np.full(n, render_fps_est) if not math.isnan(render_fps_est)
                     else np.array([]),       "render_fps_est      [CALCULATED] 1000/full_frame_ms lower bound"),
        metric_stats(cpu,                     "cpu_pct             [MEASURED]"),
        metric_stats(gpu,                     "gpu_pct             [MEASURED]"),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# CSV column definitions
# ─────────────────────────────────────────────────────────────────────────────

RAW_COLS = [
    "Timestep",
    "release_latency_ms",
    "current_injection_ms",
    "step_ms",
    "full_frame_ms",
    "post_release_work_ms",
    "RTF_pct",
    "CPU Usage (%)",
    "GPU Usage (%)",
]

SUMMARY_COLS = [
    "Metric", "Mean", "Median", "Standard Deviation",
    "Variance", "Min", "Max", "Skewness", "Kurtosis",
]

MASTER_COLS = [
    "protocol", "n", "tps", "dt_ms", "rendering",
    "mean_release_latency_ms", "std_release_latency_ms", "max_release_latency_ms",
    "wall_elapsed_s", "ticks_done",
    "mean_cpu_pct", "mean_gpu_pct",
    "full_frame_ms", "post_release_work_ms",
    "RTF", "tick_rate_hz", "render_fps_estimate", "sim_time_s",
    "rtf_above_1", "tick_rate_above_140hz",
    "full_frame_below_30ms", "full_frame_below_200ms",
]


def append_master_row(path: str, row: dict) -> None:
    write_header = not os.path.isfile(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MASTER_COLS)
        if write_header:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in MASTER_COLS})
    # Re-sort by protocol then agent count
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: (r["protocol"].strip(), int(r["n"])))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MASTER_COLS)
        w.writeheader()
        w.writerows(rows)


def write_summary(path: str, stats_rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_COLS)
        w.writeheader()
        w.writerows(stats_rows)


# ─────────────────────────────────────────────────────────────────────────────
# Core tick step
# ─────────────────────────────────────────────────────────────────────────────

def do_step(
    env,
    agent_names: list,
    last_state: dict,
    cfg: BenchmarkConfig,
    dt_s: float,
    prev_release_wall: float,
) -> tuple[dict, dict, float]:
    """
    Inject ocean currents then call env.tick().
    Returns (new_state, metrics_dict, wall_time_of_tick_return).
    """
    t_curr_start = time.perf_counter()
    for name in agent_names:
        if name not in last_state:
                continue
        pos = extract_position(last_state[name]["PoseSensor"])
        env.set_ocean_currents(name, vortex_field(pos, cfg))
    t_curr_end = time.perf_counter()

    t0    = time.perf_counter()
    raw = env.tick()
    t1    = time.perf_counter()

    # Normalize flat single-agent state to nested format
    non_meta = [k for k in raw.keys() if k != "t"]
    if non_meta and not isinstance(raw[non_meta[0]], dict):
        state = {"auv0": {k: v for k, v in raw.items() if k != "t"}}
    else:
        state = raw


    release_latency_ms = (t1 - t0)                   * 1000.0
    current_ms         = (t_curr_end - t_curr_start) * 1000.0
    step_ms            = release_latency_ms + current_ms
    full_frame_ms      = (
        (t1 - prev_release_wall) * 1000.0 if prev_release_wall > 0
        else release_latency_ms
    )
    post_release_ms = full_frame_ms - release_latency_ms
    rtf_pct         = (
        (dt_s / (full_frame_ms / 1000.0)) * 100.0 if full_frame_ms > 0
        else 100.0
    )

    return state, {
        "release_latency_ms": release_latency_ms,
        "current_ms":         current_ms,
        "step_ms":            step_ms,
        "full_frame_ms":      full_frame_ms,
        "post_release_ms":    post_release_ms,
        "rtf_pct":            rtf_pct,
        "cpu":                psutil.cpu_percent(interval=None),
        "gpu":                get_gpu_usage(),
        "wall_t":             t1,
    }, t1


# ─────────────────────────────────────────────────────────────────────────────
# Single benchmark episode
# ─────────────────────────────────────────────────────────────────────────────

def run_episode(
    count: int,
    proto_key: str,
    cfg: BenchmarkConfig,
    run_dir: str,
) -> dict | None:
    _cleanup_shm()

    shm = os.statvfs("/dev/shm")
    shm_free_gb = (shm.f_bavail * shm.f_frsize) / 1e9
    print(f"  [shm] free: {shm_free_gb:.2f}GB")
    if shm_free_gb < 2.0:
        print(f"  [!] Not enough /dev/shm space — skipping n={count}")
        return None

    p          = PROTOCOLS[proto_key]
    tps        = p["tps"]
    dt_s       = 1.0 / tps
    sim_time_s = p["sim_time_s"]
    show_vp    = p["show_viewport"]
    budget_ms  = p["budget_ms"]
    ticks_total  = tps * sim_time_s
    warmup_ticks = cfg.warmup_s * tps

    scenario    = build_scenario(count, proto_key, cfg)

    payload = json.dumps(scenario)
    print(f"Scenario JSON size: {len(payload.encode()):,} bytes  ({len(payload.encode())/1048576:.2f} MB)")

    agent_names = [f"auv{i}" for i in range(count)]

    os.makedirs(run_dir, exist_ok=True)
    raw_path = os.path.join(run_dir, "simulation_1_raw_metrics.csv")

    release_latency_list: list[float] = []
    current_ms_list:      list[float] = []
    step_ms_list:         list[float] = []
    full_frame_ms_list:   list[float] = []
    post_release_ms_list: list[float] = []
    cpu_list:             list[float] = []
    gpu_list:             list[float] = []

    try:
        with holoocean.make(scenario_cfg=scenario, show_viewport=show_vp, frames_per_sec=0) as env:

            # ── Rendering setup ───────────────────────────────────────────
            if not show_vp:
                env.should_render_viewport(False)
                env.set_render_quality(0)
            
            env.set_fps(0)  # Uncapped FPS

            # ── Warm-up ───────────────────────────────────────────────────
            print(f"    warm-up ({cfg.warmup_s}s / {warmup_ticks} ticks)…",
                  end="", flush=True)
            state = env.tick()
            prev_release_wall = time.perf_counter()

            non_meta_keys = [k for k in state.keys() if k != "t"]
            if len(non_meta_keys) > 0 and isinstance(state[non_meta_keys[0]], dict):
                # Multi-agent: {"auv0": {"PoseSensor": ...}, "auv1": {...}, "t": ...}
                agent_names = non_meta_keys
            else:
                # Single-agent flat: {"PoseSensor": ..., "t": ...}
                # Wrap it so the rest of the code works uniformly
                agent_names = ["auv0"]
                state = {"auv0": {k: v for k, v in state.items() if k != "t"}}

            for _ in range(warmup_ticks - 1):
                state, _, prev_release_wall = do_step(
                    env, agent_names, state, cfg, dt_s, prev_release_wall)
            print(" done.")

            # ── Measurement loop ──────────────────────────────────────────
            with open(raw_path, "w", newline="") as raw_f:
                raw_w = csv.DictWriter(raw_f, fieldnames=RAW_COLS)
                raw_w.writeheader()

                wall_start   = time.perf_counter()
                last_report  = wall_start
                report_every = sim_time_s / 5

                for step in range(ticks_total):
                    state, m, prev_release_wall = do_step(
                        env, agent_names, state, cfg, dt_s, prev_release_wall)

                    raw_w.writerow({
                        "Timestep":             step,
                        "release_latency_ms":   round(m["release_latency_ms"], 4),
                        "current_injection_ms": round(m["current_ms"],         4),
                        "step_ms":              round(m["step_ms"],             4),
                        "full_frame_ms":        round(m["full_frame_ms"],       4),
                        "post_release_work_ms": round(m["post_release_ms"],     4),
                        "RTF_pct":              round(m["rtf_pct"],             4),
                        "CPU Usage (%)":        round(m["cpu"],                 2),
                        "GPU Usage (%)":        round(m["gpu"],                 2),
                    })
                    raw_f.flush()

                    release_latency_list.append(m["release_latency_ms"])
                    current_ms_list.append(m["current_ms"])
                    step_ms_list.append(m["step_ms"])
                    full_frame_ms_list.append(m["full_frame_ms"])
                    post_release_ms_list.append(m["post_release_ms"])
                    cpu_list.append(m["cpu"])
                    gpu_list.append(m["gpu"])

                    if m["wall_t"] - last_report >= report_every:
                        elapsed = m["wall_t"] - wall_start
                        pct     = 100.0 * (step + 1) / ticks_total
                        print(f"    {pct:3.0f}%  "
                              f"release_lat={m['release_latency_ms']:.1f}ms  "
                              f"full_frame={m['full_frame_ms']:.1f}ms  "
                              f"RTF={m['rtf_pct']/100:.2f}x  "
                              f"elapsed={elapsed:.1f}s",
                              flush=True)
                        last_report = m["wall_t"]

                    # Early stop for protocols with a frame-time budget
                    # if budget_ms is not None and m["full_frame_ms"] >= budget_ms:
                    #     print(f"\n  [!] full_frame_ms ({m['full_frame_ms']:.2f}ms) >= "
                    #           f"budget ({budget_ms:.0f}ms) — stopping early.")
                    #     break

                wall_elapsed = time.perf_counter() - wall_start
                ticks_done   = len(release_latency_list)

        # ── Episode-level metrics ─────────────────────────────────────────
        mean_rl = float(np.mean(release_latency_list))
        std_rl  = float(np.std(release_latency_list))
        max_rl  = float(np.max(release_latency_list))

        full_frame_ms   = (wall_elapsed * 1000.0 / ticks_done
                           if ticks_done > 0 else float("nan"))
        post_release_ms = full_frame_ms - mean_rl

        total_compute_s = sum(full_frame_ms_list) / 1000.0
        rtf = ((ticks_done * dt_s) / total_compute_s
               if total_compute_s > 0 else float("nan"))

        tick_rate_hz = (ticks_done / wall_elapsed
                        if wall_elapsed > 0 else float("nan"))

        render_fps_est = (
            1000.0 / full_frame_ms
            if show_vp and full_frame_ms > 0 and not math.isnan(full_frame_ms)
            else float("nan")
        )

        if wall_elapsed > sim_time_s * 1.5:
            print(f"\n  [!] WARNING: wall_elapsed={wall_elapsed:.0f}s >> "
                  f"sim_time_s={sim_time_s}s — possible unexpected throttle.")

        summary_rows = build_summary(
            release_latency_list, current_ms_list, step_ms_list,
            full_frame_ms_list, post_release_ms_list,
            cpu_list, gpu_list,
            rtf, tick_rate_hz, render_fps_est, cfg.slice_index)
        write_summary(os.path.join(run_dir, "simulation_1_summary.csv"), summary_rows)

        result = {
            "mean_release_latency_ms": mean_rl,
            "std_release_latency_ms":  std_rl,
            "max_release_latency_ms":  max_rl,
            "wall_elapsed_s":          wall_elapsed,
            "ticks_done":              ticks_done,
            "mean_cpu_pct":            float(np.mean(cpu_list)),
            "mean_gpu_pct":            float(np.mean(gpu_list)),
            "full_frame_ms":           full_frame_ms,
            "post_release_work_ms":    post_release_ms,
            "RTF":                     rtf,
            "tick_rate_hz":            tick_rate_hz,
            "render_fps_estimate":     render_fps_est,
            "sim_time_s":              sim_time_s,
            "rtf_above_1":             rtf >= 1.0,
            "tick_rate_above_140hz":   tick_rate_hz >= 140.0,
            "full_frame_below_30ms":   full_frame_ms < BUDGET_30_MS,
            "full_frame_below_200ms":  full_frame_ms < BUDGET_200_MS,
        }

        gc.collect()
        time.sleep(2.0)
        return result

    except Exception as exc:
        print(f"\n  [!] Exception at n={count}: {exc}")
        _cleanup_shm()
        gc.collect()
        time.sleep(2.0)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Console output
# ─────────────────────────────────────────────────────────────────────────────

_HDR = ("  {:<7} {:<18} {:<16} {:<18} {:<10} {:<12} {:<16} {:<8} {:<8} {}"
        .format("Agents", "release_lat(ms)", "full_frame(ms)",
                "post_release(ms)", "RTF(x)", "tick_hz",
                "render_fps_est", "CPU%", "GPU%", "Flags"))
_SEP = "  " + "─" * 128


def _print_proto_header(proto_key: str) -> None:
    p      = PROTOCOLS[proto_key]
    tps    = p["tps"]
    mode   = "rendering ON" if p["show_viewport"] else "HEADLESS"
    bud    = f"{p['budget_ms']:.0f}ms" if p["budget_ms"] is not None else "none"
    print()
    print("  " + "=" * 128)
    print(f"  {p['label']}")
    print(f"  dt={1000.0/tps:.1f}ms  tps={tps}  {mode}  "
          f"fixed-tick  T={p['sim_time_s']}s  budget={bud}")
    print("  " + "=" * 128)
    print()
    print(_HDR)
    print(_SEP)


def _print_run_row(count: int, r: dict) -> None:
    flags = []
    if not r["rtf_above_1"]:           flags.append("RTF<1")
    if not r["tick_rate_above_140hz"]: flags.append("tick_hz<140")
    if not r["full_frame_below_30ms"]: flags.append("frame>30ms")
    if not r["full_frame_below_200ms"]:flags.append("frame>200ms")

    rfe     = r["render_fps_estimate"]
    rfe_str = f"{rfe:.1f}" if not math.isnan(rfe) else "N/A"

    print("  {:<7} {:<18.3f} {:<16.3f} {:<18.3f} {:<10.3f} {:<12.1f} "
          "{:<16} {:<8.1f} {:<8.1f}{}"
          .format(count,
                  r["mean_release_latency_ms"], r["full_frame_ms"],
                  r["post_release_work_ms"], r["RTF"], r["tick_rate_hz"],
                  rfe_str, r["mean_cpu_pct"], r["mean_gpu_pct"],
                  "  " + " | ".join(flags) if flags else ""))


# ─────────────────────────────────────────────────────────────────────────────
# Resume helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_completed(master_csv: str) -> set[tuple[str, int]]:
    """Return the set of (protocol, n_agents) pairs already recorded in `master_csv`."""
    if not os.path.isfile(master_csv):
        return set()
    done: set[tuple[str, int]] = set()
    with open(master_csv, newline="") as f:
        for row in csv.DictReader(f):
            try:
                done.add((row["protocol"].strip(), int(row["n"])))
            except (KeyError, ValueError):
                pass
    return done


def clear_episode(run_dir: str, master_csv: str,
                  proto_key: str, count: int) -> None:
    """Delete per-run CSVs and remove the (proto_key, count) row from master_csv."""
    for fname in ("simulation_1_raw_metrics.csv", "simulation_1_summary.csv"):
        path = os.path.join(run_dir, fname)
        if os.path.isfile(path):
            os.remove(path)
    if not os.path.isfile(master_csv):
        return
    with open(master_csv, newline="") as f:
        rows = [r for r in csv.DictReader(f)
                if not (r["protocol"].strip() == proto_key
                        and int(r["n"]) == count)]
    with open(master_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MASTER_COLS)
        w.writeheader()
        w.writerows(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Protocol runner
# ─────────────────────────────────────────────────────────────────────────────

def run_protocol(
    proto_key: str,
    cfg: BenchmarkConfig,
    master_csv: str,
    completed: set[tuple[str, int]],
) -> None:
    p = PROTOCOLS[proto_key]

    if not p["agent_counts"]:
        print(f"\n  [!] Protocol {proto_key}: no agent counts defined — skipping.")
        return

    _print_proto_header(proto_key)

    for count in p["agent_counts"]:
        run_dir = os.path.join(cfg.data_dir, f"protocol_{proto_key}", str(count))

        if (proto_key, count) in completed:
            print(f"\n  [Protocol {proto_key}  n={count}]  already done — rewriting.")
            clear_episode(run_dir, master_csv, proto_key, count)
            completed.discard((proto_key, count))

        print(f"\n  [Protocol {proto_key}  n={count}]")
        result = run_episode(count, proto_key, cfg, run_dir)
        _cleanup_shm()
        _kill_holodeck()

        if result is None:
            print(f"  [!] Episode failed for n={count}, skipping.")
            continue

        rfe = result["render_fps_estimate"]
        append_master_row(master_csv, {
            "protocol":                proto_key,
            "n":                       count,
            "tps":                     p["tps"],
            "dt_ms":                   round(1000.0 / p["tps"], 4),
            "rendering":               p["show_viewport"],
            "mean_release_latency_ms": round(result["mean_release_latency_ms"], 4),
            "std_release_latency_ms":  round(result["std_release_latency_ms"],  4),
            "max_release_latency_ms":  round(result["max_release_latency_ms"],  4),
            "wall_elapsed_s":          round(result["wall_elapsed_s"],           2),
            "ticks_done":              result["ticks_done"],
            "mean_cpu_pct":            round(result["mean_cpu_pct"],             2),
            "mean_gpu_pct":            round(result["mean_gpu_pct"],             2),
            "full_frame_ms":           round(result["full_frame_ms"],            4),
            "post_release_work_ms":    round(result["post_release_work_ms"],     4),
            "RTF":                     round(result["RTF"],                      4),
            "tick_rate_hz":            round(result["tick_rate_hz"],             4),
            "render_fps_estimate":     round(rfe, 2) if not math.isnan(rfe) else "",
            "sim_time_s":              result["sim_time_s"],
            "rtf_above_1":             result["rtf_above_1"],
            "tick_rate_above_140hz":   result["tick_rate_above_140hz"],
            "full_frame_below_30ms":   result["full_frame_below_30ms"],
            "full_frame_below_200ms":  result["full_frame_below_200ms"],
        })
        completed.add((proto_key, count))
        _print_run_row(count, result)

        # Budget check: stop sweeping agents if ceiling is reached
        if p["budget_ms"] is not None and result["full_frame_ms"] >= p["budget_ms"]:
            print(f"\n  [!] Ceiling reached at n={count} "
                f"(full_frame_ms={result['full_frame_ms']:.2f}ms >= "
                f"budget={p['budget_ms']:.0f}ms) — stopping Protocol {proto_key}.")
            break


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    _raise_fd_limit()
    _cleanup_shm()

    parser = argparse.ArgumentParser(description="HoloOcean BlueROV2 benchmark")
    parser.add_argument("--config", default="agent_counts.json", metavar="PATH",
                        help="JSON file with per-protocol agent sweep lists")
    args = parser.parse_args()

    load_agent_counts(args.config)

    cfg = BenchmarkConfig()
    os.makedirs(cfg.results_dir, exist_ok=True)
    master_csv = os.path.join(cfg.results_dir, "benchmark_all_protocols.csv")

    completed = load_completed(master_csv)
    if completed:
        print(f"\n  {len(completed)} existing episode(s) found — will rewrite if in sweep:")
        for pk, n in sorted(completed):
            print(f"       Protocol {pk}  n={n}")
    else:
        print("\n  No existing results — starting fresh.")

    print(f"\n  HoloOcean BlueROV2 — Three-Protocol Benchmark")
    print(f"  Master CSV: {master_csv}\n")
    print(f"  {'Protocol':<10} {'dt':>8}  {'Rendering':<12} {'Budget':>10}  "
          f"{'Sim(s)':>7}  Agents")
    print(f"  {'─' * 70}")
    for key in cfg.run_protocols:
        if key not in PROTOCOLS:
            print(f"  [!] Unknown protocol '{key}' in run_protocols — skipping.")
            continue
        p   = PROTOCOLS[key]
        rdr = "ON" if p["show_viewport"] else "OFF"
        bud = f"{p['budget_ms']:.0f}ms" if p["budget_ms"] is not None else "none"
        print(f"  {key:<10} {1000/p['tps']:>7.1f}ms  {rdr:<12} {bud:>10}  "
              f"{p['sim_time_s']:>7}s  {p['agent_counts']}")
    print()

    for proto_key in cfg.run_protocols:
        if proto_key not in PROTOCOLS:
            continue
        run_protocol(proto_key, cfg, master_csv, completed)

    print(f"\n  Done.  Master CSV : {master_csv}")
    print(f"  Per-tick data     : {cfg.data_dir}/protocol_<X>/<n>/simulation_1_raw_metrics.csv")
    print(f"  Episode summaries : {cfg.data_dir}/protocol_<X>/<n>/simulation_1_summary.csv")


if __name__ == "__main__":
    main()