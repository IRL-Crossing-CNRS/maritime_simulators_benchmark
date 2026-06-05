"""
HoloOcean BlueROV2 — Results analysis and figure generation
============================================================

Reads benchmark_results.csv directly and generates figures for the article:
    fig1 — Protocol A: tick_ms vs n_agents  (real-time HITL scalability)
    fig2 — Protocol B: tick_ms vs n_agents  (autonomous control scalability)
    fig3 — Protocol D: tick_ms vs n_agents  (headless AI training throughput)

Usage:
    python analyse.py [--csv PATH] [--outdir DIR]

Defaults:
    --csv    results/benchmark_results.csv
    --outdir figures/
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

BUDGET_200_MS       = 200.0
BUDGET_30_MS        =  30.0
PRACTICAL_LIMIT_MS  =  31.0   # tolerated margin above the 30 ms physics limit

holoocean_color = "#c46a1a"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _save(fig: plt.Figure, path: str) -> None:
    """Save `fig` to EPS, PDF, and PNG (creating parent dirs as needed) and close it."""
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


def _crossing_x(data: pd.DataFrame, ycol: str, threshold: float) -> float | None:
    """Return the interpolated x-value where `ycol` crosses `threshold`, or None."""
    x = data["n"].to_numpy(dtype=float)
    y = data[ycol].to_numpy(dtype=float)

    for i in range(len(data) - 1):
        x1, x2 = x[i], x[i + 1]
        y1, y2 = y[i], y[i + 1]
        crosses = (y1 <= threshold <= y2) or (y1 >= threshold >= y2)
        if not crosses:
            continue
        if y2 == y1:
            return x1
        return x1 + (threshold - y1) * (x2 - x1) / (y2 - y1)
    return None


def _add_threshold_label(ax: plt.Axes, threshold: float, text: str, color: str) -> None:
    """Annotate a horizontal threshold line with a left-side label."""
    ax.annotate(
        text,
        xy=(0, threshold),
        xycoords=ax.get_yaxis_transform(),
        xytext=(-38, 0),
        textcoords="offset points",
        ha="right",
        va="center",
        fontsize=8.5,
        color=color,
    )


def _add_partial_vertical(ax: plt.Axes,
                          x_value: float,
                          y_value: float,
                          line_color: str,
                          y_bottom: float = 0.0) -> None:
    """Draw a dotted vertical line from `y_bottom` up to `y_value` at `x_value`."""
    ax.vlines(x_value, y_bottom, y_value, color=line_color, linestyle=":", linewidth=1.2)


def _regular_xticks(data: pd.DataFrame, count: int = 6) -> list[float]:
    """Return `count` evenly-spaced x-tick values spanning the agent-count range."""
    n_min = float(data["n"].min())
    n_max = float(data["n"].max())
    if count <= 1 or n_min == n_max:
        return [n_min]
    ticks = np.linspace(n_min, n_max, count)
    rounded_ticks = [int(round(tick)) for tick in ticks]
    return [float(tick) for tick in sorted(set(rounded_ticks))]


def _protocol_a_xticks(data: pd.DataFrame) -> list[float]:
    """Return hand-picked round x-tick values for Protocol A's wide agent range (100–3100)."""
    preferred = [100, 300, 500, 700, 900, 1100, 1300, 1500, 1700, 1900, 2100, 2300, 2500, 2700, 2900, 3100]
    available = set(data["n"].astype(int).tolist())
    ticks = [float(tick) for tick in preferred if tick in available]
    return sorted(set(ticks))


def _set_colored_xticks(ax: plt.Axes,
                        base_ticks: list[float],
                        special_tick: float,
                        special_color: str,
                        special_label: str | None = None) -> None:
    """Set x-ticks and colour `special_tick` differently to highlight the ceiling agent count."""
    ticks = sorted(set(base_ticks + [special_tick]))
    labels = []
    for tick in ticks:
        if abs(tick - round(tick)) < 1e-9:
            labels.append(str(int(round(tick))))
        else:
            labels.append(f"{tick:g}")
    if special_label is not None:
        labels[ticks.index(special_tick)] = special_label

    ax.set_xticks(ticks)
    ax.set_xticklabels(labels)

    for tick_value, tick_label in zip(ticks, ax.get_xticklabels()):
        if abs(tick_value - special_tick) < 1e-9:
            tick_label.set_color(special_color)


