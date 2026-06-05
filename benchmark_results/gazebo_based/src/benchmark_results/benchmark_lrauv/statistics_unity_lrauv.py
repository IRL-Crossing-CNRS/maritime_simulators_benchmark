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
@file statistics_unity_lrauv.py
@author IRL Crossing

@brief LOTUSim vs LRAUVSim Update Comparison

@note Processes simulation metrics from LOTUSim (LRAUV) and LRAUVSim,
computes mean update times, and plots both on the same graph.

@details
Inputs:
    - LRAUVSim CSV: data/LRAUVSim_results.csv
    - LOTUSim folders: data/lotusim/<config_name>/<num_agents>/simulation_1_raw_metrics.csv

Outputs:
    - results/lrauv_uuvsim_lotusim_update_plot.eps
    - results/lrauv_lotusim_summary.csv

@version 0.1
@date 2025-10-22
"""

import os
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from scipy.stats import skew, kurtosis

matplotlib.rcParams.update({
    "font.family":       "serif",
    "font.serif":        ["Times New Roman", "DejaVu Serif"],
    "font.size":         10,
    "axes.titlesize":    11,
    "axes.labelsize":    10,
    "xtick.labelsize":   9,
    "ytick.labelsize":   9,
    "legend.fontsize":   9,
    "figure.dpi":        150,
    "axes.grid":         True,
    "grid.alpha":        0.3,
    "grid.linestyle":    "--",
    "axes.spines.top":   False,
    "axes.spines.right": False,
})

# ==========================
# Configuration
# ==========================
DATA_DIR = "data"
RESULTS_DIR = "results"
LOTUSIM_DIR = os.path.join(DATA_DIR, "lotusim", "lrauv_sensors_unity")
os.makedirs(RESULTS_DIR, exist_ok=True)

LRAUVSIM_CSV = os.path.join(DATA_DIR, "LRAUVSim_results.csv")
RAW_FILENAME = "simulation_1_raw_metrics.csv"
MIN_AGENTS = 0
MAX_AGENTS = 800
SLICE_INDEX = 400  # skip warm-up samples

# Thresholds
PHYSICS_LIMIT = 30
USER_PERCEPTION_LIMIT = 200

# ==========================
# Utility Functions
# ==========================


def safe_numeric(arr):
    """Convert a list to numeric values, discarding NaNs."""
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


def generate_statistical_table(prep, pre, update, post, exec_time, rtf, cpu, gpu):
    """
    Slice warm-up samples, clean numeric data, and compute statistics.
    Returns execution statistics table.
    """
    if len(update) <= SLICE_INDEX:
        raise ValueError(f"Not enough samples to slice from index {SLICE_INDEX}")

    prep, pre, update, post = map(lambda x: safe_numeric(x[SLICE_INDEX:]), [prep, pre, update, post])
    exec_time, rtf, cpu, gpu = map(lambda x: safe_numeric(x[SLICE_INDEX:]), [exec_time, rtf, cpu, gpu])

    execution_stats = [
        metric_evaluation(prep, "Preparation Update (ms)"),
        metric_evaluation(pre, "Pre-Update (ms)"),
        metric_evaluation(update, "Update (ms)"),
        metric_evaluation(post, "Post-Update (ms)"),
        metric_evaluation(exec_time, "Execution Time (ms)"),
    ]

    return pd.DataFrame(execution_stats).round(2)


# ==========================
# Data Loading Functions
# ==========================


def load_lotusim_data(folder_path):
    """
    Process a LOTUSim folder and compute mean Update (ms) for each agent count.
    Returns a DataFrame with columns ['n_agents', 'mean_update_ms'].
    """
    data = []
    for folder in sorted(os.listdir(folder_path), key=lambda x: int(x) if x.isdigit() else float("inf")):
        if not folder.isdigit():
            continue
        agents = int(folder)
        if agents < MIN_AGENTS or agents > MAX_AGENTS:
            continue

        raw_path = os.path.join(folder_path, folder, RAW_FILENAME)
        if not os.path.isfile(raw_path):
            continue

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

            exec_table = generate_statistical_table(prep, pre, update, post, exec_time, rtf, cpu, gpu)
            update_row = exec_table[exec_table["Metric"] == "Update (ms)"]

            if not update_row.empty:
                mean_update = update_row["Mean"].values[0]
                # Filter unrealistic data for high agent counts
                if not (mean_update < 20 and agents > 300):
                    data.append({"n_agents": agents, "mean_update_ms": mean_update})
        except Exception as e:
            print(f"⚠️ Failed to process {raw_path}: {e}")

    return pd.DataFrame(data).sort_values("n_agents").reset_index(drop=True)


def load_lrauvsim_csv(csv_path):
    """Load LRAUVSim CSV file into a DataFrame."""
    return pd.read_csv(csv_path)


# ==========================
# Function to save LOTUSim summary CSV
# ==========================


def save_lotusim_summary_csv(df_lotus, filename="lrauv_lotusim_summary.csv"):
    """
    Saves LOTUSim mean update times per agent count to a CSV.
    """
    results_path = os.path.join(RESULTS_DIR, filename)
    df_lotus.to_csv(results_path, index=False)
    print(f"✅ LOTUSim summary saved to {results_path}")


# ==========================
# Plotting Function
# ==========================


def plot_update_comparison(df_lrauv, df_lotus):
    """
    Plot LRAUVSim vs LOTUSim mean update times.
    Adds physics and user perception threshold lines.
    """
    fig, ax = plt.subplots(figsize=(5.5, 3.8))

    ax.plot(df_lrauv["n_agents"], df_lrauv["mean_update_ms"],
            marker="o", markersize=4, linestyle="-", linewidth=1.5, color="orange", label="LRAUVSim — LRAUV")
    ax.plot(df_lotus["n_agents"], df_lotus["mean_update_ms"],
            marker="o", markersize=4, linestyle="-", linewidth=1.5, color="teal", label="LOTUSim — LRAUV")

    LRAUV_STEP = 120  # LRAUVSim fixed physics timestep (ms)

    # Horizontal thresholds
    ax.axhline(PHYSICS_LIMIT, color="purple", linestyle="--", linewidth=1.2)
    ax.annotate("Physics\nlimit", xy=(0, PHYSICS_LIMIT),
                xycoords=ax.get_yaxis_transform(), xytext=(-38, 0),
                textcoords="offset points", ha="right", va="center",
                fontsize=8.5, color="purple")

    ax.axhline(USER_PERCEPTION_LIMIT, color="red", linestyle="--", linewidth=1.2)
    ax.annotate("User\nperception\nlimit", xy=(0, USER_PERCEPTION_LIMIT),
                xycoords=ax.get_yaxis_transform(), xytext=(-38, 0),
                textcoords="offset points", ha="right", va="center",
                fontsize=8.5, color="red")

    # LRAUVSim fixed step horizontal line at 120 ms
    ax.axhline(LRAUV_STEP, color="orange", linestyle="--", linewidth=1.0, alpha=0.6)
    ax.annotate("LRAUVSim\nfixed step", xy=(0, LRAUV_STEP),
                xycoords=ax.get_yaxis_transform(), xytext=(-38, 0),
                textcoords="offset points", ha="right", va="center",
                fontsize=8.5, color="orange")

    # LOTUSim physics limit (~55 agents)
    ax.vlines(55, 0, PHYSICS_LIMIT, color="purple", linestyle=":", linewidth=1.0)
    ax.annotate("55", xy=(55, 0), xycoords=("data", "axes fraction"),
                xytext=(0, -14), textcoords="offset points",
                ha="center", va="top", fontsize=7.5, color="teal",
                annotation_clip=False)

    # LRAUVSim last real-time point: 115 agents
    lrauv_val_115 = df_lrauv.loc[df_lrauv["n_agents"] == 115, "mean_update_ms"].values
    lrauv_ymax_115 = float(lrauv_val_115[0]) if len(lrauv_val_115) else LRAUV_STEP
    ax.vlines(115, 0, lrauv_ymax_115, color="orange", linestyle=":", linewidth=1.0)
    ax.annotate("115", xy=(115, 0), xycoords=("data", "axes fraction"),
                xytext=(-10, -14), textcoords="offset points",
                ha="center", va="top", fontsize=7.5, color="orange",
                annotation_clip=False)

    # LRAUVSim first point not in real-time: 120 agents
    lrauv_val_120 = df_lrauv.loc[df_lrauv["n_agents"] == 120, "mean_update_ms"].values
    lrauv_ymax = float(lrauv_val_120[0]) if len(lrauv_val_120) else LRAUV_STEP
    ax.vlines(120, 0, lrauv_ymax, color="orange", linestyle=":", linewidth=1.0)
    ax.annotate("120\nnot RT", xy=(120, 0), xycoords=("data", "axes fraction"),
                xytext=(10, -14), textcoords="offset points",
                ha="center", va="top", fontsize=7.5, color="orange",
                annotation_clip=False)

    # LOTUSim user perception limit (~750 agents)
    ax.vlines(750, 0, USER_PERCEPTION_LIMIT, color="red", linestyle=":", linewidth=1.0)
    ax.annotate("750", xy=(750, 0), xycoords=("data", "axes fraction"),
                xytext=(0, -14), textcoords="offset points",
                ha="center", va="top", fontsize=7.5, color="teal",
                annotation_clip=False)

    ax.set_xlabel("nb_agents")
    ax.set_ylabel("Update (ms)")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.set_yticks([0, 30, 50, 100, 120, 150, 200])
    ax.legend(loc="upper left")
    ax.set_title("Protocol A — LRAUV\ndt = 200 ms, rendering ON")

    out_path = os.path.join(RESULTS_DIR, "lrauv_uuvsim_lotusim_update_plot.eps")
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    fig.savefig(out_path.replace(".eps", ".pdf"), bbox_inches="tight")
    fig.savefig(out_path.replace(".eps", ".png"), bbox_inches="tight")
    plt.close(fig)
    print(f"✅ Plot saved to {out_path} (.eps/.pdf/.png)")


# ==========================
# Main Execution
# ==========================


def main():
    # Load LRAUVSim CSV
    df_lrauv = load_lrauvsim_csv(LRAUVSIM_CSV)

    # Load LOTUSim data
    df_lotus = load_lotusim_data(LOTUSIM_DIR)

    # Save summary CSV
    save_lotusim_summary_csv(df_lotus)

    # Plot comparison
    plot_update_comparison(df_lrauv, df_lotus)


if __name__ == "__main__":
    main()
