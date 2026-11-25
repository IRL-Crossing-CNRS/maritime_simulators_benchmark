#!/usr/bin/env bash
# Repeats the UUVSim reference points, REPEATS independent runs each, and flags
# every run that departs from the reference as soon as it finishes.
# Protocol and outputs follow the HoloOcean, LRAUVSim and Stonefish repeats.
#
# Points (protocol, agents) and what is checked (reference values in brackets):
#   A 150   mean step <= 200 ms + 2 %                       [16.2 ms]
#   A 162   reference ceiling: holds the budget or crashes on memory as in
#           the reference ("memory crash at 162 agents")   [82.1 ms, crash]
#   B 150   mean step <= 30.3 ms + 2 %                      [16.2 ms]
#   B 162   next size: exceeds the budget or crashes        [82.1 ms, crash]
#   C 1     RTF peak, rendering ON, within ±TOL %           [189.0x]
#   D 1     RTF peak, headless, within ±TOL %               [215.0x]
#   D 35    RTF > 2x in every run (max_agents > 2x = 35)    [2.25x]
#   D 40    next size: RTF <= 2x                            [1.85x]
# A and B pass on the protocol rule: mean World::Update() duration <= budget
# + 2 %. The RTF does not enter the verdict (a real step lasts 12-17 % longer
# than its Update(), so RTF ~0.87 at the ceiling is expected); it is reported.
# Only simulated / wall time above 1.02 flags a run invalid (RTF cap not applied).
# Every run checks that Gazebo loaded the step and update rate of the protocol.
#
# SMOKE TEST FIRST: SMOKE=1 ./repeat_uuvsim.sh runs B with 2 agents and D with
# 1 agent, 1 run each, 20 s of measure, then the Python 3 statistics (≈ 3 min).
# It checks spawn, measure window, CSV slicing, kills and get_physics_properties
# before leaving the 6 h campaign unattended.
#
# Every agent is spawned BEFORE the measure: the script waits until
# /gazebo/model_states lists all of them, adds MARGIN_SECONDS, then measures
# MEASURE_SECONDS of wall-clock time. Every process (roscore, roslaunch, gzserver,
# gzclient, ROS nodes) is killed and checked gone between two runs.
#
# Run it YOURSELF from the graphical session, network off, no other application
# open (close editors and browsers first). Nothing here needs the network.
#
# Usage:
#   ./repeat_uuvsim.sh                      all points (A B C D)
#   ./repeat_uuvsim.sh B D                  only some protocols
#   RESULTS_DIR=<dir> ./repeat_uuvsim.sh    resume a campaign (finished runs are kept)
#
# Environment overrides: SMOKE, CATKIN_WS, REPEATS, TOL (%), MEASURE_SECONDS,
# MARGIN_SECONDS, SPAWN_PACE, COOLDOWN, CURRENT, B_BUDGET_MS

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$SCRIPT_DIR/../.." && pwd)
REPEAT_DIR=$SCRIPT_DIR/repeats

SMOKE=${SMOKE:-0}
if [ "$SMOKE" = 1 ]; then
    REPEATS=${REPEATS:-1} MEASURE_SECONDS=${MEASURE_SECONDS:-20} COOLDOWN=${COOLDOWN:-5}
    RESULTS_DIR=${RESULTS_DIR:-$HOME/uuvsim_smoke/$(date +%Y%m%d_%H%M%S)}
fi
CATKIN_WS=${CATKIN_WS:-$SCRIPT_DIR/uuv_ws/catkin_ws}
PROCESS=${PROCESS:-$REPO/benchmark_results/gazebo_based/src/benchmark_results/benchmark_bluerov/process_uuvsim_repeats.py}
REPEATS=${REPEATS:-5}
TOL=${TOL:-10}
MEASURE_SECONDS=${MEASURE_SECONDS:-300}
MARGIN_SECONDS=${MARGIN_SECONDS:-10}
SPAWN_PACE=${SPAWN_PACE:-2}          # s between two agents, as spawn_multiple_rovs.py
COOLDOWN=${COOLDOWN:-15}             # s of idle machine between two runs
CURRENT=${CURRENT:-0.5}              # m/s, README terminal 3
RESULTS_DIR=${RESULTS_DIR:-$HOME/uuvsim_repeats/$(date +%Y%m%d_%H%M%S)}
REF_DRIVER=570.133.07
STEP_MARGIN=1.02
RT_TOL=0.02
# Budget of B: 1/33 s = 30.303 ms, the base used by the Stonefish and HoloOcean
# repeats (limit 30.91 ms). With dt = 0.03 s the strict base would be 30 ms
# (limit 30.6 ms): B_BUDGET_MS=30 ./repeat_uuvsim.sh. No reference verdict
# changes (B 150 ≈ 16 ms, B 162 ≈ 82 ms in the reference).
B_BUDGET_MS=${B_BUDGET_MS:-30.303030}

# protocol agents check [rtf_floor]
ALL_POINTS=(
    "A 150 realtime"
    "A 162 ceiling"
    "B 150 realtime"
    "B 162 over"
    "C 1 rtf"
    "D 1 rtf"
    "D 35 rtf 2"
    "D 40 below 2"
)

if [ "$SMOKE" = 1 ]; then
    ALL_POINTS=("B 2 realtime" "D 1 rtf")
fi
# SWEEP="125 130 132 133 135" (protocol SWEEP_PROTOCOL, default A): one probe run
# per size, in increasing order; at the first size that fails (budget or crash)
# the sweep stops and REPEATS runs are made at the last passing size (check
# realtime) and at the failing size (check over). The probe run counts as run 1.
# SWEEPS="A:130 135 140;B:30 40 50 60" chains several sweeps, one per protocol,
# then the regular points of the protocols given as arguments (e.g. C D).
SWEEP=${SWEEP:-}
SWEEP_PROTOCOL=${SWEEP_PROTOCOL:-A}
SWEEPS=${SWEEPS:-}
[ -n "$SWEEP" ] && SWEEPS="${SWEEPS:+$SWEEPS;}$SWEEP_PROTOCOL:$SWEEP"
SWEEP_MAX=${SWEEP_MAX:-250}  # while every size passes, the sweep goes on by the last step, up to this size
SWEEP_NEXT=${SWEEP_NEXT:-0}   # 1: also REPEATS fresh runs at the failing size
# POINTS="A 130 probe;A 135 probe" replaces the list above. Checks: realtime (must
# hold the budget), probe (reports PASS / FAIL only, to look for a ceiling),
# ceiling, over, rtf, below.
if [ -n "${POINTS:-}" ]; then
    IFS=';' read -r -a ALL_POINTS <<< "$POINTS"
fi