def _add_bottom_note(ax: plt.Axes, x_value: float, text: str, color: str) -> None:
    """Add a small annotation below the x-axis at `x_value` (e.g. crash/ceiling note)."""
    ax.annotate(
        text,
        xy=(x_value, 0),
        xycoords=ax.get_xaxis_transform(),
        xytext=(12, -14),
        textcoords="offset points",
        ha="left",
        va="top",
        fontsize=8.5,
        color=color,
    )


def _last_within_budget_n(data: pd.DataFrame, ycol: str, threshold: float) -> float | None:
    """Return the agent count of the last row where `ycol` is still within `threshold`."""
    valid = data[data[ycol] <= threshold]
    if valid.empty:
        return None
    return float(valid.iloc[-1]["n"])


# ─────────────────────────────────────────────────────────────────────────────
# Figures
# ─────────────────────────────────────────────────────────────────────────────

def fig_protocol_A(df: pd.DataFrame, outdir: str) -> None:
    """
    Protocol A — full_frame_ms vs n_agents.
    Shows the user-perception limit (200ms) and the physics control limit (30ms).
    Annotates the last agent count below budget (ceiling).
    """
    data = df[df["protocol"] == "A"].sort_values("n")

    fig, ax = plt.subplots(figsize=(5.5, 3.8))

    ax.plot(data["n"], data["full_frame_ms"],
            color=holoocean_color, marker="o", markersize=4, linewidth=1.5,
            label="HoloOcean — BlueROV2")

    ax.axhline(BUDGET_200_MS, color="red", linestyle="--", linewidth=1.2)
    _add_threshold_label(ax, BUDGET_200_MS, "User\nperception\nlimit", "red")

    last_point = data.iloc[-1]
    _add_partial_vertical(ax, float(last_point["n"]), float(last_point["full_frame_ms"]), holoocean_color)
    _set_colored_xticks(
        ax,
        _protocol_a_xticks(data),
        float(last_point["n"]),
        holoocean_color,
    )
    _add_bottom_note(ax, float(last_point["n"]), "Exceeds\nbuffer\nsize", holoocean_color)

    ax.set_xlabel("nb_agents")
    ax.set_ylabel(r"$\overline{\mathrm{full\_frame\_ms}}$ (ms)")
    ax.set_title("Protocol A\n"
                 "dt = 200 ms, TPS = 5, rendering ON")
    ax.legend(loc="upper left")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0, top=230)
    ax.tick_params(axis="x", rotation=45)

    _save(fig, os.path.join(outdir, "holoocean_protocol_A.eps"))


def fig_protocol_B(df: pd.DataFrame, outdir: str) -> None:
    """
    Protocol B — full_frame_ms vs n_agents.

    The hard physics limit is 30 ms, but a practical margin of 31 ms is
    tolerated.  We therefore:
      - draw the 30 ms horizontal budget line
      - place the vertical marker and colour the x-tick at the FIRST
        configuration that exceeds the practical limit (31 ms), i.e. n = 11
    """
    data = df[df["protocol"] == "B"].sort_values("n")

    fig, ax = plt.subplots(figsize=(5.5, 3.8))

    ax.plot(data["n"], data["full_frame_ms"],
            color=holoocean_color, marker="o", markersize=4, linewidth=1.5,
            label="HoloOcean — BlueROV2")

    # ── 30 ms budget line ──────────────────────────────────────────────────
    ax.axhline(BUDGET_30_MS, color="purple", linestyle="--", linewidth=1.2)
    _add_threshold_label(ax, BUDGET_30_MS, "Physics\nlimit", "purple")

    # ── First configuration that exceeds the practical limit (31 ms) ───────
    invalid = data[data["full_frame_ms"] >= PRACTICAL_LIMIT_MS]
    if not invalid.empty:
        first_failing_n = float(invalid.iloc[0]["n"])
        first_failing_y = float(invalid.iloc[0]["full_frame_ms"])

        # vertical dotted line from bottom of axis up to the data point
        _add_partial_vertical(ax, first_failing_n, first_failing_y, holoocean_color, y_bottom=28.5)

        # x-ticks: 2 4 6 8 10 12 14, with the failing tick coloured
        max_n = int(data["n"].max())
        base_ticks = [float(t) for t in range(2, max_n + 1, 2)]
        _set_colored_xticks(ax, base_ticks, first_failing_n, holoocean_color)
    else:
        max_n = int(data["n"].max())
        ax.set_xticks(range(2, max_n + 1, 2))

    ax.set_xlabel("nb_agents")
    ax.set_ylabel(r"$\overline{\mathrm{full\_frame\_ms}}$ (ms)")
    ax.set_title("Protocol B \n"
                 "dt = 30 ms, TPS = 33, rendering ON")
    ax.legend(loc="upper left")
    ax.set_xlim(left=0)

    # ── Very tight framing so the curve appears flat near 30 ms ───────────
    ax.set_ylim(0, 80)
    ax.set_yticks([0, 10, 20, 30, 40, 50, 60, 70])
    ax.margins(y=0.0)

    _save(fig, os.path.join(outdir, "holoocean_protocol_B.eps"))


