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
@file statistics_accelerated_time.py
@author IRL Crossing

@brief Accelerated Time Simulation Performance Analysis (AI Training)

@note Analyzes RTF metrics from multiple simulators (LOTUSim, UUVSim, LRAUVSim)
and produces comparative visualizations.

Raw data and CSV summaries are saved in ./data/
Generated plots are saved in ./results/

@version 0.1
@date 2025-10-22
"""

import os
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

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

try:
    from scipy.stats import skew, kurtosis
except ModuleNotFoundError:
    def skew(values):
        values = np.asarray(values)
        std = np.std(values)
        if std == 0:
            return 0.0
        return np.mean(((values - np.mean(values)) / std) ** 3)

    def kurtosis(values):
        values = np.asarray(values)
        std = np.std(values)
        if std == 0:
            return 0.0
        return np.mean(((values - np.mean(values)) / std) ** 4) - 3

# ==========================
# Global Configuration
# ==========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
RAW_FILENAME = "simulation_1_raw_metrics.csv"
MIN_AGENTS = 1
MAX_AGENTS = 35
MAX_UUVSIM_HEADLESS_AGENTS = 50

# Folders to process
FOLDERS_TO_PROCESS = {
    "LOTUSIM_LRAUV": os.path.join(DATA_DIR, "lotusim", "lrauv_sensors_bridge_gui"),
    "LOTUSIM_BlueROV": os.path.join(DATA_DIR, "lotusim", "bluerov_sensors_bridge"),
    "LOTUSIM_BlueROV_Headless": os.path.join(DATA_DIR, "lotusim", "bluerov_sensors_headless_ai"),
    "UUVSim": os.path.join(DATA_DIR, "uuvsim"),
    "LRAUVSim": None,  # Data comes only from CSV for this case
}

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# ==========================
# Helper Functions
# ==========================


def safe_numeric(arr):
    """Convert a list to numeric values, discarding invalid entries (NaNs)."""
    numeric_arr = pd.to_numeric(arr, errors="coerce")
    return numeric_arr[~np.isnan(numeric_arr)]


def metric_evaluation(metrics, name):
    """Compute descriptive statistics for a numeric array."""
    stats = {
        "Metric": name,
        "Mean": round(np.mean(metrics), 4),
        "Median": round(np.median(metrics), 4),
        "Standard Deviation": round(np.std(metrics), 4),
        "Variance": round(np.var(metrics), 4),
        "Min": round(np.min(metrics), 4),
        "Max": round(np.max(metrics), 4),
    }

    if len(np.unique(metrics)) > 1:
        stats["Skewness"] = round(skew(metrics), 4)
        stats["Kurtosis"] = round(kurtosis(metrics), 4)
    else:
        stats["Skewness"] = 0.0
        stats["Kurtosis"] = 0.0

    return stats


# ==========================
# Data Processing Functions
# ==========================


def process_rtf_file(file_path):
    """
    Process a LOTUSim raw CSV file and return the mean RTF (normalized).
    Skips the first 350 warm-up steps.
    """
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()

    if "Real Time Factor (%)" not in df.columns:
        raise ValueError("Missing 'Real Time Factor (%)' column in CSV.")

    rtf_list = safe_numeric(df["Real Time Factor (%)"].tolist())
    if len(rtf_list) <= 350:
        raise ValueError("Insufficient RTF samples (<350).")

    rtf_list = rtf_list[350:]

    # Reject frozen/crashed simulations: std ≈ 0 means the RTF never changed
    if np.std(rtf_list) < 0.5:
        raise ValueError("RTF has near-zero variance — simulation likely frozen.")

    stats = metric_evaluation(rtf_list, "RTF")
    mean_rtf = stats["Mean"] / 100.0

    # Reject runs where the RTF is implausibly low (simulation failure)
    if mean_rtf < 0.1:
        raise ValueError(f"Mean RTF={mean_rtf:.3f} is too low — likely a failed run.")

    return mean_rtf


def collect_rtf_data(folder_name, summary_csv_name=None):
    """
    Collect RTF data from subfolders and save a summary CSV.
    Returns a DataFrame indexed by agent count.
    """
    rows = []

    for folder in os.listdir(folder_name):
        if not folder.isdigit():
            continue
        num_agents = int(folder)
        if not (MIN_AGENTS <= num_agents <= MAX_AGENTS):
            continue

        file_path = os.path.join(folder_name, folder, RAW_FILENAME)
        if not os.path.isfile(file_path):
            continue

        try:
            mean_rtf = process_rtf_file(file_path)
            rows.append({"n_agents": num_agents, "mean_rtf": mean_rtf})
        except Exception:
            continue

    df_summary = pd.DataFrame(rows).set_index("n_agents").sort_index() if rows else pd.DataFrame()

    if not df_summary.empty:
        df_summary["mean_rtf"] = df_summary["mean_rtf"].round(2)

    if summary_csv_name:
        out_path = os.path.join(DATA_DIR, summary_csv_name)
        df_summary.to_csv(out_path)
        print(f"✅ Saved summary CSV: {out_path}")

    return df_summary


def extract_rtf_column(df):
    """Automatically detect the most likely RTF column in a CSV."""
    keywords = ["rtf", "real time"]
    candidates = [col for col in df.columns if any(k in col.lower() for k in keywords)]
    if not candidates:
        raise ValueError("No RTF-like column found in CSV.")
    return candidates[0]


def process_uuvsim_file(file_path):
    """
    Process a UUVSim CSV file and return the median RTF over the stable phase.

    For accelerated-time (Protocol C & D) data the RTF has high natural variance,
    so a fixed 10 % warm-up skip is used to discard the spawning transient, and
    the median is used instead of the mean to suppress the effect of outliers.
    """
    df = pd.read_csv(file_path, on_bad_lines="skip")
    df.columns = df.columns.str.strip()
    rtf_col = extract_rtf_column(df)
    rtf = pd.to_numeric(df[rtf_col], errors="coerce").dropna().reset_index(drop=True)
    if len(rtf) == 0:
        raise ValueError("No valid RTF samples in UUVSim CSV.")

    # Skip first 10 % of samples (spawning / warm-up phase), then use mean
    skip = max(1, int(0.10 * len(rtf)))
    stable_rtf = rtf.iloc[skip:]

    if len(stable_rtf) == 0:
        raise ValueError("No stable RTF samples found.")
    return round(float(stable_rtf.mean()), 4)


def collect_uuvsim_data(
    folder_name,
    summary_csv_name="uuvsim_rtf_plot_data.csv",
    filename_suffixes=("_agent", "_agents"),
    max_agents=MAX_AGENTS,
):
    """Collect UUVSim CSVs matching a filename suffix and save summary data."""
    rows = []

    for filename in os.listdir(folder_name):
        if not filename.startswith("benchmark_rtf_") or not filename.endswith(".csv"):
            continue
        stem = filename.replace(".csv", "")
        if filename_suffixes and not stem.endswith(filename_suffixes):
            continue
        try:
            num_agents = int(stem.split("_")[2])
            if not (MIN_AGENTS <= num_agents <= max_agents):
                continue
            mean_rtf = process_uuvsim_file(os.path.join(folder_name, filename))
            rows.append({"n_agents": num_agents, "mean_rtf": mean_rtf})
        except Exception:
            continue

    df_summary = pd.DataFrame(rows).set_index("n_agents").sort_index() if rows else pd.DataFrame()
    if not df_summary.empty:
        df_summary["mean_rtf"] = df_summary["mean_rtf"].round(2)

    out_path = os.path.join(DATA_DIR, summary_csv_name)
    df_summary.to_csv(out_path)
    print(f"✅ Saved summary CSV: {out_path}")

    return df_summary


def load_data(label):
    """Load RTF summary CSV for a simulator."""
    csv_path = os.path.join(DATA_DIR, f"{label.lower()}_rtf_plot_data.csv")
    if os.path.isfile(csv_path):
        df = pd.read_csv(csv_path)
        return df.set_index("n_agents").sort_index()
    else:
        print(f"⚠️ CSV not found for {label}: {csv_path}")
        return pd.DataFrame()


# ==========================
# Plotting Functions
# ==========================


def add_real_time_line(ax):
    """Add a horizontal line at RTF=1 to indicate real-time speed."""
    ax.axhline(y=1, color="red", linestyle="--", linewidth=1.2)
    ax.annotate("Real-time\n(×1 speed)", xy=(0, 1),
                xycoords=ax.get_yaxis_transform(), xytext=(-38, 0),
                textcoords="offset points", ha="right", va="center",
                fontsize=8.5, color="red")


def configure_axes(ax, ymax):
    """Configure plot axes, ticks, labels, and grid."""
    ax.set_ylim(0, max(3, ymax + 1))

    yticks = ax.get_yticks()
    if 1 not in yticks:
        yticks = np.append(yticks, 1)
    ax.set_yticks(sorted(yticks))

    def y_formatter(val, _):
        return "" if val == 0 else str(int(val)) if val.is_integer() else str(val)

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(y_formatter))

    ax.set_xlabel("nb_agents")
    ax.set_ylabel(r"$\overline{\mathrm{RTF}}$ (>1 = faster)")
    ax.set_xticks(range(MIN_AGENTS, MAX_AGENTS + 1, 2))


def plot_curves(
    selected_labels,
    filename,
    custom_colors=None,
    custom_labels=None,
    title="",
    min_agents=MIN_AGENTS,
    max_agents=MAX_AGENTS,
    x_tick_step=2,
):
    """Plot RTF curves for selected simulators and save EPS."""
    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    ymax = 0
    full_index = np.arange(min_agents, max_agents + 1)

    for label in selected_labels:
        df = load_data(label)
        if df.empty:
            continue
        df = df.reindex(full_index)
        color = custom_colors.get(label, "black") if custom_colors else "black"
        name = custom_labels.get(label, label) if custom_labels else label

        df_valid = df.dropna()
        ax.plot(df_valid.index, df_valid["mean_rtf"],
                marker="o", markersize=4, linestyle="-", linewidth=1.5, color=color, label=name)
        if not df["mean_rtf"].isna().all():
            ymax = max(ymax, df["mean_rtf"].max())

    add_real_time_line(ax)
    configure_axes(ax, ymax)
    # Start ticks at the first clean multiple of x_tick_step
    first_tick = x_tick_step if x_tick_step > 1 else min_agents
    ax.set_xticks(range(first_tick, max_agents + 1, x_tick_step))

    ax.legend(loc="upper right")
    if title:
        ax.set_title(title)
    fig.tight_layout()

    out_path = os.path.join(RESULTS_DIR, filename)
    fig.savefig(out_path, bbox_inches="tight")
    fig.savefig(out_path.replace(".eps", ".pdf"), bbox_inches="tight")
    fig.savefig(out_path.replace(".eps", ".png"), bbox_inches="tight")
    plt.close(fig)
    print(f"✅ Saved plot: {out_path} (.eps/.pdf/.png)")


# ==========================
# Custom Plot Configurations
# ==========================
LRAUV_COLORS = {"LOTUSIM_LRAUV": "teal", "LRAUVSim": "orange"}
LRAUV_LABELS = {"LOTUSIM_LRAUV": "LOTUSim", "LRAUVSim": "LRAUVSim"}

BLUEROV_COLORS = {"LOTUSIM_BlueROV": "teal", "UUVSim": "blue"}
BLUEROV_LABELS = {"LOTUSIM_BlueROV": "LOTUSim — BlueROV2", "UUVSim": "UUVSim — BlueROV2"}

BLUEROV_HEADLESS_COLORS = {"UUVSim_Headless": "blue", "LOTUSIM_BlueROV_Headless": "teal"}
BLUEROV_HEADLESS_LABELS = {"UUVSim_Headless": "UUVSim — BlueROV2 (headless)", "LOTUSIM_BlueROV_Headless": "LOTUSim — BlueROV2 (headless)"}

UUVSIM_RENDERING_COLORS = {"UUVSim": "blue", "UUVSim_Headless": "green"}
UUVSIM_RENDERING_LABELS = {
    "UUVSim": "UUVSim with rendering",
    "UUVSim_Headless": "UUVSim headless",
}


# ==========================
# Main Execution
# ==========================
def main():
    # Generate summary CSVs for each simulator
    for label, folder in FOLDERS_TO_PROCESS.items():
        if folder is None or not os.path.isdir(folder):
            continue
        summary_csv_name = f"{label.lower()}_rtf_plot_data.csv"
        if label == "UUVSim":
            collect_uuvsim_data(
                folder,
                summary_csv_name,
                filename_suffixes=("_agent", "_agents"),
                max_agents=MAX_UUVSIM_HEADLESS_AGENTS,
            )
            collect_uuvsim_data(
                folder,
                "uuvsim_headless_rtf_plot_data.csv",
                filename_suffixes=("_headless",),
                max_agents=MAX_UUVSIM_HEADLESS_AGENTS,
            )
        else:
            collect_rtf_data(folder, summary_csv_name)

    # Plot comparisons
    plot_curves(
        selected_labels=["LOTUSIM_BlueROV", "UUVSim"],
        filename="bluerov_ai_training_comparison.eps",
        custom_colors=BLUEROV_COLORS,
        custom_labels=BLUEROV_LABELS,
        title="Protocol C — BlueROV2\ndt = 30 ms, TPS = 33, rendering ON",
        x_tick_step=5,
    )

    plot_curves(
        selected_labels=["LOTUSIM_LRAUV", "LRAUVSim"],
        filename="lrauv_ai_training_comparison.eps",
        custom_colors=LRAUV_COLORS,
        custom_labels=LRAUV_LABELS,
        title="Protocol C — LRAUV\ndt = 30 ms, TPS = 33, rendering ON",
    )

    plot_curves(
        selected_labels=["UUVSim_Headless", "LOTUSIM_BlueROV_Headless"],
        filename="bluerov_ai_training_headless_comparison.eps",
        custom_colors=BLUEROV_HEADLESS_COLORS,
        custom_labels=BLUEROV_HEADLESS_LABELS,
        title="Protocol D — BlueROV2\ndt = 30 ms, TPS = 33, rendering OFF",
        max_agents=50,
        x_tick_step=10,
    )

if __name__ == "__main__":
    main()