PROTOCOLS=("$@")
if [ ${#PROTOCOLS[@]} -eq 0 ]; then
    [ "$SMOKE" = 1 ] && PROTOCOLS=(B D) || PROTOCOLS=(A B C D)
fi
SWEPT=()
if [ -n "$SWEEPS" ]; then
    IFS=';' read -r -a SWEEP_LIST <<< "$SWEEPS"
    for sw in "${SWEEP_LIST[@]}"; do SWEPT+=("${sw%%:*}"); done
    # protocols on the command line get their regular points after the sweeps
    [ $# -eq 0 ] && REGULAR=() || REGULAR=("$@")
    PROTOCOLS=("${SWEPT[@]}" "${REGULAR[@]}")
fi

if [ -t 1 ]; then
    RED=$'\e[1;97;41m' YEL=$'\e[1;30;43m' GRN=$'\e[1;32m' BLD=$'\e[1m' RST=$'\e[0m'
else
    RED='' YEL='' GRN='' BLD='' RST=''
fi

protocol_name() {
    case $1 in
        A) echo A-human-loop ;;  B) echo B-control ;;  C) echo C-ftrt-render ;;  D) echo D-ai-headless ;;
        *) return 1 ;;
    esac
}
budget_ms()   { [ "$1" = A ] && echo 200 || echo "$B_BUDGET_MS"; }
world_of()    { case $1 in A) echo "$REPEAT_DIR/worlds/empty_underwater_A.world" ;;
                           B) echo "$REPEAT_DIR/worlds/empty_underwater_B.world" ;;
                           *) echo "$REPEAT_DIR/worlds/empty_underwater_CD.world" ;; esac; }
gui_of()      { [ "$1" = D ] && echo false || echo true; }
# expected <time_step> <max_update_rate> as loaded by Gazebo
physics_of()  { case $1 in A) echo "0.2 5" ;; B) echo "0.03 33.333" ;; *) echo "0.03 0" ;; esac; }
reference_of() {
    case "$1 $2" in
        "A 150"|"B 150") echo 16.20 ;;  "A 162"|"B 162") echo 82.10 ;;
        "C 1") echo 189.01 ;;  "C 30") echo 2.63 ;;  "C 35") echo 2.11 ;;  "D 1") echo 214.98 ;;  "D 35") echo 2.25 ;;  "D 40") echo 1.85 ;;
        *) echo - ;;
    esac
}

# ─── Output helpers ───────────────────────────────────────────────────────────

say() {
    printf '%s\n' "$*"
    printf '%s\n' "$*" | sed 's/\x1b\[[0-9;]*m//g' >> "$RESULTS_DIR/campaign.log"
}

fmt_duration() {
    local s=$1
    if [ "$s" -ge 3600 ]; then printf '%d h %02d min' $((s / 3600)) $((s % 3600 / 60))
    elif [ "$s" -ge 60 ]; then printf '%d min %02d s' $((s / 60)) $((s % 60))
    else printf '%d s' "$s"; fi
}

pct() { awk -v g="$1" -v r="$2" 'BEGIN { if (r + 0 == 0 || g == "-") print "n/a"; else printf "%+.1f", (g - r) / r * 100 }'; }
gt()  { awk -v a="$1" -v b="$2" 'BEGIN { exit !(a + 0 > b + 0) }'; }

# alert <OK|DEVIATION|CONTRADICTS> <title> <message>
alert() {
    case $1 in
        OK)          say "${GRN}  ✔ $2${RST}: $3" ;;
        DEVIATION)   printf '\a'
                     say "${YEL}  ⚠ DEVIATION FROM THE REFERENCE — $2 ${RST}"
                     say "${YEL}    $3 ${RST}" ;;
        CONTRADICTS) printf '\a\a\a'
                     say "${RED}  ✖ CONTRADICTS THE REFERENCE — $2 ${RST}"
                     say "${RED}    $3 ${RST}" ;;
    esac
}

N_OK=0 N_DIFF=0 N_BAD=0 N_RUN_ALERTS=0
REPORT=()

print_report() {
    say ""
    say "${BLD}══════════════════════════════════ SUMMARY ══════════════════════════════════${RST}"
    local line
    for line in "${REPORT[@]}"; do say "$line"; done
    say ""
    say "  points matching the reference: $N_OK    deviating: $N_DIFF    contradicting: $N_BAD"
    say "  runs flagged during the campaign: $N_RUN_ALERTS"
    say "  results: $RESULTS_DIR"
    if [ "$N_BAD" -gt 0 ]; then
        say "${RED}  $N_BAD point(s) contradict the reference ${RST}"
    elif [ "$N_DIFF" -gt 0 ]; then
        say "${YEL}  $N_DIFF point(s) deviate from the reference ${RST}"
    else
        say "${GRN}  Every repeated point matches the reference.${RST}"
    fi
}

# ─── ROS environment (README §2.4 step 4) ─────────────────────────────────────

set +u
# shellcheck disable=SC1091
source /opt/ros/melodic/setup.bash
# shellcheck disable=SC1091
[ -f /usr/local/share/gazebo/setup.sh ] && source /usr/local/share/gazebo/setup.sh
# shellcheck disable=SC1091
source "$CATKIN_WS/devel/setup.bash"
set -u
export CMAKE_PREFIX_PATH=/usr/local:${CMAKE_PREFIX_PATH:-}
export LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH:-}
export PATH=/usr/local/bin:$PATH
export ROS_HOME=$HOME/.ros
UPDATE_CSV=$ROS_HOME/update_times.csv
FPS_CSV=$ROS_HOME/render_fps.csv

# ─── Process control ──────────────────────────────────────────────────────────

# Everything a run starts. Matched on the command line.
ROS_PATTERNS=(gzserver gzclient roslaunch rosmaster roscore rosout
              "$CATKIN_WS/" /opt/ros/melodic/ repeat_run_uuvsim.py)

ros_leftovers() {
    local p
    for p in "${ROS_PATTERNS[@]}"; do pgrep -f -- "$p"; done 2>/dev/null | sort -u | grep -v "^$$\$"
}

PGIDS=()
SAMPLER_PID=''

# Kills every process of the run and waits until none is left.
kill_ros_stack() {
    local pg i p
    for pg in "${PGIDS[@]}"; do kill -TERM -- "-$pg" 2>/dev/null; done
    for p in "${ROS_PATTERNS[@]}"; do pkill -TERM -f -- "$p" 2>/dev/null; done
    for i in $(seq 1 20); do
        [ -z "$(ros_leftovers)" ] && break
        sleep 1
    done
    if [ -n "$(ros_leftovers)" ]; then
        for pg in "${PGIDS[@]}"; do kill -KILL -- "-$pg" 2>/dev/null; done
        for p in "${ROS_PATTERNS[@]}"; do pkill -KILL -f -- "$p" 2>/dev/null; done
        sleep 3
    fi
    PGIDS=()
    if [ -n "$(ros_leftovers)" ]; then
        stop_campaign "processes still alive after kill -9: $(ros_leftovers | xargs -r ps -o pid=,args= -p | head -n 5)"
    fi
}

