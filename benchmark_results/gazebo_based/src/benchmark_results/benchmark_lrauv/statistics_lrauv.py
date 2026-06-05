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
@file statistics_lrauv.py
@author IRL Crossing

@brief LRAUV Simulation Update Statistics for LOTUSim

@note Processes simulation metrics from LRAUV experiments conducted in LOTUSim.
Computes statistical summaries for update times, CPU/GPU usage, real-time factor,
and generates a comparative update plot across different simulation configurations.

@details
Inputs:
    - Raw simulation CSV files inside agent subfolders
    - Expected folder structure: data/lotusim/<config_name>/<num_agents>/simulation_1_raw_metrics.csv
      where each <config_name> represents a different simulation configuration.

Outputs:
    - results/lrauv__lotusim_configs_average_update.csv
    - results/lrauv_lotusim_configs_update_plot.eps

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
# Configuration
# ==========================
DATA_DIR = "data/lotusim"
RESULTS_DIR = "results"
RAW_FILENAME = "simulation_1_raw_metrics.csv"

SLICE_INDEX = 400  # Skip warm-up samples
MIN_AGENTS = 0
MAX_AGENTS = 800

ANNOTATION_FONTSIZE = 12
LABEL_FONTSIZE = 14
LEGEND_FONTSIZE = 12

CONFIGS = [
    "lrauv_no-gui",
    "lrauv_sensors_no-gui",
    "lrauv_gui",
    "lrauv_sensors_gui",
    "lrauv_sensors_bridge_gui",
    "lrauv_sensors_unity",
]

CONFIG_LABELS = {
    "lrauv_no-gui": "1: No GUI + No Sensors + No ROS2 Sensors + No Unity",
    "lrauv_sensors_no-gui": "2: No GUI + Sensors + No ROS2 Sensors + No Unity",
    "lrauv_gui": "3: GUI + No Sensors + No ROS2 Sensors + No Unity",
    "lrauv_sensors_gui": "4: GUI + Sensors + No ROS2 Sensors + No Unity",
    "lrauv_sensors_bridge_gui": "5: GUI + Sensors + ROS2 Sensors + No Unity",
    "lrauv_sensors_unity": "6: No GUI + Sensors + ROS2 Sensors + Unity",
}

os.makedirs(RESULTS_DIR, exist_ok=True)

# ==========================
# Utility Functions
# ==========================


def safe_numeric(arr):
    """Convert a list to numeric values, discarding invalid entries."""
    numeric_arr = pd.to_numeric(arr, errors="coerce")
    return numeric_arr[~np.isnan(numeric_arr)]


def metric_evaluation(metrics, name):
    """Compute descriptive statistics for a numeric dataset."""
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


def generate_statistical_tables(prep, pre, update, post, exec_time, rtf, cpu, gpu, slice_index=SLICE_INDEX):
    """Slice warm-up samples, clean data, and compute statistics for metrics."""
    if len(update) <= slice_index:
        raise ValueError(f"Not enough samples to slice from index {slice_index}")

    prep, pre, update, post = map(
        safe_numeric, [prep[slice_index:], pre[slice_index:], update[slice_index:], post[slice_index:]]
    )
    exec_time, rtf, cpu, gpu = map(
        safe_numeric, [exec_time[slice_index:], rtf[slice_index:], cpu[slice_index:], gpu[slice_index:]]
    )

    exec_table = pd.DataFrame(
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

    return exec_table, rtf_table, cpu_table, gpu_table


# ==========================
# Data Loading Functions
# ==========================


def process_configuration(config_name):
    """
    Process a configuration folder, compute mean Update (ms) per agent,
    and return a DataFrame indexed by agent number.
    """
    base_folder = os.path.join(DATA_DIR, config_name)
    if not os.path.isdir(base_folder):
        return pd.DataFrame()

    rows = []

    for folder in sorted(os.listdir(base_folder), key=lambda x: int(x) if x.isdigit() else float("inf")):
        if not folder.isdigit():
            continue
        num_agents = int(folder)
        if not (MIN_AGENTS <= num_agents <= MAX_AGENTS):
            continue

        raw_path = os.path.join(base_folder, folder, RAW_FILENAME)
        if not os.path.isfile(raw_path):
            continue

        print(f"📊 Processing {raw_path}")
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
                mean_update = update_row["Mean"].values[0]
                # Filter unrealistic mean updates
                if not (mean_update < 20 and num_agents > 300):
                    rows.append({"n_agents": num_agents, config_name: mean_update})

        except Exception as e:
            print(f"⚠️ Failed {raw_path}: {e}")

    if not rows:
        return pd.DataFrame()

    df_config = pd.DataFrame(rows).set_index("n_agents").sort_index()
    # Cutoff if mean update exceeds 200 ms
    cutoff_index = df_config[df_config[config_name] > 200].index.min()
    if cutoff_index:
        df_config = df_config[df_config.index <= cutoff_index]

    return df_config


# ==========================
# Plotting Function
# ==========================


def plot_update_curves(df_dict, output_filename):
    """Plot mean Update (ms) vs number of agents for all configurations."""
    plt.figure(figsize=(12, 6))
    colors = ["blue", "#7ED957", "orange", "purple", "pink", "black"]

    for idx, (config, df) in enumerate(df_dict.items()):
        subset = df[config].dropna()
        plt.plot(
            subset.index,
            subset.values,
            marker="o",
            linestyle="-",
            color=colors[idx % len(colors)],
            label=CONFIG_LABELS.get(config, config),
        )

    # Reference lines
    plt.axhline(y=200, color="red", linestyle=":", linewidth=1.5, label="User perception: update limit (200 ms)")
    plt.axhline(y=30, color="teal", linestyle=":", linewidth=1.5, label="Physics timestep (30 ms)")
    plt.axvline(x=55, color="teal", linestyle=":", linewidth=1.5)
    plt.axvline(x=750, color="red", linestyle=":", linewidth=1.5)

    plt.text(
        45, -10, "LOTUSim: 55 LRAUV\n(physics limit)", ha="center", va="top", color="teal", fontsize=ANNOTATION_FONTSIZE
    )
    plt.text(
        750,
        -10,
        "LOTUSim: 750 LRAUV\n(perception limit)",
        ha="center",
        va="top",
        color="red",
        fontsize=ANNOTATION_FONTSIZE,
    )

    plt.xlabel("nb_agents", fontsize=LABEL_FONTSIZE)
    plt.ylabel("Update (ms)", fontsize=LABEL_FONTSIZE)
    plt.xlim(left=0)
    plt.ylim(bottom=0)
    plt.grid(True)
    plt.legend(title="Configuration LRAUV", fontsize=LEGEND_FONTSIZE)
    plt.tight_layout()

    plt.savefig(output_filename, format="eps")
    plt.show()
    print(f"✅ Plot saved to {output_filename}")


# ==========================
# Main Execution
# ==========================


def main():
    all_data = {}

    for config in CONFIGS:
        df = process_configuration(config)
        if not df.empty:
            all_data[config] = df

    if all_data:
        combined_df = pd.concat(all_data.values(), axis=1)
        combined_df.rename(columns=CONFIG_LABELS, inplace=True)
        combined_csv = os.path.join(RESULTS_DIR, "lrauv_lotusim_configs_average_update.csv")
        combined_df.to_csv(combined_csv)
        print(f"✅ Combined statistics saved to {combined_csv}")

        plot_path = os.path.join(RESULTS_DIR, "lrauv_lotusim_configs_update_plot.eps")
        plot_update_curves(all_data, plot_path)
    else:
        print("❌ No data available.")


if __name__ == "__main__":
    main()
