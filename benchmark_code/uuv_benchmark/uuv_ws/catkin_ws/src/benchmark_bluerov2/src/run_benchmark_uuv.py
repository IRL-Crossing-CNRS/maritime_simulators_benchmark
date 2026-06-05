#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 IRL Crossing
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0
#
"""
@file run_benchmark_uuv.py
@author IRL Crossing

@brief Automated BlueROV2 Simulation Benchmark Runner for UUVSim

@note Launches a complete underwater simulation, spawns multiple ROVs,
collects real-time factor (RTF) metrics through the BenchmarkSubscriber,
and saves the results as a CSV file.

@details
This script automates a full benchmarking cycle in UUVSim by:
    1. Launching the Gazebo underwater world via roslaunch.
    2. Spawning a specified number of BlueROV2 vehicles.
    3. Running a ROS subscriber (BenchmarkSubscriber) to collect the simulator’s Real-Time Factor (RTF) from /gazebo/performance_metrics.
    4. Logging RTF samples for a fixed duration.
    5. Saving the collected data and mean RTF to a CSV file.

Inputs:
    - num_rovs: number of BlueROV2 vehicles to spawn (hardcoded: 5)
    - sim_duration: duration of data collection in seconds (hardcoded: 500)
    - Gazebo world launched through "uuv_gazebo_worlds/empty_underwater_world.launch"

Outputs:
    - benchmark_output/benchmark_rtf.csv
        Contains all RTF samples and the computed mean RTF.

Notes:
    - Requires the BenchmarkSubscriber class from benchmark_subscriber.py
    - All processes are automatically terminated on completion or error.

@version 0.1
@date 2025-10-22
"""

import rospy
import subprocess
import time
import os
import traceback
from benchmark_subscriber import BenchmarkSubscriber

def main():
    try:
        # Initialize the ROS node (needed for subscriber to work)
        rospy.init_node('benchmark_main', anonymous=True)

        num_rovs = 50
        sim_duration = 300 # seconds
        output_dir = "benchmark_output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Start Gazebo
        print("Launching Gazebo world...")
        gz_proc = subprocess.Popen(["roslaunch", "uuv_gazebo_worlds", "empty_underwater_world.launch", "gui:=false"])
        time.sleep(10)

        # Spawn ROVs
        print("Spawning {} ROVs...".format(num_rovs))
        subprocess.Popen(["rosrun", "benchmark_bluerov2", "spawn_multiple_rovs.py", str(num_rovs)])
        time.sleep(10)

        # Start the benchmark subscriber
        print("Starting RTF benchmark subscriber...")
        benchmark = BenchmarkSubscriber()
        time.sleep(1)  # <-- give time to register subscriber

        # Collect RTF over time
        print("Collecting metrics for {} seconds...".format(sim_duration))
        start_time = time.time()
        while time.time() - start_time < sim_duration and not rospy.is_shutdown():
            time.sleep(0.1)

        # Save results
        csv_path = os.path.join(output_dir, "benchmark_rtf.csv")
        print("Saving benchmark data to:", csv_path)
        benchmark.save_to_csv(csv_path)
        print("Benchmark data saved successfully.")

    except Exception as e:
        print("Exception occurred in benchmark script!")
        print(traceback.format_exc())  # Full error trace

    finally:
        print("Shutting down simulation...")
        rospy.signal_shutdown("Benchmark finished.")
        try:
            gz_proc.terminate()
        except:
            pass
        print("Benchmark completed.")

if __name__ == '__main__':
    main()