# Starts "$@" in its own process group (PGID = PID); log to $LOG_TO.
start_group() {
    setsid "$@" >> "$LOG_TO" 2>&1 < /dev/null &
    PGIDS+=($!)
    LAST_PID=$!
}

on_interrupt() {
    [ -n "$SAMPLER_PID" ] && kill "$SAMPLER_PID" 2>/dev/null
    kill_ros_stack
    say ""
    say "${YEL}  Campaign interrupted. To resume without re-running finished runs:${RST}"
    say "    RESULTS_DIR=$RESULTS_DIR $0 ${PROTOCOLS[*]}"
    print_report
    exit 130
}
trap on_interrupt INT TERM

stop_campaign() {
    printf '\a\a\a'
    [ -n "$SAMPLER_PID" ] && kill "$SAMPLER_PID" 2>/dev/null
    say ""
    say "${RED}  CAMPAIGN STOPPED: $1 ${RST}"
    print_report
    exit 2
}

check_alone() {
    local others
    others=$(ros_leftovers | xargs -r ps -o pid=,args= -p | head -n 5)
    [ -z "$others" ] || stop_campaign "ROS / Gazebo processes are already running (never measure two at once):
$others"
}

# ─── Machine state ────────────────────────────────────────────────────────────

PKG_TEMP=$(for z in /sys/class/thermal/thermal_zone*; do
    [ "$(cat "$z/type" 2>/dev/null)" = x86_pkg_temp ] && echo "$z/temp"; done | head -n 1)
BAT_STATUS=$(ls /sys/class/power_supply/BAT*/status 2>/dev/null | head -n 1)

# Samples the machine every 0.2 s into $1 until killed: fastest core clock, CPU
# package temperature, battery status, available memory (162 agents crash on
# memory in the reference) and the phase of the run read from its log $2.
sample_machine() {
    # gz_fds / gz_rss_mb: open file descriptors and resident memory of gzserver
    # (limit: gz_fd_limit), to tell a descriptor exhaustion from a memory crash.
    echo "time_s,max_core_mhz,pkg_temp_c,battery,mem_available_mb,gz_fds,gz_fd_limit,gz_rss_mb,phase" > "$1"
    local phase=setup f mem gz fds lim rss
    while :; do
        case $phase in
            setup)   grep -q 'spawn:' "$2" 2>/dev/null && phase=spawn ;;
            spawn)   grep -q 'Starting measurement' "$2" 2>/dev/null && phase=measure ;;
            measure) grep -q 'Measurement complete' "$2" 2>/dev/null && phase=end ;;
        esac
        f=$(sort -n /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq 2>/dev/null | tail -n 1)
        mem=$(awk '/^MemAvailable:/ { print int($2 / 1024) }' /proc/meminfo)
        # the real binary, not the gazebo_ros "gzserver" shell wrapper (same name)
        gz='' fds=0 lim=0 rss=0
        for q in $(pgrep -x gzserver); do
            case $(readlink /proc/"$q"/exe 2>/dev/null) in *gzserver*) gz=$q ;; esac
        done
        if [ -n "$gz" ]; then
            fds=$(ls /proc/"$gz"/fd 2>/dev/null | wc -l)
            lim=$(awk '/^Max open files/ { print $4 }' /proc/"$gz"/limits 2>/dev/null)
            rss=$(awk '/^VmRSS:/ { print int($2 / 1024) }' /proc/"$gz"/status 2>/dev/null)
        fi
        echo "$(date +%s.%N | cut -c1-14),$((${f:-0} / 1000)),$(( $(cat "$PKG_TEMP" 2>/dev/null || echo 0) / 1000 )),$(cat "$BAT_STATUS" 2>/dev/null || echo none),$mem,${fds:-0},${lim:-0},${rss:-0},$phase" >> "$1"
        sleep 0.2
    done
}

# ─── One benchmark run ────────────────────────────────────────────────────────

wait_for() {  # wait_for <seconds> <command...>: true once the command succeeds
    local t=$1; shift
    local i
    for i in $(seq 1 "$t"); do "$@" > /dev/null 2>&1 && return 0; sleep 1; done
    return 1
}

