#!/usr/bin/env python3
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
@file benchmark_subscriber.py
@author IRL Crossing

@brief ROS subscriber for collecting Real-Time Factor (RTF) metrics from Gazebo.

@note
This script listens to the `/gazebo/performance_metrics` topic, extracts the
Real-Time Factor (RTF) from incoming `PerformanceMetrics` messages, stores all
received samples in memory, and optionally writes them to a CSV file.

@details
Functionality:
    - Subscribes to: /gazebo/performance_metrics (gazebo_msgs/PerformanceMetrics)
    - Extracts the `real_time_factor` field from each message.
    - Collects all RTF samples in a list.
    - Computes the mean RTF over the collected samples.
    - Exports all raw samples and the computed mean into a CSV file.

Intended Use:
    - Useful when benchmarking Gazebo simulation performance.
    - Can be used during robotic experiments to log simulation fidelity and speed.

Inputs:
    - ROS messages from `/gazebo/performance_metrics`.

Outputs:
    - A CSV file containing:
        * The full list of RTF samples
        * The computed mean RTF

Limitations:
    - Does not process CPU/GPU usage or other metrics from Gazebo.
    - Only collects and saves RTF values.

@version 0.1
@date 2025-10-22
"""

import rospy
from std_msgs.msg import Float64
import csv
from gazebo_msgs.msg import PerformanceMetrics


class BenchmarkSubscriber:
    def __init__(self):
        """Subscribe to /gazebo/performance_metrics and collect RTF samples."""
        self.rtf_samples = []
        rospy.Subscriber('/gazebo/performance_metrics', PerformanceMetrics, self.rtf_callback)
        rospy.loginfo("BenchmarkSubscriber initialized and listening to RTF...")

    def rtf_callback(self, msg):
        """Append the real_time_factor from each incoming PerformanceMetrics message."""
        self.rtf_samples.append(msg.real_time_factor)

    def save_to_csv(self, filepath):
        """Write all collected RTF samples and their mean to a CSV file."""
        if not self.rtf_samples:
            print("No RTF samples collected.")
            return

        mean_rtf = sum(self.rtf_samples) / len(self.rtf_samples)
        with open(filepath, 'w') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["RTF Samples"])
            for sample in self.rtf_samples:
                writer.writerow([sample])
            writer.writerow([])
            writer.writerow(["Mean RTF", mean_rtf])
        print("RTF data and mean saved to: {}".format(filepath))
