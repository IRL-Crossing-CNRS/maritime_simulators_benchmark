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
@file repeat_run_uuvsim.py
@brief One repeated UUVSim run (Python 2.7, ROS Melodic), driven by repeat_uuvsim.sh.

Gazebo (repeat_uuvsim.launch) is already running when this node starts. It:
    1. reads the physics actually loaded (/gazebo/get_physics_properties) -> physics.json
    2. applies the 0.5 m/s current (/hydrodynamics/set_current_velocity), as in the README
    3. spawns the BlueROV2 agents exactly as spawn_multiple_rovs.py (one roslaunch of
       upload_bluerov2.launch every 2 s, x, y in U(-50, 50), z in U(-45, -40)), but
       with a fixed seed and the drawn poses written to positions.csv
    4. waits until /gazebo/model_states lists all the agents, plus a margin
    5. measures for --measure-seconds of wall-clock time with every agent present:
       RTF samples from /gazebo/performance_metrics (as benchmark_subscriber.py),
       simulated time from /clock, and the line ranges of ~/.ros/update_times.csv and
       ~/.ros/render_fps.csv written during the window -> window.json

Exit codes: 0 measured, 3 spawn timeout, 4 Gazebo services unavailable.
"""

import argparse
import csv
import json
import os
import random
import re
import subprocess
import sys
import time

import rospy
from gazebo_msgs.msg import ModelStates, PerformanceMetrics
from gazebo_msgs.srv import GetPhysicsProperties

ROV_NAME = re.compile(r"^rov\d+$")


def log(msg):
    sys.stdout.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
    sys.stdout.flush()


def count_lines(path):
    if not os.path.isfile(path):
        return 0
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return n


class Run(object):
    def __init__(self, args):
        self.args = args
        self.n_rovs_seen = 0
        self.measuring = False
        self.rtf_samples = []  # (wall_s, sim_s, rtf)
        rospy.Subscriber("/gazebo/model_states", ModelStates, self.on_states, queue_size=1)
        rospy.Subscriber("/gazebo/performance_metrics", PerformanceMetrics, self.on_metrics)

    def on_states(self, msg):
        self.n_rovs_seen = sum(1 for name in msg.name if ROV_NAME.match(name))

    def on_metrics(self, msg):
        if self.measuring:
            self.rtf_samples.append((time.time(), rospy.get_time(), msg.real_time_factor))

    def physics(self):
        try:
            rospy.wait_for_service("/gazebo/get_physics_properties", timeout=60)
            p = rospy.ServiceProxy("/gazebo/get_physics_properties", GetPhysicsProperties)()
        except Exception as e:
            log("ERROR: /gazebo/get_physics_properties unavailable: %s" % e)
            sys.exit(4)
        info = {"time_step": p.time_step, "max_update_rate": p.max_update_rate, "pause": p.pause}
        with open(os.path.join(self.args.out_dir, "physics.json"), "w") as f:
            json.dump(info, f, indent=2)
        log("PHYSICS time_step=%r max_update_rate=%r" % (p.time_step, p.max_update_rate))

    def current(self):
        # Same call as Terminal 3 of the README.
        cmd = ["rosservice", "call", "/hydrodynamics/set_current_velocity",
               "velocity: %s\nhorizontal_angle: 0.0\nvertical_angle: 0.0" % self.args.current]
        try:
            rospy.wait_for_service("/hydrodynamics/set_current_velocity", timeout=60)
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        except Exception as e:
            log("ERROR: could not set the current: %s" % e)
            sys.exit(4)
        ok = "True" in out
        with open(os.path.join(self.args.out_dir, "current.txt"), "w") as f:
            f.write("velocity %s m/s, horizontal_angle 0, vertical_angle 0\n%s" % (self.args.current, out))
        log("CURRENT %s m/s set: %s" % (self.args.current, "success" if ok else out.strip()))
        if not ok:
            sys.exit(4)

    def spawn(self):
        rng = random.Random(self.args.seed)
        path = os.path.join(self.args.out_dir, "positions.csv")
        t0 = time.time()
        with open(path, "w") as f:
            w = csv.writer(f)
            w.writerow(["namespace", "x", "y", "z", "launch_wall_s"])
            for i in range(self.args.agents):
                ns = "rov%d" % (i + 1)
                x, y, z = rng.uniform(-50, 50), rng.uniform(-50, 50), rng.uniform(-45, -40)
                subprocess.Popen(["roslaunch", "bluerov2_description", "upload_bluerov2.launch",
                                  "namespace:=%s" % ns, "x:=%s" % x, "y:=%s" % y, "z:=%s" % z])
                w.writerow([ns, x, y, z, "%.3f" % (time.time() - t0)])
                f.flush()
                if (i + 1) % 10 == 0 or i + 1 == self.args.agents:
                    log("spawn: %d/%d launched, %d in Gazebo" % (i + 1, self.args.agents, self.n_rovs_seen))
                time.sleep(self.args.spawn_pace)
        deadline = t0 + self.args.spawn_timeout
        last = -1
        while self.n_rovs_seen < self.args.agents and not rospy.is_shutdown():
            if time.time() > deadline:
                log("ERROR: spawn timeout, %d/%d agents in Gazebo after %.0f s"
                    % (self.n_rovs_seen, self.args.agents, time.time() - t0))
                sys.exit(3)
            if self.n_rovs_seen != last:
                last = self.n_rovs_seen
                log("waiting for agents: %d/%d in Gazebo" % (last, self.args.agents))
            time.sleep(0.5)
        spawn_s = time.time() - t0
        log("SPAWN COMPLETE %d agents in %.1f s" % (self.n_rovs_seen, spawn_s))
        return spawn_s

    def measure(self, spawn_s):
        a = self.args
        log("margin of %d s before the measure" % a.margin)
        time.sleep(a.margin)
        w0, s0 = time.time(), rospy.get_time()
        u0, f0 = count_lines(a.update_times), count_lines(a.render_fps)
        n0 = self.n_rovs_seen
        self.measuring = True
        log("Starting measurement (%d s, %d agents)" % (a.measure_seconds, n0))
        next_beat = 60
        while time.time() - w0 < a.measure_seconds and not rospy.is_shutdown():
            time.sleep(0.1)
            if time.time() - w0 >= next_beat:
                log("measure: %d/%d s, sim time +%.1f s" % (next_beat, a.measure_seconds, rospy.get_time() - s0))
                next_beat += 60
        self.measuring = False
        w1, s1 = time.time(), rospy.get_time()
        u1, f1 = count_lines(a.update_times), count_lines(a.render_fps)
        window = {
            "agents_requested": a.agents, "agents_at_start": n0, "agents_at_end": self.n_rovs_seen,
            "seed": a.seed, "spawn_seconds": round(spawn_s, 3), "margin_seconds": a.margin,
            "wall_start": w0, "wall_end": w1, "wall_seconds": w1 - w0,
            "sim_start": s0, "sim_end": s1, "sim_seconds": s1 - s0,
            # update_times.csv / render_fps.csv: 1-based line numbers (header = line 1);
            # the window holds the lines (start_line, end_line], i.e. written during it.
            "update_times_lines": [u0, u1], "render_fps_lines": [f0, f1],
            "rtf_samples": len(self.rtf_samples),
        }
        with open(os.path.join(a.out_dir, "window.json"), "w") as f:
            json.dump(window, f, indent=2)
        with open(os.path.join(a.out_dir, "rtf_samples.csv"), "w") as f:
            wr = csv.writer(f)
            wr.writerow(["wall_s", "sim_s", "rtf"])
            for row in self.rtf_samples:
                wr.writerow(["%.6f" % row[0], "%.6f" % row[1], repr(row[2])])
        # Same format as benchmark_rtf.csv of the reference (benchmark_subscriber.py).
        with open(os.path.join(a.out_dir, "benchmark_rtf.csv"), "w") as f:
            wr = csv.writer(f)
            wr.writerow(["RTF Samples"])
            for row in self.rtf_samples:
                wr.writerow([row[2]])
            wr.writerow([])
            if self.rtf_samples:
                wr.writerow(["Mean RTF", sum(r[2] for r in self.rtf_samples) / len(self.rtf_samples)])
        log("Measurement complete: wall %.1f s, sim %.1f s, %d update steps, %d RTF samples, %d agents"
            % (w1 - w0, s1 - s0, u1 - u0, len(self.rtf_samples), self.n_rovs_seen))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--measure-seconds", type=float, default=300)
    ap.add_argument("--margin", type=float, default=10)
    ap.add_argument("--spawn-pace", type=float, default=2.0)
    ap.add_argument("--spawn-timeout", type=float, default=0)
    ap.add_argument("--current", type=float, default=0.5)
    ap.add_argument("--update-times", default=os.path.expanduser("~/.ros/update_times.csv"))
    ap.add_argument("--render-fps", default=os.path.expanduser("~/.ros/render_fps.csv"))
    args = ap.parse_args(rospy.myargv()[1:])
    if args.spawn_timeout <= 0:
        args.spawn_timeout = args.agents * args.spawn_pace + 180
    rospy.init_node("uuvsim_repeat_run", anonymous=True, disable_signals=True)
    run = Run(args)
    run.physics()
    run.current()
    spawn_s = run.spawn()
    run.measure(spawn_s)


if __name__ == "__main__":
    main()