# run_once <dir> <protocol> <agents> <seed>; leaves "key=value ..." in $ROW
run_once() {
    local dir=$1 p=$2 n=$3 seed=$4
    if [ -f "$dir/status.txt" ] && [ -f "$dir/metrics.txt" ]; then
        say "  (run already finished in this campaign, kept: $(cat "$dir/status.txt"))"
        ROW=$(cat "$dir/metrics.txt")
        return
    fi
    check_alone
    rm -rf "$dir"
    mkdir -p "$dir"
    rm -f "$UPDATE_CSV" "$FPS_CSV"

    local log="$dir/run.log" world gui
    world=$(world_of "$p") gui=$(gui_of "$p")
    : > "$log"
    export ROS_LOG_DIR="$dir/ros_log"
    sample_machine "$dir/machine.csv" "$log" &
    SAMPLER_PID=$!
    local start=$SECONDS status=''

    LOG_TO="$dir/roscore.log" start_group roscore
    if ! wait_for 30 rostopic list; then status=setup_no_roscore; fi

    if [ -z "$status" ]; then
        LOG_TO="$dir/launch.log" start_group roslaunch "$REPEAT_DIR/repeat_uuvsim.launch" "world:=$world" "gui:=$gui"
        wait_for 60 pgrep -x gzserver || status=setup_no_gzserver
        if [ -z "$status" ] && [ "$gui" = true ]; then
            wait_for 60 pgrep -x gzclient || status=setup_no_gzclient
        fi
    fi

    local node_pid='' rc=0 gui_lost=0 window_done=0
    if [ -z "$status" ]; then
        local spawn_timeout=$(( n * SPAWN_PACE + 180 ))
        local run_timeout=$(( spawn_timeout + MARGIN_SECONDS + MEASURE_SECONDS + 180 ))
        LOG_TO="$log" start_group stdbuf -oL -eL python "$REPEAT_DIR/repeat_run_uuvsim.py" \
            --agents "$n" --seed "$seed" --out-dir "$dir" --measure-seconds "$MEASURE_SECONDS" \
            --margin "$MARGIN_SECONDS" --spawn-pace "$SPAWN_PACE" --spawn-timeout "$spawn_timeout" \
            --current "$CURRENT" --update-times "$UPDATE_CSV" --render-fps "$FPS_CSV"
        node_pid=$LAST_PID
        tail -n +1 -f --pid="$node_pid" "$log" 2>/dev/null \
            | grep --line-buffered -E 'PHYSICS|CURRENT|launched|SPAWN|Starting|measure:|complete|ERROR' \
            | sed -u 's/^/    /' &
        local tail_pid=$! next_beat=60
        while kill -0 "$node_pid" 2>/dev/null; do
            sleep 2
            local el=$((SECONDS - start))
            if ! pgrep -x gzserver > /dev/null; then
                if grep -q 'Starting measurement' "$log"; then status=crash_measure; else status=crash_spawn; fi
                echo "gzserver died after $el s of run ($status)" > "$dir/crash.txt"
                tail -n 40 "$dir/launch.log" >> "$dir/crash.txt" 2>/dev/null
                say "    gzserver died after $(fmt_duration "$el") ($status)"
                kill -TERM -- "-$node_pid" 2>/dev/null
                break
            fi
            if [ "$gui" = true ] && ! pgrep -x gzclient > /dev/null && [ "$gui_lost" = 0 ]; then
                gui_lost=1
                say "    gzclient (rendering window) closed during the run: rendering condition lost"
            fi
            if [ "$window_done" = 0 ] && [ "$gui" = true ] && grep -q 'Starting measurement' "$log"; then
                window_done=1
                { xrandr 2>/dev/null | grep -E '\*|connected primary'
                  xwininfo -name Gazebo 2>/dev/null | grep -E 'Absolute|Width|Height|Map State'; } \
                    > "$dir/gzclient_window.txt"
            fi
            if [ "$el" -ge "$run_timeout" ]; then
                status=timeout_${run_timeout}s
                kill -TERM -- "-$node_pid" 2>/dev/null
                break
            fi
            if [ "$el" -ge "$next_beat" ]; then
                say "    … running for $(fmt_duration "$el") (expected ≈ $(fmt_duration "$RUN_EST"))"
                next_beat=$((next_beat + 60))
            fi
        done
        wait "$node_pid" 2>/dev/null
        rc=$?
        wait "$tail_pid" 2>/dev/null
        if [ -z "$status" ]; then
            case $rc in
                0) [ -f "$dir/window.json" ] && status=ok || status=no_result ;;
                3) status=spawn_timeout ;;
                4) status=setup_gazebo_services ;;
                *) status=no_result_rc_$rc ;;
            esac
        fi
        [ "$status" = ok ] && [ "$gui_lost" = 1 ] && status=gui_lost
    fi

    kill "$SAMPLER_PID" 2>/dev/null
    wait "$SAMPLER_PID" 2>/dev/null
    SAMPLER_PID=''
    kill_ros_stack
    # gzserver / gzclient are gone: their CSVs are closed and complete.
    [ -f "$UPDATE_CSV" ] && mv "$UPDATE_CSV" "$dir/update_times.csv"
    [ -f "$FPS_CSV" ] && mv "$FPS_CSV" "$dir/render_fps.csv"
    echo "$status" > "$dir/status.txt"
    ROW=$(python3 -I "$PROCESS" run "$dir" --protocol "$p")
    echo "$ROW" > "$dir/metrics.txt"

    # Setup failures are not measurements: stop rather than record them.
    case $status in setup_*) stop_campaign "run could not start ($status), see $dir" ;; esac
    # Gazebo must have loaded the step and update rate of the protocol.
    local exp_dt exp_rate got_dt got_rate
    read -r exp_dt exp_rate <<< "$(physics_of "$p")"
    got_dt=$(field time_step) got_rate=$(field max_update_rate)
    if [ "$got_dt" != - ] && ! awk -v a="$got_dt" -v b="$exp_dt" -v c="$got_rate" -v d="$exp_rate" \
            'BEGIN { exit !((a - b < 1e-6 && b - a < 1e-6) && (c - d < 1e-3 && d - c < 1e-3)) }'; then
        stop_campaign "Gazebo loaded time_step=$got_dt max_update_rate=$got_rate, protocol $p needs $exp_dt / $exp_rate (world $(world_of "$p"))"
    fi
    say "    cooldown ${COOLDOWN} s"
    sleep "$COOLDOWN"
}

field() { sed -n "s/.*\\b$1=\\([^ ]*\\).*/\\1/p" <<< "$ROW"; }

estimate_seconds() {  # startup + spawn + settle + margin + measure + cleanup/cooldown
    echo $(( 25 + $1 * SPAWN_PACE + 10 + MARGIN_SECONDS + MEASURE_SECONDS + 25 + COOLDOWN ))
}

# ─── Statistics ───────────────────────────────────────────────────────────────

stats() {  # one value per line -> "n mean ci95 min max" (Student t, n-1 dof)
    awk 'NF {
            v[++n] = $1; s += $1
            if (n == 1 || $1 < lo) lo = $1
            if (n == 1 || $1 > hi) hi = $1
        }
        END {
            if (n == 0) { print "0 - - - -"; exit }
            m = s / n
            split("12.706 4.303 3.182 2.776 2.571 2.447 2.365 2.306 2.262", t, " ")
            ci = "-"
            if (n > 1) {
                for (i = 1; i <= n; i++) ss += (v[i] - m) ^ 2
                tq = (n - 1 <= 9) ? t[n - 1] : 1.96
                ci = sprintf("%.3f", tq * sqrt(ss / (n - 1)) / sqrt(n))
            }
            printf "%d %.3f %s %.3f %.3f\n", n, m, ci, lo, hi
        }'
}

process_repeats() {
    python3 -I "$PROCESS" summary --repeats-dir "$RESULTS_DIR" --out-dir "$RESULTS_DIR" "$@" 2>&1 \
        | tee -a "$RESULTS_DIR/campaign.log"
}

worst() {  # worst <v1> <v2>
    case "$1 $2" in *CONTRADICTS*) echo CONTRADICTS ;; *DEVIATION*) echo DEVIATION ;; *) echo OK ;; esac
}

# ─── One reference point, repeated ────────────────────────────────────────────

