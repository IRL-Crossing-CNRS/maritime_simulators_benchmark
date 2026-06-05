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
@file process_uuvsim.py
@author IRL Crossing

@brief Process UUVSim raw benchmark data into a summary CSV.

@details
Reads per-agent raw CSVs from data/uuv/AB/<n_agents>/. Only samples recorded
AFTER all agents are spawned are used. The spawning period is detected via the
benchmark_rtf.csv: the first index where the rolling RTF standard deviation
drops below a threshold is taken as the end of the spawning phase. The same
fraction of samples is then skipped in update_times.csv.

Inputs:
    - data/uuv/AB/<n_agents>/benchmark_rtf.csv   — RTF per physics step
    - data/uuv/AB/<n_agents>/update_times.csv    — physics update duration (s)
    - data/uuv/AB/<n_agents>/render_fps.csv      — render FPS

Outputs:
    - data/UUVSim_results.csv  (n_agents, mean_update_ms, mean_fps)
"""

import os
import pandas as pd
import numpy as np

DATA_DIR = os.path.join("data", "uuv", "AB")
OUTPUT_CSV = os.path.join("data", "UUVSim_results.csv")

# Rolling-std window and threshold used to detect RTF stability
RTF_STABILITY_WINDOW = 50
RTF_STABILITY_THRESHOLD = 5.0


def stable_start_fraction(rtf_path):
    """
    Return the fraction of the RTF time-series that belongs to the spawning
    (unstable) phase. The stable phase starts at the first index where the
    rolling standard deviation over RTF_STABILITY_WINDOW samples drops below
    RTF_STABILITY_THRESHOLD.
    """
    df = pd.read_csv(rtf_path, on_bad_lines="skip", header=None, names=["rtf"])
    rtf = pd.to_numeric(df["rtf"], errors="coerce").dropna().reset_index(drop=True)
    rtf = rtf[rtf > 0].reset_index(drop=True)

    if rtf.empty:
        return 0.0

    roll_std = rtf.rolling(RTF_STABILITY_WINDOW).std()
    stable_idx = roll_std[roll_std < RTF_STABILITY_THRESHOLD].index
    if len(stable_idx) == 0:
        return 0.0
    return stable_idx[0] / len(rtf)


def compute_mean_update(update_path, skip_fraction):
    """
    Return mean update duration in ms using only the stable (post-spawn) portion.
    skip_fraction is the fraction of samples to discard from the start.
    """
    df = pd.read_csv(update_path, header=None, names=["upd"])
    upd = pd.to_numeric(df["upd"], errors="coerce").dropna().reset_index(drop=True)
    upd = upd[upd > 0].reset_index(drop=True)

    skip = int(skip_fraction * len(upd))
    stable = upd.iloc[skip:]
    return round(float(stable.mean() * 1000), 6)


def compute_mean_fps(fps_path, skip_fraction):
    """Return mean FPS from the stable (post-spawn) portion of render_fps.csv."""
    df = pd.read_csv(fps_path)
    df.columns = df.columns.str.strip()
    fps_col = next((c for c in df.columns if "FPS" in c.upper()), None)
    if fps_col is None:
        return None
    fps = pd.to_numeric(df[fps_col], errors="coerce").dropna().reset_index(drop=True)
    fps = fps[fps > 0].reset_index(drop=True)
    skip = int(skip_fraction * len(fps))
    stable = fps.iloc[skip:]
    return round(float(stable.mean()), 4) if not stable.empty else None


def main():
    rows = []
    for folder in sorted(os.listdir(DATA_DIR), key=lambda x: int(x) if x.isdigit() else float("inf")):
        if not folder.isdigit():
            continue
        n_agents = int(folder)
        rtf_path = os.path.join(DATA_DIR, folder, "benchmark_rtf.csv")
        update_path = os.path.join(DATA_DIR, folder, "update_times.csv")
        fps_path = os.path.join(DATA_DIR, folder, "render_fps.csv")

        if not os.path.isfile(update_path):
            print(f"⚠️  Missing: {update_path}")
            continue

        skip_frac = stable_start_fraction(rtf_path) if os.path.isfile(rtf_path) else 0.0
        mean_ms = compute_mean_update(update_path, skip_frac)
        mean_fps = compute_mean_fps(fps_path, skip_frac) if os.path.isfile(fps_path) else None

        print(f"  {n_agents:3d} agents → skip={skip_frac*100:.1f}%  update={mean_ms:.2f} ms  fps={mean_fps}")
        rows.append({"n_agents": n_agents, "mean_update_ms": mean_ms, "mean_fps": mean_fps})

    df_out = pd.DataFrame(rows).sort_values("n_agents")
    df_out.to_csv(OUTPUT_CSV, index=False)
    print(f"\n✅ Saved {len(rows)} entries to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
