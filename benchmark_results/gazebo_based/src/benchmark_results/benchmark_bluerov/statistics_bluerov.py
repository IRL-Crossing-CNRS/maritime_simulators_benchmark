#
# Copyright (c) 2025 IRL Crossing
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0
#
"""
@file statistics_bluerov.py
@author IRL Crossing

@brief BlueROV Simulation Statistics and Plotting for LOTUSim

@note Processes simulation metrics from BlueROV experiments conducted in LOTUSim.
Computes statistical summaries for update times, CPU/GPU usage, real-time factor,
and generates a comparative update plot across different simulation configurations.

@details
Inputs:
    - Raw simulation CSV files inside agent subfolders
    - Expected folder structure: data/lotusim/<config_name>/<num_agents>/simulation_1_raw_metrics.csv
      where each <config_name> represents a different simulation configuration.

Outputs:
    - results/bluerov_lotusim_configs_average_update.csv (combined summary table across configurations)
    - results/bluerov_lotusim_configs_update_plot.eps   (comparative plot of update times)

Note:
    - This script processes only LOTUSim data.

@version 0.1
@date 2025-10-22
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import skew, kurtosis

# ==========================
# Global Configuration
# ==========================
DATA_DIR = "data/lotusim"  # Base folder containing LOTUSim simulation data
RESULTS_DIR = "results"  # Folder to save CSVs and plots
RAW_FILENAME = "simulation_1_raw_metrics.csv"

SLICE_INDEX = 400  # Skip warm-up samples
MIN_AGENTS = 0  # Minimum number of agents to process
MAX_AGENTS = 500  # Maximum number of agents to process
PERCEPTION_LIMIT_MS = 200  # User perception update limit
PHYSICS_TIMESTEP_MS = 30  # Physics timestep

VERTICAL_LINES = [(30, PHYSICS_TIMESTEP_MS, "30", "teal"), (450, PERCEPTION_LIMIT_MS, "450", "red")]

PLOT_COLORS = ["blue", "#7ED957", "orange", "purple", "pink", "black"]  # Plot line colors
ANNOTATION_FONTSIZE = 12
LABEL_FONTSIZE = 14
LEGEND_FONTSIZE = 12

# ==========================
# Utility Functions
# ==========================


def safe_numeric(arr):
    """Convert list to numeric values, discarding invalid entries."""
    numeric_arr = pd.to_numeric(arr, errors="coerce")
    return numeric_arr[~np.isnan(numeric_arr)]


def metric_evaluation(metrics, name):
    """Return descriptive statistics for a dataset."""
    return {
        "Metric": name,
        "Mean": round(np.mean(metrics), 4),
        "Median": round(np.median(metrics), 4),
        "Standard Deviation": round(np.std(metrics), 4),
        "Variance": round(np.var(metrics), 4),
        "Min": round(np.min(metrics), 4),
        "Max": round(np.max(metrics), 4),
        "Skewness": round(skew(metrics), 4),
        "Kurtosis": round(kurtosis(metrics), 4),
    }


# ==========================
# Statistical Table Generation
# ==========================


def generate_statistical_tables(prep, pre, update, post, exec_time, rtf, cpu, gpu, slice_index=SLICE_INDEX):
    """
    Slice metrics (to skip warm-up), clean numeric values, and compute
    statistical summaries for execution times, RTF, CPU, and GPU.
    Returns four DataFrames.
    """
    if len(update) <= slice_index:
        raise ValueError(f"Not enough samples to slice from index {slice_index}")

    prep, pre, update, post = prep[slice_index:], pre[slice_index:], update[slice_index:], post[slice_index:]
    exec_time, rtf, cpu, gpu = exec_time[slice_index:], rtf[slice_index:], cpu[slice_index:], gpu[slice_index:]

    prep, pre, update, post = map(safe_numeric, [prep, pre, update, post])
    exec_time, rtf, cpu, gpu = map(safe_numeric, [exec_time, rtf, cpu, gpu])

    execution_time_table = pd.DataFrame(
        [
            metric_evaluation(prep, "Preparation Update (ms)"),
            metric_evaluation(pre, "Pre-Update (ms)"),
            metric_evaluation(update, "Update (ms)"),
            metric_evaluation(post, "Post-Update (ms)"),
            metric_evaluation(exec_time, "Execution time (ms)"),
        ]
    ).round(2)

    rtf_table = pd.DataFrame([metric_evaluation(rtf, "Real Time Factor (%)")]).round(2)
    cpu_table = pd.DataFrame([metric_evaluation(cpu, "CPU usage (%)")]).round(2)
    gpu_table = pd.DataFrame([metric_evaluation(gpu, "GPU usage (%)")]).round(2)

    return execution_time_table, rtf_table, cpu_table, gpu_table


# ==========================
# Data Loading & Processing
# ==========================


def process_folder(
    base_folder, raw_filename=RAW_FILENAME, min_agents=MIN_AGENTS, max_agents=MAX_AGENTS, excluded_folders=None
):
    """Process agent subfolders and return DataFrame of mean Update (ms)."""
    if excluded_folders is None:
        excluded_folders = []

    rows = []
    subfolders = sorted(os.listdir(base_folder), key=lambda x: int(x) if x.isdigit() else float("inf"))

    for folder in subfolders:
        if not folder.isdigit():
            continue
        num_agents = int(folder)
        if num_agents < min_agents or num_agents > max_agents or num_agents in excluded_folders:
            continue

        raw_path = os.path.join(base_folder, folder, raw_filename)
        if not os.path.isfile(raw_path):
            continue

        print(f"📊 Processing: {raw_path}")
        try:
            df = pd.read_csv(raw_path)
            df.columns = df.columns.str.strip()

            prep = df["Preparation Update (ms)"].tolist()
            pre = df["Pre-Update (ms)"].tolist()
            update = df["Update (ms)"].tolist()
            post = df["Post-Update (ms)"].tolist()
            exec_time = df["Execution Time (ms)"].tolist()
            rtf = df["Real Time Factor (%)"].tolist()
            cpu = df["CPU Usage (%)"].tolist()
            gpu = df["GPU Usage (%)"].tolist()

            exec_table, *_ = generate_statistical_tables(prep, pre, update, post, exec_time, rtf, cpu, gpu)

            update_row = exec_table[exec_table["Metric"] == "Update (ms)"]
            if not update_row.empty:
                rows.append({"n_agents": num_agents, "mean_update_ms": update_row["Mean"].values[0]})

        except Exception as e:
            print(f"⚠️ Failed to process {raw_path}: {e}")

    if not rows:
        return pd.DataFrame()

    df_base = pd.DataFrame(rows).sort_values("n_agents").set_index("n_agents")
    cutoff_index = df_base[df_base["mean_update_ms"] > PERCEPTION_LIMIT_MS].index.min()
    if cutoff_index:
        df_base = df_base[df_base.index <= cutoff_index]

    return df_base


# ==========================
# Plotting Function
# ==========================


def plot_update_curves(df_dict, output_filename):
    plt.figure(figsize=(12, 6))

    for idx, (config_name, df) in enumerate(df_dict.items()):
        subset = df["mean_update_ms"].dropna()
        plt.plot(
            subset.index,
            subset.values,
            marker="o",
            linestyle="-",
            color=PLOT_COLORS[idx % len(PLOT_COLORS)],
            label=config_name,
        )

    # Reference lines
    plt.axhline(
        y=PERCEPTION_LIMIT_MS,
        color="red",
        linestyle=":",
        linewidth=1.5,
        label=f"User perception limit ({PERCEPTION_LIMIT_MS} ms)",
    )
    plt.axhline(
        y=PHYSICS_TIMESTEP_MS,
        color="teal",
        linestyle=":",
        linewidth=1.5,
        label=f"Physics timestep ({PHYSICS_TIMESTEP_MS} ms)",
    )

    # Vertical lines and annotations
    for x, y_max, label, color in VERTICAL_LINES:
        plt.axvline(x=x, color=color, linestyle=":", linewidth=1.5)
        plt.text(x, -5, f"LOTUSim: {label} BlueROV", ha="center", va="top", color=color, fontsize=ANNOTATION_FONTSIZE)

    plt.xlabel("nb_agents", fontsize=LABEL_FONTSIZE)
    plt.ylabel("Update (ms)", fontsize=LABEL_FONTSIZE)
    plt.xlim(0, MAX_AGENTS)
    plt.ylim(bottom=0)
    plt.grid(True)
    plt.legend(title="Configuration BlueROV", fontsize=LEGEND_FONTSIZE)
    plt.tight_layout()

    plt.savefig(output_filename, format="eps")
    plt.show()
    print(f"✅ Plot saved to {output_filename}")


# ==========================
# Main Execution
# ==========================


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    if not os.path.isdir(DATA_DIR):
        print(f"❌ Data folder not found: {DATA_DIR}")
        return

    base_folders = [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, f))]

    all_data = {}
    for folder in base_folders:
        config_name = os.path.basename(folder)
        df = process_folder(folder)
        if not df.empty:
            all_data[config_name] = df

    if not all_data:
        print("❌ No LOTUSim data available.")
        return

    combined_df = pd.concat(all_data.values(), axis=1)
    combined_df.columns = all_data.keys()
    csv_path = os.path.join(RESULTS_DIR, "bluerov_lotusim_configs_average_update.csv")
    combined_df.to_csv(csv_path)
    print(f"✅ Combined CSV saved to {csv_path}")

    plot_path = os.path.join(RESULTS_DIR, "bluerov_lotusim_configs_update_plot.eps")
    plot_update_curves(all_data, plot_path)


if __name__ == "__main__":
    main()