repeat_point() {
    local p=$1 n=$2 check=$3 floor=${4:-}
    local pname; pname=$(protocol_name "$p")
    local ref; ref=$(reference_of "$p" "$n")
    local limit; limit=$(awk -v b="$(budget_ms "$p")" -v m="$STEP_MARGIN" 'BEGIN { printf "%.2f", b * m }')
    local reference
    case $check in
        realtime) reference="mean step ${ref} ms (budget + 2 % = $limit ms)" ;;
        probe)    reference="ceiling search: PASS if mean step ≤ $limit ms and real time" ;;
        ceiling)  reference="mean step ${ref} ms then memory crash (budget + 2 % = $limit ms)" ;;
        over)     reference="ceiling 150: mean step ${ref} ms > $limit ms, memory crash" ;;
        rtf)      reference="RTF ${ref}${floor:+, > ${floor}x}" ;;
        below)    reference="RTF ${ref} ≤ ${floor}x (ceiling 35)" ;;
    esac
    say ""
    say "${BLD}━━━━━━ Protocol $pname — $n agent(s) — $REPEATS runs ━━━━━━${RST}"
    say "  reference: $reference"
    say "  world: $(basename "$(world_of "$p")"), rendering: $( [ "$(gui_of "$p")" = true ] && echo 'gzclient window' || echo headless)"

    local values='' passed=0 k point_verdict=OK
    for k in $(seq 1 "$REPEATS"); do
        RUN_EST=$(estimate_seconds "$n")
        say ""
        say "${BLD}[run $k/$REPEATS — point $POINT_NO/$N_POINTS] $(date +%H:%M) — this run ≈ $(fmt_duration "$RUN_EST"), left ≈ $(fmt_duration "$REMAINING"), done around $(date -d "+$REMAINING seconds" +%H:%M)${RST}"
        run_once "$RESULTS_DIR/protocol_$p/$n/${RUN_PREFIX:-run}$k" "$p" "$n" "$(( ${SEED_OFFSET:-0} + k ))"
        REMAINING=$((REMAINING > RUN_EST ? REMAINING - RUN_EST : 0))

        local status step rtf rtfc agents spawn p95 verdict msg
        status=$(cat "$RESULTS_DIR/protocol_$p/$n/${RUN_PREFIX:-run}$k/status.txt")
        step=$(field mean_step_ms) rtf=$(field mean_rtf) rtfc=$(field rtf_clock)
        agents=$(field agents_end) spawn=$(field spawn_s) p95=$(field p95_ms)
        local title="$p, $n agent(s), run $k/$REPEATS"
        local rt_fast=0 rt_slow=0
        [ "$rtfc" != - ] && awk -v r="$rtfc" -v t="$RT_TOL" 'BEGIN { exit !(r > 1 + t) }' && rt_fast=1
        [ "$rtfc" != - ] && awk -v r="$rtfc" -v t="$RT_TOL" 'BEGIN { exit !(r < 1 - t) }' && rt_slow=1
        local cap_msg="simulated/wall time $rtfc > $(awk -v t="$RT_TOL" 'BEGIN { print 1 + t }'): the RTF cap was not applied (configuration error, run invalid)"
        case $check in
            realtime)
                if [ "$status" != ok ]; then
                    verdict=CONTRADICTS msg="the reference holds $n agents within the budget, this run ended with $status"
                elif [ "$rt_fast" = 1 ]; then
                    verdict=DEVIATION msg="$cap_msg"
                elif gt "$step" "$limit"; then
                    verdict=CONTRADICTS msg="mean step $step ms > $limit ms (budget + 2 %): $n agents do not hold the budget (sim/wall $rtfc)"
                    values+="$step"$'\n'
                else
                    verdict=OK msg="mean step $step ms ≤ $limit ms, real time $rtfc, p95 $p95 ms ($(pct "$step" "$ref")% vs reference $ref ms)"
                    values+="$step"$'\n'
                fi ;;
            probe)
                if [ "$status" != ok ]; then
                    verdict=OK PROBE_PASS=0 PROBE_CRASH=1 msg="CRASH: run ended with $status (ceiling set by a crash, not by the budget)"
                elif [ "$rt_fast" = 1 ]; then
                    verdict=DEVIATION msg="$cap_msg"
                else
                    values+="$step"$'\n'
                    if gt "$step" "$limit"; then
                        verdict=OK PROBE_PASS=0 msg="FAIL: mean step $step ms (limit $limit ms), sim/wall $rtfc, p95 $p95 ms"
                    else
                        verdict=OK PROBE_PASS=1 msg="PASS: mean step $step ms ≤ $limit ms, sim/wall $rtfc, p95 $p95 ms"
                    fi
                fi ;;
            ceiling)
                case $status in
                    ok)  if [ "$rt_fast" = 1 ]; then
                             verdict=DEVIATION msg="$cap_msg"
                         elif gt "$step" "$limit"; then
                             verdict=CONTRADICTS msg="mean step $step ms (limit $limit ms), sim/wall $rtfc: the reference counts $n agents within the budget"
                         else
                             verdict=OK msg="holds the budget: mean step $step ms ≤ $limit ms, real time $rtfc (reference $ref ms before its memory crash)"
                             values+="$step"$'\n'
                         fi ;;
                    crash_*) verdict=OK msg="$status, as the memory crash of the reference at $n agents" ;;
                    *)   verdict=DEVIATION msg="run ended with $status" ;;
                esac ;;
            over)
                case $status in
                    ok)  values+="$step"$'\n'
                         if [ "$rt_fast" = 1 ]; then
                             verdict=DEVIATION msg="$cap_msg"
                         elif gt "$step" "$limit"; then
                             verdict=OK msg="fails as in the reference: mean step $step ms (limit $limit ms), sim/wall $rtfc"
                         else
                             verdict=DEVIATION msg="mean step $step ms ≤ $limit ms: $n agents hold the budget, the reference ceiling is 150"
                         fi ;;
                    crash_*) verdict=OK msg="CRASH ($status): fails by a crash, not by the budget" ;;
                    *)   verdict=DEVIATION msg="run ended with $status" ;;
                esac ;;
            rtf)
                if [ "$status" != ok ]; then
                    verdict=CONTRADICTS msg="$status where the reference reaches RTF $ref"
                else
                    values+="$rtf"$'\n'
                    local diff; diff=$(pct "$rtf" "$ref")
                    if [ -n "$floor" ] && ! gt "$rtf" "$floor"; then
                        verdict=CONTRADICTS msg="RTF $rtf ≤ ${floor}x at $n agents"
                    elif awk -v d="$diff" -v tol="$TOL" 'BEGIN { exit !(d < -tol || d > tol) }'; then
                        verdict=DEVIATION msg="RTF $rtf, ${diff}% from the reference $ref (beyond ±${TOL}%); sim/wall $rtfc"
                    else
                        verdict=OK msg="RTF $rtf, ${diff}% from the reference $ref; sim/wall $rtfc"
                    fi
                fi ;;
            below)
                if [ "$status" != ok ]; then
                    verdict=DEVIATION msg="run ended with $status"
                else
                    values+="$rtf"$'\n'
                    if gt "$rtf" "$floor"; then
                        verdict=DEVIATION msg="RTF $rtf > ${floor}x at $n agents: the reference ceiling (35) is exceeded"
                    else
                        verdict=OK msg="RTF $rtf ≤ ${floor}x ($(pct "$rtf" "$ref")% vs reference $ref)"
                    fi
                fi ;;
        esac
        if [ "$status" = ok ] && [ "$agents" != - ] && [ "$agents" -lt "$n" ] 2>/dev/null; then
            verdict=$(worst "$verdict" DEVIATION) msg+=" — only $agents/$n agents left at the end"
        fi
        [ "$verdict" = OK ] && passed=$((passed + 1)) || N_RUN_ALERTS=$((N_RUN_ALERTS + 1))
        point_verdict=$(worst "$point_verdict" "$verdict")
        alert "$verdict" "$title" "$msg"
        local mhz temp_max battery mem_min
        read -r mhz temp_max battery mem_min <<< "$(python3 -I "$PROCESS" machine "$RESULTS_DIR/protocol_$p/$n/${RUN_PREFIX:-run}$k/machine.csv")"
        say "    gzserver peak: $(awk -F, 'NR > 1 { if ($6 > f) f = $6; if ($8 > r) r = $8; l = $7 } END { printf "%d open files (limit %s), %d MB RSS", f, l, r }' "$RESULTS_DIR/protocol_$p/$n/${RUN_PREFIX:-run}$k/machine.csv")"
        say "    spawn ${spawn} s; machine during the measure: fastest core $mhz MHz (median), CPU ${temp_max} °C max, battery $battery, RAM available ≥ ${mem_min} MB"
        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$pname" "$n" "${RUN_PREFIX:-run}$k" "$status" "$spawn" \
            "$step" "$p95" "$rtf" "$rtfc" "$agents" "$verdict" "$mhz" "$temp_max" "$battery" "$mem_min" \
            >> "$RESULTS_DIR/verdicts_per_run.csv"
    done

    local cnt mean ci lo hi summary
    read -r cnt mean ci lo hi <<< "$(printf '%s' "$values" | stats)"
    local unit=ms; case $check in rtf|below) unit=x ;; esac
    summary="$passed/$REPEATS runs as the reference; mean $mean ± $ci $unit (95 % CI over $cnt runs; min $lo, max $hi); reference $ref $unit"
    if [ "$check" = rtf ] && [ "$cnt" -gt 0 ] && \
        awk -v d="$(pct "$mean" "$ref")" -v tol="$TOL" 'BEGIN { exit !(d < -tol || d > tol) }'; then
        point_verdict=$(worst "$point_verdict" DEVIATION) summary+=" (mean $(pct "$mean" "$ref")%)"
    fi
    case $point_verdict in
        OK) N_OK=$((N_OK + 1)) ;;  DEVIATION) N_DIFF=$((N_DIFF + 1)) ;;  CONTRADICTS) N_BAD=$((N_BAD + 1)) ;;
    esac
    say ""
    alert "$point_verdict" "POINT $p, $n agent(s)" "$summary"
    REPORT+=("$(printf '%-11s %-2s %3s agents  %s' "$point_verdict" "$p" "$n" "$summary")")
    printf '%s,%s,%s,"%s",%s,%s,%s,%s,%s,%s,%s\n' "$pname" "$n" "$check" "$reference" \
        "$REPEATS" "$passed" "$mean" "$ci" "$lo" "$hi" "$point_verdict" \
        >> "$RESULTS_DIR/verdicts_per_point.csv"
    say "  Point statistics (measure window; dispersion ratios with the first 10 % of the steps discarded):"
    process_repeats --point "$p:$n"
}