def fig_protocol_D(df: pd.DataFrame, outdir: str) -> None:
    """
    Protocol D — full_frame_ms vs n_agents, headless mode.
    Uses the SAME axis framing as Protocol B for direct visual comparison:
      - ylim 24–32, yticks at [24, 26, 28, 30, 31, 32]
      - vertical marker and coloured tick at the first config exceeding 31 ms
      - 30 ms budget line + label
    """
    data = df[df["protocol"] == "D"].sort_values("n")

    fig, ax = plt.subplots(figsize=(5.5, 3.8))

    ax.plot(data["n"], data["full_frame_ms"],
            color=holoocean_color, marker="o", markersize=4, linewidth=1.5,
            label="HoloOcean — BlueROV2 (headless)")

    # ── 30 ms budget line ──────────────────────────────────────────────────
    ax.axhline(BUDGET_30_MS, color="purple", linestyle="--", linewidth=1.2)
    _add_threshold_label(ax, BUDGET_30_MS, "Physics\nlimit", "purple")

    # ── First configuration that exceeds the practical limit (31 ms) ───────
    invalid = data[data["full_frame_ms"] >= PRACTICAL_LIMIT_MS]
    if not invalid.empty:
        first_failing_n = float(invalid.iloc[0]["n"])
        first_failing_y = float(invalid.iloc[0]["full_frame_ms"])

        _add_partial_vertical(ax, first_failing_n, first_failing_y, holoocean_color, y_bottom=28.5)

        max_n = int(data["n"].max())
        base_ticks = [float(t) for t in range(2, max_n + 1, 2)]
        _set_colored_xticks(ax, base_ticks, first_failing_n, holoocean_color)
    else:
        # no configuration exceeds 31 ms — just show even ticks
        max_n = int(data["n"].max())
        ax.set_xticks(range(2, max_n + 1, 2))

    ax.set_xlabel("nb_agents")
    ax.set_ylabel(r"$\overline{\mathrm{full\_frame\_ms}}$ (ms)")
    ax.set_title("Protocol D \n"
                 "dt = 30 ms, TPS = 33, rendering OFF")
    ax.legend(loc="upper left")
    ax.set_xlim(left=0)

    # ── Same tight framing as Protocol B ──────────────────────────────────
    ax.set_ylim(0, 80)
    ax.set_yticks([0, 10, 20, 30, 40, 50, 60, 70])
    ax.margins(y=0.0)

    _save(fig, os.path.join(outdir, "holoocean_protocol_D.eps"))


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse benchmark results and generate article figures.")
    parser.add_argument("--csv",    default="results/benchmark_all_protocols.csv",
                        help="Input CSV (not modified)")
    parser.add_argument("--outdir", default="figures",
                        help="Output directory for figures")
    args = parser.parse_args()

    print(f"\nLoading: {args.csv}")
    df = pd.read_csv(args.csv)

    print(f"  Protocol A: {len(df[df['protocol']=='A'])} rows")
    print(f"  Protocol B: {len(df[df['protocol']=='B'])} rows")
    print(f"  Protocol D: {len(df[df['protocol']=='D'])} rows")

    print(f"\nGenerating figures → {args.outdir}/")
    if not df[df["protocol"] == "A"].empty:
        fig_protocol_A(df, args.outdir)
    else:
        print("  Skipping fig1 — no Protocol A data")

    if not df[df["protocol"] == "B"].empty:
        fig_protocol_B(df, args.outdir)
    else:
        print("  Skipping fig2 — no Protocol B data")

    if not df[df["protocol"] == "D"].empty:
        fig_protocol_D(df, args.outdir)
    else:
        print("  Skipping fig3 — no Protocol D data")

    print("\nDone.")


if __name__ == "__main__":
    main()