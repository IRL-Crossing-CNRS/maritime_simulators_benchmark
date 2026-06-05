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
@file process_lrauvsim.py
@author IRL Crossing

@brief Process LRAUVSim raw benchmark data into a summary CSV.

@details
Reads per-agent raw CSVs from data/lrauvsim/<n_agents>/real_update.csv,
computes the mean physics update time in milliseconds (excluding warmup zeros),
and writes the summary to data/LRAUVSim_results.csv.

Inputs:
    - data/lrauvsim/<n_agents>/real_update.csv
      Columns: SimTime, RealUpdateDuration (seconds)

Outputs:
    - data/LRAUVSim_results.csv  (n_agents, mean_update_ms)
"""

import os
import pandas as pd
import numpy as np

DATA_DIR = os.path.join("data", "lrauvsim")
OUTPUT_CSV = os.path.join("data", "LRAUVSim_results.csv")


def compute_mean_update(csv_path):
    """Return mean update duration in ms, skipping zero warmup rows."""
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    valid = df[df["RealUpdateDuration"] > 0]["RealUpdateDuration"]
    return round(float(valid.mean() * 1000), 6)


def main():
    rows = []
    for folder in sorted(os.listdir(DATA_DIR), key=lambda x: int(x) if x.isdigit() else float("inf")):
        if not folder.isdigit():
            continue
        n_agents = int(folder)
        csv_path = os.path.join(DATA_DIR, folder, "real_update.csv")
        if not os.path.isfile(csv_path):
            print(f"⚠️  Missing: {csv_path}")
            continue
        mean_ms = compute_mean_update(csv_path)
        print(f"  {n_agents:3d} agents → {mean_ms:.2f} ms")
        rows.append({"n_agents": n_agents, "mean_update_ms": mean_ms})

    df_out = pd.DataFrame(rows).sort_values("n_agents")
    df_out.to_csv(OUTPUT_CSV, index=False)
    print(f"\n✅ Saved {len(rows)} entries to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