# ─── Pre-flight ───────────────────────────────────────────────────────────────

for p in "${PROTOCOLS[@]}"; do
    protocol_name "$p" > /dev/null || { echo "Unknown protocol: $p (expected: A B C D)"; exit 1; }
done
for f in "$REPEAT_DIR/repeat_uuvsim.launch" "$REPEAT_DIR/repeat_run_uuvsim.py" "$PROCESS" \
         "$REPEAT_DIR"/worlds/empty_underwater_{A,B,CD}.world; do
    [ -f "$f" ] || { echo "Missing file: $f"; exit 1; }
done
[ "$(command -v gzserver)" = /usr/local/bin/gzserver ] || {
    echo "gzserver is $(command -v gzserver), not the recompiled /usr/local/bin/gzserver (README §2.4):"
    echo "update_times.csv and render_fps.csv would not be written."; exit 1; }
command -v python3 > /dev/null || { echo "python3 is needed for the statistics"; exit 1; }
needs_display=0
[[ " ${PROTOCOLS[*]} " =~ [ABC] ]] && needs_display=1
if [ "$needs_display" = 1 ] && [ -z "${DISPLAY:-}" ]; then
    echo "Protocols A, B and C open the gzclient window: run this script from the graphical session."
    exit 1
fi

mkdir -p "$RESULTS_DIR"

say "${BLD}UUVSim repeated runs — $(date '+%Y-%m-%d %H:%M')${RST}"
[ "$SMOKE" = 1 ] && say "${YEL}  SMOKE TEST: B 2 agents and D 1 agent, $REPEATS run, ${MEASURE_SECONDS} s. Checks the pipeline only, not a measurement. ${RST}"
say "  protocols: ${PROTOCOLS[*]}    $REPEATS runs per point    measure: ${MEASURE_SECONDS} s of wall time, every agent spawned"
say "  A/B: mean Update() ≤ budget + 2 % (RTF reported, not judged)    C/D: RTF flagged beyond ±${TOL}% of the reference"
say "  results:   $RESULTS_DIR"
say ""

check_alone

warn=0
DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n 1)
if [ "$DRIVER" != "$REF_DRIVER" ]; then
    say "${YEL}  NVIDIA driver $DRIVER, the README of the reference states $REF_DRIVER. ${RST}"
    warn=1
