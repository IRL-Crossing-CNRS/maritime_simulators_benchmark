"""
Stonefish Simulation — Results analysis and figure generation
==============================================================

    Protocol A  (A-human-loop) : Y = mean Update (ms), threshold 210 ms
    Protocol B  (B-control)    : Y = mean Update (ms), threshold 30  ms
    Protocol C  (C-ai-render)  : Y = mean RTF,         threshold RTF = 1
    Protocol D  (D-ai-headless): Y = mean RTF,         threshold RTF = 1

Protocols A/B/C crash at n=9 (MAX_OCEAN_CURRENTS=64, 8 thrusters/agent).
Protocol D (headless) is unaffected — scales to 90 agents.

Usage:
    python analyse_stonefish.py [--csv PATH] [--outdir DIR]
"""

import argparse
import os

import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt

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

STONEFISH_COLOR = "#4fa3d1"
SEGFAULT_COLOR  = "red"
THRESHOLD_COLOR = "#7B2D8B"   # purple — matches paper

BUDGET_A_MS  = 200.0
BUDGET_B_MS  =  30.0
RTF_REALTIME =   1.0


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _save(fig: plt.Figure, path: str) -> None:
    """Save EPS, PDF, and PNG."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    print(f"  saved: {path}")
    pdf_path = path.replace(".eps", ".pdf")
    fig.savefig(pdf_path, bbox_inches="tight")
    print(f"  saved: {pdf_path}")
    png_path = path.replace(".eps", ".png")
    fig.savefig(png_path, bbox_inches="tight")
    print(f"  saved: {png_path}")
    plt.close(fig)


def _threshold_label(ax: plt.Axes, threshold: float, text: str, color: str) -> None:
    """Left-side annotation for a horizontal threshold line."""
    ax.annotate(
        text,
        xy=(0, threshold),
        xycoords=ax.get_yaxis_transform(),
        xytext=(-38, 0),
        textcoords="offset points",
        ha="right", va="center",
        fontsize=8.5, color=color,
    )


def _regular_xticks(data: pd.DataFrame, count: int = 6) -> list:
    n_min = float(data["agents"].min())
    n_max = float(data["agents"].max())
    if count <= 1 or n_min == n_max:
        return [n_min]
    ticks = np.linspace(n_min, n_max, count)
    return sorted({float(int(round(t))) for t in ticks})


def _apply_xticks(ax: plt.Axes, ticks: list, colored: dict) -> None:
    """
    Set x-ticks and colour specific ones.
    colored: {tick_value: color_string}
    """
    ticks = sorted(set(ticks))
    labels = [str(int(round(t))) if abs(t - round(t)) < 1e-9 else f"{t:g}"
              for t in ticks]
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels)
    for val, lbl in zip(ticks, ax.get_xticklabels()):
        rv = int(round(val))
        if rv in colored:
            lbl.set_color(colored[rv])


def _add_segfault_annotation(ax: plt.Axes, n_crash: int) -> None:
    """
    Red dashed vertical line at n_crash.
    The x-tick itself is coloured red.
    """
    ax.axvline(n_crash, color=SEGFAULT_COLOR, linestyle="--", linewidth=1.0,
               zorder=1)

    # Annotation below the x-axis using axes-fraction coordinates
    ax.annotate(
        "Seg. fault",
        xy=(n_crash, 0),
        xycoords=("data", "axes fraction"),
        xytext=(0, -20),
        textcoords="offset points",
        ha="center", va="top",
        fontsize=7.5,
        color=SEGFAULT_COLOR,
        linespacing=1.3,
        annotation_clip=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Protocols A & B  —  Y-axis: mean Update (ms)
# ─────────────────────────────────────────────────────────────────────────────

def _plot_update_ms(df: pd.DataFrame,
                    protocol_tag: str,
                    budget_ms: float,
                    title: str,
                    outname: str,
                    outdir: str,
                    threshold_label: str,
                    segfault_n: int | None = None) -> None:
    data = df[(df["protocol"] == protocol_tag) & (df["status"] == "ok")].copy()
    if data.empty:
        print(f"  Skipping {outname} — no valid data for '{protocol_tag}'")
        return

    data = data.groupby("agents", as_index=False).agg({"mean_step_ms": "mean"})
    data = data.sort_values("agents")

    fig, ax = plt.subplots(figsize=(5.5, 3.8))

    ax.plot(data["agents"], data["mean_step_ms"],
            color=STONEFISH_COLOR, marker="o", markersize=4, linewidth=1.5,
            label="Stonefish — BlueROV2")

    # Threshold line in purple
    ax.axhline(budget_ms, color=THRESHOLD_COLOR, linestyle="--", linewidth=1.2)
    _threshold_label(ax, budget_ms, threshold_label, THRESHOLD_COLOR)

    # x-axis: all agent ticks + segfault tick coloured red
    base_ticks = list(data["agents"].astype(float))
    colored = {}
    if segfault_n is not None:
        colored[segfault_n] = SEGFAULT_COLOR
    _apply_xticks(ax, base_ticks + ([float(segfault_n)] if segfault_n else []),
                  colored)

    x_right = (segfault_n + 0.8) if segfault_n else float(data["agents"].max()) + 0.5
    ax.set_xlim(left=0, right=x_right)

    if protocol_tag == "B-control":
            ax.set_ylim(0, budget_ms + 10) 
    else:
            ax.set_ylim(0, budget_ms + 50)


    if segfault_n is not None:
        _add_segfault_annotation(ax, segfault_n)

    ax.set_xlabel("nb_agents")
    ax.set_ylabel(r"$\overline{\mathrm{step size}}$ (ms)")

    ax.set_title(title)
    ax.legend(loc="center")

    _save(fig, os.path.join(outdir, outname))


# ─────────────────────────────────────────────────────────────────────────────
# Protocols C & D  —  Y-axis: mean RTF
# ─────────────────────────────────────────────────────────────────────────────

def _plot_rtf(df: pd.DataFrame,
              protocol_tag: str,
              title: str,
              outname: str,
              outdir: str,
              downsample_step: int | None = None,
              segfault_n: int | None = None) -> None:
    data = df[(df["protocol"] == protocol_tag) & (df["status"] == "ok")].copy()
    if data.empty:
        print(f"  Skipping {outname} — no valid data for '{protocol_tag}'")
        return

    data = data.groupby("agents", as_index=False).agg({"mean_rtf": "max"})
    data = data.sort_values("agents")

    # Downsample markers only for Protocol D (dense data)
    if downsample_step is not None:
        mask = data["agents"] % downsample_step == 0
        mask.iloc[0]  = True
        mask.iloc[-1] = True
        plot_data = data[mask].copy()
    else:
        plot_data = data.copy()

    fig, ax = plt.subplots(figsize=(5.5, 3.8))

    # Continuous line through all points; markers on (possibly thinned) subset
    ax.plot(data["agents"], data["mean_rtf"],
            color=STONEFISH_COLOR, linewidth=1.5, zorder=2)
    ax.plot(plot_data["agents"], plot_data["mean_rtf"],
            color=STONEFISH_COLOR, marker="o", markersize=4, linewidth=0,
            label="Stonefish — BlueROV2", zorder=3)

    # Threshold line: real-time RTF = 1.0 in red
    ax.axhline(RTF_REALTIME, color="red", linestyle="--", linewidth=1.2)
    _threshold_label(ax, RTF_REALTIME, "Real-time\n(x1 speed)", "red")

    # x-ticks: all agent values (or downsampled set) + segfault tick
    base_ticks = list(plot_data["agents"].astype(float))
    colored = {}
    if segfault_n is not None:
        colored[segfault_n] = SEGFAULT_COLOR
    _apply_xticks(ax, base_ticks + ([float(segfault_n)] if segfault_n else []),
                  colored)

    x_right = (segfault_n + 0.8) if segfault_n else float(data["agents"].max()) + 1
    ax.set_xlim(left=0, right=x_right)
    if protocol_tag == "C-ai-render":
        ax.set_ylim(0, 250)
    else:
        ax.set_ylim(bottom=0)

    if segfault_n is not None:
        _add_segfault_annotation(ax, segfault_n)

    ax.set_xlabel("nb_agents")
    ax.set_ylabel(r"$\overline{\mathrm{RTF}}$")
    ax.set_title(title)
    ax.legend(loc="center")

    _save(fig, os.path.join(outdir, outname))


# ─────────────────────────────────────────────────────────────────────────────
# Public figure functions
# ─────────────────────────────────────────────────────────────────────────────

def fig_protocol_A(df: pd.DataFrame, outdir: str) -> None:
    _plot_update_ms(
        df,
        protocol_tag="A-human-loop",
        budget_ms=BUDGET_A_MS,
        title="Protocol A\ndt = 200 ms, TPS = 5, rendering ON",
        outname="stonefish_protocol_A.eps",
        outdir=outdir,
        threshold_label="User\nperception\nlimit",
        segfault_n=9,
    )


def fig_protocol_B(df: pd.DataFrame, outdir: str) -> None:
    _plot_update_ms(
        df,
        protocol_tag="B-control",
        budget_ms=BUDGET_B_MS,
        title="Protocol B\ndt = 30 ms, TPS = 33, rendering ON",
        outname="stonefish_protocol_B.eps",
        outdir=outdir,
        threshold_label="Physics\nlimit",
        segfault_n=9,
    )


def fig_protocol_C(df: pd.DataFrame, outdir: str) -> None:
    _plot_rtf(
        df,
        protocol_tag="C-ai-render",
        title="Protocol C\ndt = 30 ms, TPS = 33, rendering ON",
        outname="stonefish_protocol_C.eps",
        outdir=outdir,
        downsample_step=None,
        segfault_n=9,
    )


def fig_protocol_D(df: pd.DataFrame, outdir: str) -> None:
    _plot_rtf(
        df,
        protocol_tag="D-ai-headless",
        title="Protocol D\ndt = 30 ms, TPS = 33, rendering OFF",
        outname="stonefish_protocol_D.eps",
        outdir=outdir,
        downsample_step=5,
        segfault_n=None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse Stonefish benchmark results and generate article figures.")
    parser.add_argument("--csv",    default="results/benchmark_summary.csv")
    parser.add_argument("--outdir", default="figures")
    args = parser.parse_args()

    print(f"\nLoading: {args.csv}")
    df = pd.read_csv(args.csv)

    df_ok = df[df["status"] == "ok"]
    for tag in ["A-human-loop", "B-control", "C-ai-render", "D-ai-headless"]:
        n_agents = df_ok[df_ok["protocol"] == tag]["agents"].nunique()
        print(f"  {tag}: {len(df_ok[df_ok['protocol']==tag])} rows, "
              f"{n_agents} unique agent counts")

    print(f"\nGenerating figures → {args.outdir}/")
    for proto, fn in [
        ("A-human-loop",  fig_protocol_A),
        ("B-control",     fig_protocol_B),
        ("C-ai-render",   fig_protocol_C),
        ("D-ai-headless", fig_protocol_D),
    ]:
        if not df[df["protocol"] == proto].empty:
            fn(df, args.outdir)
        else:
            print(f"  Skipping '{proto}' — no data")

    print("\nDone.")


if __name__ == "__main__":
    main()
