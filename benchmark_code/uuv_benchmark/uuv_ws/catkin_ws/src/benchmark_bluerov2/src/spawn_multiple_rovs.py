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
@file spawn_multiple_rovs.py
@author IRL Crossing

@brief Randomized BlueROV Spawner for Gazebo/ROS.

@note Spawns a specified number of BlueROV2 vehicles into the simulation,
each with a unique namespace and a randomly generated underwater pose.

@details
Functionality:
    - Initializes a ROS node and parses the desired number of ROVs from command-line arguments.
    - For each ROV, generates a random (x, y, z) pose within predefined ranges:
          * x ∈ [-50, 50] meters
          * y ∈ [-50, 50] meters
          * z ∈ [-45, -40] meters (depth)
    - Launches each vehicle via roslaunch:
          roslaunch bluerov2_description upload_bluerov2.launch
              namespace:=<rov_name>
              x:=<value>  y:=<value>  z:=<value>
    - Ensures a short delay between spawns to allow Gazebo/ROS to load each vehicle.
    - Keeps the script alive with rospy.spin() to maintain node activity.

Inputs:
    - Command line argument: <num_rovs>  (integer)
    - No external data files required.

Outputs:
    - Spawns BlueROV2 models in the running Gazebo simulation.
    - Logs to ROS console:
         * Spawn progress
         * Errors such as incorrect arguments

Usage Example:
    rosrun benchmark_bluerov2 spawn_multiple_rovs.py 5

@version 0.1
@date 2025-10-22
"""

import rospy
import subprocess
import time
import random
import sys

def launch_rov(namespace, x, y, z):
    """
    Launch a BlueROV with a specific namespace and pose.
    """
    # Build the roslaunch command for each ROV using .format()
    launch_command = [
        "roslaunch", 
        "bluerov2_description", 
        "upload_bluerov2.launch", 
        "namespace:={}".format(namespace), 
        "x:={}".format(x), 
        "y:={}".format(y), 
        "z:={}".format(z)
    ]

    # Run the roslaunch command
    subprocess.Popen(launch_command)
    rospy.loginfo("Launched {} at position ({}, {}, {})".format(namespace, x, y, z))

def generate_random_pose():
    """
    Generate random pose for ROV within a defined range.
    """
    x = random.uniform(-50, 50)  # Random X position in range [-50, 50]
    y = random.uniform(-50, 50)  # Random Y position in range [-50, 50]
    z = random.uniform(-45, -40)  # Random Z position in range [-45, -40] m (depth range)
    
    return x, y, z

if __name__ == '__main__':
    try:
        rospy.init_node('launch_random_rovs', anonymous=True)

        # Parse number of ROVs from command-line arguments
        if len(sys.argv) < 2:
            rospy.logerr("Usage: spawn_multiple_rovs.py <num_rovs>")
            sys.exit(1)

        try:
            num_rovs = int(sys.argv[1])
        except ValueError:
            rospy.logerr("num_rovs must be an integer.")
            sys.exit(1)

        rospy.loginfo("Launching {} ROVs with random positions...".format(num_rovs))

        # Launch the specified number of ROVs
        for i in range(num_rovs):
            namespace = "rov{}".format(i+1)
            x, y, z = generate_random_pose()  # Generate random position for each ROV
            launch_rov(namespace, x, y, z)
            time.sleep(2)  # Wait to ensure each ROV is loaded

        rospy.loginfo("All {} ROVs are being launched!".format(num_rovs))
        rospy.spin()

    except rospy.ROSInterruptException:
        pass