fi
for supply in /sys/class/power_supply/*; do
    [ "$(cat "$supply/type" 2>/dev/null)" = Mains ] || continue
    if [ "$(cat "$supply/online" 2>/dev/null)" = 0 ]; then
        say "${RED}  On battery: measurements will be off. Plug in the AC adapter. ${RST}"
        warn=1
    fi
done
if [ "$(cat "$BAT_STATUS" 2>/dev/null)" = Charging ]; then
    say "${YEL}  The battery is charging: wait until it is full, charging can throttle the CPU. ${RST}"
    warn=1
fi
others=$(pgrep -a -f -i -- '(^|/)(code|node|firefox|chrome|chromium|slack|thunderbird|teams|zoom|spotify)( |$)' \
    | head -n 5)
if [ -n "$others" ]; then
    say "${YEL}  Other applications are running (close them before measuring): ${RST}"
    say "$others"
    warn=1
fi
if ip route show default 2>/dev/null | grep -q .; then
    say "${YEL}  The network is still up: disconnect it. ${RST}"
    warn=1
fi
monitors=$(xrandr --listmonitors 2>/dev/null | sed -n 's/^Monitors: //p')
if [ -n "$monitors" ] && [ "$monitors" -gt 1 ]; then
    say "${YEL}  $monitors displays connected: keep only one. ${RST}"
    warn=1
fi
powermizer=$(nvidia-settings -q '[gpu:0]/GpuPowerMizerMode' -t 2>/dev/null | head -n 1)
if [ "${powermizer:-}" != 1 ]; then
    say "${YEL}  NVIDIA PowerMizer mode is \"${powermizer:-unknown}\": set the GPU to performance (nvidia-settings, PowerMizer: Prefer Maximum Performance). ${RST}"
    warn=1
fi
if [ "$warn" = 1 ] && [ -t 0 ]; then
    read -r -p "  Continue anyway? [y/N] " answer
    [[ "$answer" =~ ^[yY] ]] || exit 1
fi
[ "$needs_display" = 1 ] && say "  Disable screen blanking and do not touch the gzclient window (normal size) during the runs."

# CSVs left in ~/.ros by earlier runs: kept aside, never overwritten.
if [ -f "$UPDATE_CSV" ] || [ -f "$FPS_CSV" ]; then
    mkdir -p "$RESULTS_DIR/preexisting_ros_csv"
    for f in "$UPDATE_CSV" "$FPS_CSV"; do
        [ -f "$f" ] && mv "$f" "$RESULTS_DIR/preexisting_ros_csv/$(basename "$f" .csv)_$(date -r "$f" +%Y%m%d_%H%M%S).csv"
    done
    say "  earlier ~/.ros CSVs moved to $RESULTS_DIR/preexisting_ros_csv/"
fi

[ -f "$RESULTS_DIR/verdicts_per_run.csv" ] || \
    echo "protocol,agents,run,status,spawn_s,mean_step_ms,p95_step_ms,mean_rtf,rtf_clock,agents_end,verdict,median_max_core_mhz,max_pkg_temp_c,battery,min_mem_available_mb" \
    > "$RESULTS_DIR/verdicts_per_run.csv"
[ -f "$RESULTS_DIR/verdicts_per_point.csv" ] || \
    echo "protocol,agents,check,reference,runs,runs_pass,mean,ci95,min,max,verdict" \
    > "$RESULTS_DIR/verdicts_per_point.csv"
cp "$REPEAT_DIR"/worlds/*.world "$REPEAT_DIR/repeat_uuvsim.launch" "$RESULTS_DIR/" 2>/dev/null

sha() { sha256sum "$1" 2>/dev/null | cut -c1-16; }
{
    echo "# UUVSim repeated runs"
    echo
    echo "$REPEATS independent runs of each UUVSim reference point. Each run has its own folder"
    echo "(\`protocol_<P>/<agents>/run<k>/\`)."
    echo
    echo "## Setup"
    echo
    echo "| Specification | Value |"
    echo "|---|---|"
    echo "| Date | $(date '+%Y-%m-%d %H:%M %Z') |"
    echo "| Host | $(cat /sys/class/dmi/id/product_name 2>/dev/null) |"
    echo "| Operating system | $(lsb_release -ds 2>/dev/null), kernel $(uname -r) |"
    echo "| Processor | $(lscpu | sed -n 's/^Model name: *//p') |"
    echo "| RAM | $(awk '/MemTotal/ { printf "%.0f GB", $2 / 1048576 }' /proc/meminfo) |"
    echo "| GPU | $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -n 1) |"
    echo "| NVIDIA driver | $DRIVER (reference README: $REF_DRIVER) |"
    echo "| Gazebo | $(gzserver --version 2>&1 | sed -n 's/.*version \([0-9.]*\).*/\1/p' | head -n 1), $(command -v gzserver) |"
    echo "| ROS | $(rosversion -d 2>/dev/null) |"
    echo "| Python | $(python --version 2>&1) (runs), $(python3 --version 2>&1) (statistics) |"
    echo "| uuv_simulator | $(git -C "$CATKIN_WS/src/uuv_simulator" rev-parse --short HEAD 2>/dev/null) |"
    echo "| bluerov2 | $(git -C "$CATKIN_WS/src/bluerov2" rev-parse --short HEAD 2>/dev/null) |"
    echo "| Worlds (sha256) | A $(sha "$REPEAT_DIR/worlds/empty_underwater_A.world"), B $(sha "$REPEAT_DIR/worlds/empty_underwater_B.world"), C/D $(sha "$REPEAT_DIR/worlds/empty_underwater_CD.world") |"
    echo "| Runner (sha256) | $(sha "$REPEAT_DIR/repeat_run_uuvsim.py") |"
    echo "| Power supply | $(for ps in /sys/class/power_supply/*; do [ "$(cat "$ps/type" 2>/dev/null)" = Mains ] && { [ "$(cat "$ps/online")" = 1 ] && echo AC || echo battery; }; done | head -n 1) |"
    echo "| Displays | ${monitors:-unknown} |"
    echo "| Rendering | gzclient window at its normal size for A, B and C (\`gzclient_window.txt\` per run); D headless (\`gui:=false\`) |"
    echo
    echo "## Protocol"
    echo
    echo "- World per protocol, passed to the launch (\`repeats/worlds/\`), the submodule world is untouched:"
    echo "  A dt 0.2 s, real_time_update_rate 5, RTF 1; B dt 0.03 s, rate 33.333, RTF 1; C/D dt 0.03 s, uncapped."
    echo "  Each run checks that Gazebo loaded these values (\`physics.json\`)."
    echo "- Current of $CURRENT m/s applied through \`/hydrodynamics/set_current_velocity\` before the spawn."
    echo "- Agents spawned as \`spawn_multiple_rovs.py\` (one every $SPAWN_PACE s) with seed = run number;"
    echo "  the drawn poses are in \`positions.csv\`. The reference runs had no fixed seed."
    echo "- The measure starts once \`/gazebo/model_states\` lists every agent, plus $MARGIN_SECONDS s, and lasts"
    echo "  $MEASURE_SECONDS s of wall time (\`window.json\`). In the reference, the 300 s window started 10 s after"
    echo "  the first spawn, so the spawn (2 s per agent) overlapped most of it."
    echo "- A and B pass when the mean step over the window is at most the budget + 2 %: 204 ms for A,"
    echo "  $(awk -v b="$B_BUDGET_MS" 'BEGIN { printf "%.2f", b * 1.02 }') ms for B (base $B_BUDGET_MS ms; 30.303 ms = 1/33 s is the base of the Stonefish and"
    echo "  HoloOcean repeats, the strict base for dt = 0.03 s would be 30 ms, i.e. 30.6 ms)."
    echo "- The verdict uses the mean Update() duration only. The RTF (simulated / wall time)"
    echo "  is reported but not judged: a real step lasts 12-17 % longer than its Update(). Only an RTF"
    echo "  above 1.02 flags a run invalid (RTF cap not applied)."
    echo "- \`update_times.csv\` holds the duration of \`World::Update()\` only (gz_sim_source_files/World.cc),"
    echo "  without the sleep of the RTF throttle: the mean step of these capped runs compares directly"
    echo "  with the uncapped reference sweep."
    echo "- C and D report the mean RTF of \`/gazebo/performance_metrics\` over the window, compared with the"
    echo "  reference within ±$TOL %; D 35 must stay above 2x and D 40 at or below 2x."
    echo "- Every process (roscore, roslaunch, gzserver, gzclient, ROS nodes) is killed and checked gone"
    echo "  between two runs, followed by $COOLDOWN s of idle machine."
    echo "- Departures from the reference:"
    echo "  - the reference A/B sweep (\`data/uuv/AB\`) ran with the RTF uncapped (median RTF 11.6 at 30 agents),"
    echo "    not at RTF 1 as these repeats, and its spawn overlapped the measure window;"
    echo "  - the gzclient window stays at its normal size, the UUVSim README asks to extend it to full screen;"
    echo "  - NVIDIA driver $DRIVER on this machine, the README states $REF_DRIVER."
    echo
    echo "Statistics: \`python3 $(basename "$PROCESS") summary --repeats-dir <this folder>\`"
    echo "writes \`uuvsim_repeats_per_run.csv\` and \`uuvsim_repeats_summary.csv\`."
    echo "\`machine.csv\` in each run folder holds the fastest core clock, the CPU package temperature,"
    echo "the battery status and the available memory, sampled every 0.2 s with the run phase."
} > "$RESULTS_DIR/README.md"

# ─── Campaign ─────────────────────────────────────────────────────────────────

# run_sweep <protocol> "<sizes>": one probe run per size until the first failure,
# then REPEATS fresh runs at the last passing size (and at the failing one if SWEEP_NEXT=1).
run_sweep() {
    local sp=$1
    read -r -a sizes <<< "$2"
    REMAINING=0
    for n in "${sizes[@]}"; do REMAINING=$((REMAINING + $(estimate_seconds "$n"))); done
    REMAINING=$((REMAINING + (1 + SWEEP_NEXT) * REPEATS * $(estimate_seconds "${sizes[-1]}")))
    N_POINTS=$(( ${#sizes[@]} + 1 + SWEEP_NEXT ))
    say ""
    say "${BLD}Ceiling sweep, protocol $sp: ${sizes[*]} (1 run each), then $REPEATS runs at the ceiling$( [ "$SWEEP_NEXT" = 1 ] && echo ' and at the next size') — at most $(fmt_duration "$REMAINING")${RST}"
    FULL_REPEATS=$REPEATS REPEATS=1 POINT_NO=0 prev='' fail='' fail_kind=budget RUN_PREFIX=probe SEED_OFFSET=100
    local step=5 n i=0
    [ ${#sizes[@]} -ge 2 ] && step=$(( sizes[-1] - sizes[-2] ))
    [ "$step" -gt 0 ] || step=5
    n=${sizes[0]}
    while :; do
        POINT_NO=$((POINT_NO + 1)) PROBE_PASS=0 PROBE_CRASH=0
        repeat_point "$sp" "$n" probe
        if [ "$PROBE_PASS" = 1 ]; then prev=$n
        else fail=$n; [ "$PROBE_CRASH" = 1 ] && fail_kind=crash; break; fi
        i=$((i + 1))
        if [ "$i" -lt ${#sizes[@]} ]; then
            n=${sizes[$i]}
        else
            n=$((n + step))
            [ "$n" -le "$SWEEP_MAX" ] || break
            say "  every size so far passes: extending the sweep to $n"
        fi
    done
    REPEATS=$FULL_REPEATS RUN_PREFIX=run SEED_OFFSET=0
    say "  (the probe runs, in probe1/, are not part of the confirmation runs: $REPEATS fresh runs per size)"
    say ""
    if [ -z "$prev" ]; then
        say "${RED}  The smallest size of the sweep (${sizes[0]}) already fails: the ceiling is below it. Repeating ${sizes[0]} only.${RST}"
        POINT_NO=$((POINT_NO + 1)); repeat_point "$sp" "$fail" over
    elif [ -z "$fail" ]; then
        say "${YEL}  Every size up to SWEEP_MAX=$SWEEP_MAX passes: the ceiling is ≥ $prev. Repeating $prev.${RST}"
        POINT_NO=$((POINT_NO + 1)); repeat_point "$sp" "$prev" realtime
    else
        say "${BLD}  Ceiling found: $prev passes, $fail fails ($( [ "$fail_kind" = crash ] && echo 'CRASH' || echo 'budget exceeded' )). $REPEATS fresh runs at $prev to confirm.${RST}"
        POINT_NO=$((POINT_NO + 1)); repeat_point "$sp" "$prev" realtime
        if [ "$SWEEP_NEXT" = 1 ]; then POINT_NO=$((POINT_NO + 1)); repeat_point "$sp" "$fail" over; fi
    fi
}

if [ -n "$SWEEPS" ]; then
    for sw in "${SWEEP_LIST[@]}"; do
        run_sweep "${sw%%:*}" "${sw#*:}"
        say "  So far: ${GRN}$N_OK point(s) matching${RST}, ${YEL}$N_DIFF deviating${RST}, ${RED}$N_BAD contradicting${RST}"
    done
    PROTOCOLS=("${REGULAR[@]}")
    if [ ${#PROTOCOLS[@]} -eq 0 ]; then
        say ""
        say "${BLD}Campaign statistics:${RST}"
        process_repeats
        print_report
        exit 0
    fi
    say ""
    say "${BLD}Sweeps done. Regular points of: ${PROTOCOLS[*]}${RST}"
fi

POINTS=()
REMAINING=0
for point in "${ALL_POINTS[@]}"; do
    read -r p n _ <<< "$point"
    [[ " ${PROTOCOLS[*]} " == *" $p "* ]] || continue
    POINTS+=("$point")
    REMAINING=$((REMAINING + REPEATS * $(estimate_seconds "$n")))
done
N_POINTS=${#POINTS[@]}
say ""
say "${BLD}$N_POINTS points × $REPEATS runs — expected $(fmt_duration "$REMAINING"), done around $(date -d "+$REMAINING seconds" +%H:%M)${RST}"

POINT_NO=0
for point in "${POINTS[@]}"; do
    POINT_NO=$((POINT_NO + 1))
    # shellcheck disable=SC2086
    repeat_point $point
    say "  So far: ${GRN}$N_OK point(s) matching${RST}, ${YEL}$N_DIFF deviating${RST}, ${RED}$N_BAD contradicting${RST}"
done

say ""
say "${BLD}Campaign statistics:${RST}"
process_repeats
print_report
[ "$N_BAD" -eq 0 ]
