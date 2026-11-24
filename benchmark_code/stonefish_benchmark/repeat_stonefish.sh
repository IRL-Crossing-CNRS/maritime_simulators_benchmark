#!/usr/bin/env bash
# Repeats the Stonefish reference points, REPEATS independent runs each, and
# flags every run that departs from the reference value as soon as it finishes.
# Protocol and outputs follow the HoloOcean and LRAUVSim repeats.
#
# Points (protocol, agents, target RTF) and what is checked:
#   A 8, B 8 at RTF 1   every run holds mean step <= budget + 2 %
#   A 9, B 9 at RTF 1   every run crashes at start-up (MAX_OCEAN_CURRENTS = 64 = 8 agents x 8 thrusters)
#   D 1 at 1000         RTF peak
#   D 90 at 5           RTF > 2x in every run
#
# Usage:
#   ./repeat_stonefish.sh                     all points
#   ./repeat_stonefish.sh A D                 only some protocols
#   RESULTS_DIR=<dir> ./repeat_stonefish.sh   resume a campaign (finished runs are kept)
#
# Environment overrides: BENCH (Stonefish Tests/Benchmark executable), REF_CSV,
# REPEATS, TOL (%), MEASURE_SECONDS, WARMUP_STEPS, RUN_TIMEOUT

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$SCRIPT_DIR/../.." && pwd)

BENCH=${BENCH:-$REPO/../stonefish/build/Tests/Benchmark}
REF_CSV=${REF_CSV:-$REPO/benchmark_results/stonefish/results/benchmark_summary.csv}
PROCESS=${PROCESS:-$REPO/benchmark_results/stonefish/process_stonefish_repeats.py}
REF_SHA256=0b903f5a6d31d6661a1b3d9de934cbce698d94c90f22cfa9ab4543c432b9b7fa
REPEATS=${REPEATS:-5}
TOL=${TOL:-10}
MEASURE_SECONDS=${MEASURE_SECONDS:-300}
WARMUP_STEPS=${WARMUP_STEPS:-50}
RUN_TIMEOUT=${RUN_TIMEOUT:-$((3 * MEASURE_SECONDS + 120))}
RESULTS_DIR=${RESULTS_DIR:-$HOME/stonefish_repeats/$(date +%Y%m%d_%H%M%S)}
STEP_MARGIN=1.02

# protocol agents target_rtf check [rtf_floor]
ALL_POINTS=(
    "A 8 1 realtime"
    "A 9 1 crash"
    "B 8 1 realtime"
    "B 9 1 crash"
    "D 1 1000 rtf"
    "D 90 5 rtf 2"
)

PROTOCOLS=("$@")
[ ${#PROTOCOLS[@]} -eq 0 ] && PROTOCOLS=(A B D)

if [ -t 1 ]; then
    RED=$'\e[1;97;41m' YEL=$'\e[1;30;43m' GRN=$'\e[1;32m' BLD=$'\e[1m' RST=$'\e[0m'
else
    RED='' YEL='' GRN='' BLD='' RST=''
fi

protocol_name() {
    case $1 in
        A) echo A-human-loop ;;  B) echo B-control ;;  D) echo D-ai-headless ;;
        *) return 1 ;;
    esac
}

budget_ms() { [ "$1" = A ] && echo 200 || echo 30.303030; }

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

pct() { awk -v g="$1" -v r="$2" 'BEGIN { printf "%+.1f", (g - r) / r * 100 }'; }

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
    say "  MAX_OCEAN_CURRENTS in the installed headers: ${OCEAN_CURRENTS:-not found}"
    say "  results: $RESULTS_DIR"
    if [ "$N_BAD" -gt 0 ]; then
        say "${RED}  $N_BAD point(s) contradict the reference ${RST}"
    elif [ "$N_DIFF" -gt 0 ]; then
        say "${YEL}  $N_DIFF point(s) deviate from the reference ${RST}"
    else
        say "${GRN}  Every repeated point matches the reference.${RST}"
    fi
}

RUN_PID='' SAMPLER_PID=''
on_interrupt() {
    [ -n "$RUN_PID" ] && kill -TERM "$RUN_PID" 2>/dev/null
    [ -n "$SAMPLER_PID" ] && kill "$SAMPLER_PID" 2>/dev/null
    wait 2>/dev/null
    say ""
    say "${YEL}  Campaign interrupted. To resume without re-running finished runs:${RST}"
    say "    RESULTS_DIR=$RESULTS_DIR $0 ${PROTOCOLS[*]}"
    print_report
    exit 130
}
trap on_interrupt INT TERM

stop_campaign() {
    printf '\a\a\a'
    say ""
    say "${RED}  CAMPAIGN STOPPED: $1 ${RST}"
    print_report
    exit 2
}

# ─── Guards checked before every run ──────────────────────────────────────────

check_alone() {
    local others
    others=$(pgrep -a -x Benchmark || true)
    [ -z "$others" ] || stop_campaign "another Stonefish benchmark is already running (never measure two at once): $others"
}

check_renderer() {
    local r
    r=$(glxinfo -B 2>/dev/null | sed -n 's/.*OpenGL renderer string: //p')
    [[ "$r" == *NVIDIA* ]] || stop_campaign "OpenGL renders on \"${r:-glxinfo unavailable}\", not on the NVIDIA GPU: protocols A and B would be invalid"
}

# ─── Machine state ────────────────────────────────────────────────────────────

PKG_TEMP=$(for z in /sys/class/thermal/thermal_zone*; do
    [ "$(cat "$z/type" 2>/dev/null)" = x86_pkg_temp ] && echo "$z/temp"; done | head -n 1)
BAT_STATUS=$(ls /sys/class/power_supply/BAT*/status 2>/dev/null | head -n 1)

# Samples the machine every 0.2 s into $1 until killed: highest core clock (the
# core running the simulation), CPU package temperature, battery status, and the
# phase of the run read from its log $2 (setup, measure, end).
sample_machine() {
    echo "time_s,max_core_mhz,pkg_temp_c,battery,phase" > "$1"
    local phase=setup f
    while :; do
        if [ "$phase" = setup ] && grep -q 'Starting measurement' "$2" 2>/dev/null; then phase=measure; fi
        if [ "$phase" = measure ] && grep -q 'Measurement complete' "$2" 2>/dev/null; then phase=end; fi
        f=$(sort -n /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq 2>/dev/null | tail -n 1)
        echo "$(date +%s.%N | cut -c1-14),$((${f:-0} / 1000)),$(( $(cat "$PKG_TEMP" 2>/dev/null || echo 0) / 1000 )),$(cat "$BAT_STATUS" 2>/dev/null || echo none),$phase" >> "$1"
        sleep 0.2
    done
}

# Prints "<median MHz> <max temp> <battery states>" over the measure phase of a
# machine.csv (the whole run if no sample fell inside the measure).
machine_summary() {
    [ -f "$1" ] || { echo "- - -"; return; }
    awk -F, 'NR > 1 { all[++n] = $0; if ($5 == "measure") m++ }
        END {
            for (i = 1; i <= n; i++) {
                split(all[i], r, ",")
                if (m > 0 && r[5] != "measure") continue
                f[++k] = r[2]; if (r[3] > t) t = r[3]; b[r[4]] = 1
            }
            if (k == 0) { print "- - -"; exit }
            asort(f); s = ""
            for (x in b) s = s (s == "" ? "" : "+") x
            printf "%d %d %s\n", f[int((k + 1) / 2)], t, s
        }' "$1"
}

# ─── One benchmark run ────────────────────────────────────────────────────────

# Prints the summary row of (protocol $2, agents $3, target $4) from run directory $1.
result_row() {
    [ -f "$1/benchmark_summary.csv" ] || return 0
    awk -F, -v p="$(protocol_name "$2")" -v n="$3" -v t="$4" \
        'NR > 1 && $1 == p && $2 + 0 == n + 0 && $4 + 0 == t + 0' "$1/benchmark_summary.csv" | tail -n 1
}

# run_once <dir> <protocol> <agents> <target_rtf>; leaves the summary row in $ROW
run_once() {
    local dir=$1 p=$2 n=$3 t=$4
    ROW=$(result_row "$dir" "$p" "$n" "$t")
    if [ -n "$ROW" ]; then
        say "  (run already finished in this campaign, kept)"
        return
    fi

    check_alone
    [ "$p" = D ] || check_renderer
    mkdir -p "$dir"
    cat > "$dir/config.json" <<EOF
{
  "output_dir": "$dir",
  "warmup_steps": $WARMUP_STEPS,
  "measure_seconds": $MEASURE_SECONDS,
  "runs": [ { "protocol": "$p", "agents": [$n], "target_rtf": $t } ]
}
EOF
    local log="$dir/run.log"
    : > "$log"
    sample_machine "$dir/machine.csv" "$log" &
    SAMPLER_PID=$!
    # timeout runs the benchmark in its own process group, so a hang kills the
    # forked simulation child too; Ctrl+C reaches it through on_interrupt.
    (cd "$dir" && exec timeout -k 30 "$RUN_TIMEOUT" \
        stdbuf -oL -eL "$BENCH" --config "$dir/config.json") >> "$log" 2>&1 &
    RUN_PID=$!
    tail -n +1 -f --pid="$RUN_PID" "$log" | grep --line-buffered -E 'agents=|Child exited|ERROR|CRITICAL' | sed 's/^/    /' &
    local tail_pid=$! start=$SECONDS next_beat=60
    while kill -0 "$RUN_PID" 2>/dev/null; do
        sleep 5
        if [ $((SECONDS - start)) -ge "$next_beat" ]; then
            say "    … running for $(fmt_duration $((SECONDS - start))) (expected ≈ $(fmt_duration "$RUN_EST"))"
            next_beat=$((next_beat + 60))
        fi
    done
    wait "$RUN_PID"
    local rc=$?
    RUN_PID=''
    kill "$SAMPLER_PID" 2>/dev/null
    wait "$SAMPLER_PID" 2>/dev/null
    SAMPLER_PID=''
    wait "$tail_pid" 2>/dev/null

    ROW=$(result_row "$dir" "$p" "$n" "$t")
    if [ -z "$ROW" ]; then
        local status="no_result_rc_$rc"
        [ "$rc" -eq 124 ] && status="timeout_${RUN_TIMEOUT}s"
        ROW="$(protocol_name "$p"),$n,0,$t,-,0,0,0,0,0,0,0,0,false,$status"
    fi
}

field() { cut -d, -f"$1" <<< "$ROW"; }

# Wall time of one run: start-up plus the 2 s the benchmark sleeps after each
# child (~15 s), warmup, then the measure window played at the reference RTF.
estimate_seconds() {
    local p=$1 check=$2 rtf=$3
    [ "$check" = crash ] && { echo 20; return; }
    awk -v p="$p" -v m="$MEASURE_SECONDS" -v w="$WARMUP_STEPS" -v r="$rtf" 'BEGIN {
        if (p == "A")      s = m + w * 0.2
        else if (p == "B") s = m + w / 33
        else               s = (m + w / 33) / r
        printf "%d", s + 15
    }'
}

# ─── Statistics ───────────────────────────────────────────────────────────────

# Reads one value per line; prints "n mean ci95 min max" (Student t, n-1 dof).
stats() {
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

# Per-run and summary statistics (mean, sd, CI, PI, p95, dispersion ratios), same
# definitions as the HoloOcean and LRAUVSim repeats. Rewrites both CSVs each call.
process_repeats() {
    python3 -I "$PROCESS" --repeats-dir "$RESULTS_DIR" --reference-csv "$REF_CSV" \
        --out-dir "$RESULTS_DIR" "$@" 2>&1 | tee -a "$RESULTS_DIR/campaign.log"
}

# ─── One reference point, repeated ────────────────────────────────────────────

repeat_point() {
    local p=$1 n=$2 t=$3 check=$4 floor=${5:-}
    local pname; pname=$(protocol_name "$p")
    local ref; ref=$(awk -F, -v p="$pname" -v n="$n" -v t="$t" \
        'NR > 1 && $1 == p && $2 + 0 == n + 0 && $4 + 0 == t + 0' "$REF_CSV" | tail -n 1)
    [ -n "$ref" ] || { say "${YEL}Point $p $n agents target $t not in the reference, skipped.${RST}"; return; }
    local ref_status ref_rtf ref_step
    ref_status=$(cut -d, -f15 <<< "$ref") ref_rtf=$(cut -d, -f6 <<< "$ref") ref_step=$(cut -d, -f9 <<< "$ref")
    local limit; limit=$(awk -v b="$(budget_ms "$p")" -v m="$STEP_MARGIN" 'BEGIN { printf "%.2f", b * m }')

    local reference
    case $check in
        realtime) reference="step ${ref_step} ms (budget + 2 % = $limit ms)" ;;
        crash)    reference="crash ($ref_status)" ;;
        rtf)      reference="RTF ${ref_rtf}${floor:+, > ${floor}x}" ;;
    esac
    say ""
    say "${BLD}━━━━━━ Protocol $pname — $n agent(s) — target_rtf $t — $REPEATS runs ━━━━━━${RST}"
    say "  reference: $reference"

    local values='' passed=0 k
    for k in $(seq 1 "$REPEATS"); do
        RUN_EST=$(estimate_seconds "$p" "$check" "$ref_rtf")
        say ""
        say "${BLD}[run $k/$REPEATS — point $POINT_NO/$N_POINTS] $(date +%H:%M) — this run ≈ $(fmt_duration "$RUN_EST"), left ≈ $(fmt_duration "$REMAINING"), done around $(date -d "+$REMAINING seconds" +%H:%M)${RST}"
        run_once "$RESULTS_DIR/protocol_$p/$n/run$k" "$p" "$n" "$t"
        REMAINING=$((REMAINING > RUN_EST ? REMAINING - RUN_EST : 0))

        local status rtf step verdict msg
        status=$(field 15) rtf=$(field 6) step=$(field 9)
        local title="$p, $n agent(s), run $k/$REPEATS"
        case $check in
            realtime)
                if [ "$status" != ok ]; then
                    verdict=CONTRADICTS msg="the reference holds $n agents within the budget, this run crashed ($status)"
                elif awk -v s="$step" -v l="$limit" 'BEGIN { exit !(s > l) }'; then
                    verdict=CONTRADICTS msg="mean step $step ms > $limit ms (budget + 2 %): $n agents do not hold the budget"
                else
                    verdict=OK msg="mean step $step ms ≤ $limit ms (mean RTF $rtf)"
                    values+="$step"$'\n'
                fi ;;
            crash)
                if [ "$status" = ok ]; then
                    verdict=DEVIATION msg="the reference crashes at $n agents (limit of 8), this run finished (mean step $step ms)"
                    values+="$step"$'\n'
                else
                    verdict=OK msg="crashes as in the reference ($status)"
                fi ;;
            rtf)
                if [ "$status" != ok ]; then
                    verdict=CONTRADICTS msg="crash ($status) where the reference reaches RTF $ref_rtf"
                else
                    values+="$rtf"$'\n'
                    local diff; diff=$(pct "$rtf" "$ref_rtf")
                    if [ -n "$floor" ] && awk -v r="$rtf" -v f="$floor" 'BEGIN { exit !(r <= f) }'; then
                        verdict=CONTRADICTS msg="RTF $rtf ≤ ${floor}x at $n agents"
                    elif awk -v d="$diff" -v tol="$TOL" 'BEGIN { exit !(d < -tol || d > tol) }'; then
                        verdict=DEVIATION msg="RTF $rtf, ${diff}% from the reference (beyond ±${TOL}%)"
                    else
                        verdict=OK msg="RTF $rtf, ${diff}% from the reference"
                    fi
                fi ;;
        esac
        [ "$verdict" = OK ] && passed=$((passed + 1)) || N_RUN_ALERTS=$((N_RUN_ALERTS + 1))
        alert "$verdict" "$title" "$msg"
        local mhz temp_max battery
        read -r mhz temp_max battery <<< "$(machine_summary "$RESULTS_DIR/protocol_$p/$n/run$k/machine.csv")"
        say "    machine during the measure: fastest core at $mhz MHz (median), CPU ${temp_max} °C max, battery $battery"
        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$pname" "$n" "$t" "$k" "$status" \
            "$rtf" "$(field 7)" "$(field 8)" "$step" "$(field 10)" "$(field 11)" "$verdict" \
            "$mhz" "$temp_max" "$battery" >> "$RESULTS_DIR/verdicts_per_run.csv"
    done

    # Point verdict over all runs
    local cnt mean ci lo hi point_verdict summary
    read -r cnt mean ci lo hi <<< "$(printf '%s' "$values" | stats)"
    case $check in
        realtime)
            summary="$passed/$REPEATS runs within the budget; mean step $mean ± $ci ms (min $lo, max $hi)"
            [ "$passed" -eq "$REPEATS" ] && point_verdict=OK || point_verdict=CONTRADICTS ;;
        crash)
            summary="$passed/$REPEATS runs crash as in the reference"
            [ "$passed" -eq "$REPEATS" ] && point_verdict=OK || point_verdict=DEVIATION ;;
        rtf)
            summary="RTF $mean ± $ci (95 % CI, $cnt of $REPEATS runs finished; min $lo, max $hi); reference $ref_rtf"
            if [ "$cnt" -eq 0 ]; then
                point_verdict=CONTRADICTS
            elif [ -n "$floor" ] && awk -v l="$lo" -v f="$floor" 'BEGIN { exit !(l <= f) }'; then
                point_verdict=CONTRADICTS
            elif awk -v d="$(pct "$mean" "$ref_rtf")" -v tol="$TOL" 'BEGIN { exit !(d < -tol || d > tol) }'; then
                point_verdict=DEVIATION summary+=" (mean $(pct "$mean" "$ref_rtf")%)"
            elif [ "$cnt" -lt "$REPEATS" ]; then
                point_verdict=DEVIATION summary+="; $((REPEATS - cnt)) run(s) crashed"
            else
                point_verdict=OK
            fi ;;
    esac
    case $point_verdict in
        OK) N_OK=$((N_OK + 1)) ;;  DEVIATION) N_DIFF=$((N_DIFF + 1)) ;;  CONTRADICTS) N_BAD=$((N_BAD + 1)) ;;
    esac
    say ""
    alert "$point_verdict" "POINT $p, $n agent(s), target_rtf $t" "$summary"
    REPORT+=("$(printf '%-11s %-3s %3s agents  target %-5s  %s' "$point_verdict" "$p" "$n" "$t" "$summary")")
    printf '%s,%s,%s,%s,"%s",%s,%s,%s,%s,%s,%s,%s\n' "$pname" "$n" "$t" "$check" "$reference" \
        "$REPEATS" "$passed" "$mean" "$ci" "$lo" "$hi" "$point_verdict" \
        >> "$RESULTS_DIR/verdicts_per_point.csv"
    say "  Point statistics (first 10 % of the steps discarded for median, p95, p99, max and ratios):"
    process_repeats --point "$p:$n"
}

# ─── Pre-flight ───────────────────────────────────────────────────────────────

for p in "${PROTOCOLS[@]}"; do
    protocol_name "$p" > /dev/null || { echo "Unknown protocol: $p (expected: A B D)"; exit 1; }
done
if [ ! -x "$BENCH" ]; then
    echo "Benchmark executable not found: $BENCH"
    echo "Build Stonefish with BUILD_TESTS=ON (with gcc: clang lacks OpenMP) or set BENCH=<path>."
    exit 1
fi
[ -f "$REF_CSV" ] || { echo "Reference CSV not found: $REF_CSV"; exit 1; }
python3 -I -c 'import numpy' 2> /dev/null || { echo "numpy is needed for the statistics: sudo apt install python3-numpy"; exit 1; }
needs_display=0
[[ " ${PROTOCOLS[*]} " =~ [AB] ]] && needs_display=1
if [ "$needs_display" = 1 ] && [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    echo "Protocols A and B open a window: run this script from the graphical session."
    exit 1
fi

mkdir -p "$RESULTS_DIR"

say "${BLD}Stonefish repeated runs — $(date '+%Y-%m-%d %H:%M')${RST}"
say "  protocols: ${PROTOCOLS[*]}    $REPEATS runs per point    measure: ${MEASURE_SECONDS} s of simulated time"
say "  A/B: mean step ≤ budget + 2 %    D: flagged beyond ±${TOL}% of the reference"
say "  results:   $RESULTS_DIR"
say ""

check_alone
[ "$needs_display" = 1 ] && check_renderer

warn=0
if [ "$(sha256sum "$REF_CSV" | cut -d' ' -f1)" != "$REF_SHA256" ]; then
    say "${RED}  The reference CSV is not the released one (sha256 differs): $REF_CSV ${RST}"
    warn=1
fi
OCEAN_CURRENTS=$(sed -n 's/.*#define MAX_OCEAN_CURRENTS *((GLint)\([0-9]*\)).*/\1/p' \
    /usr/local/include/Stonefish/graphics/OpenGLDataStructs.h 2>/dev/null)
if [ "${OCEAN_CURRENTS:-}" != 64 ]; then
    say "${RED}  MAX_OCEAN_CURRENTS is \"${OCEAN_CURRENTS:-not found}\" in the installed headers, the reference build has 64. ${RST}"
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
if pgrep -x code > /dev/null || pgrep -f '/code/code' > /dev/null; then
    say "${YEL}  VSCode is still running: close it (no other application open). ${RST}"
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
profile=$(powerprofilesctl get 2>/dev/null || echo unknown)
if [ "$profile" != performance ]; then
    say "${YEL}  Power profile: $profile (use performance: powerprofilesctl set performance). ${RST}"
    warn=1
fi
if [ "$warn" = 1 ] && [ -t 0 ]; then
    read -r -p "  Continue anyway? [y/N] " answer
    [[ "$answer" =~ ^[yY] ]] || exit 1
fi
[ "$needs_display" = 1 ] && say "  Disable screen blanking: A and B draw in a window."

cp "$REF_CSV" "$RESULTS_DIR/reference_summary.csv"
echo "protocol,agents,target_rtf,run,status,mean_rtf,min_rtf,p95_rtf,mean_step_ms,p95_step_ms,mean_fps,verdict,median_max_core_mhz,max_pkg_temp_c,battery" \
    > "$RESULTS_DIR/verdicts_per_run.csv"
echo "protocol,agents,target_rtf,check,reference,runs,runs_pass,mean,ci95,min,max,verdict" \
    > "$RESULTS_DIR/verdicts_per_point.csv"
STONEFISH_SRC=$(cd "$(dirname "$BENCH")/../.." && pwd)
STONEFISH_VERSION=$(sed -n 's/^project(Stonefish VERSION \([0-9.]*\)).*/\1/p' "$STONEFISH_SRC/CMakeLists.txt")
DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n 1)
{
    echo "# Stonefish repeated runs"
    echo
    echo "$REPEATS independent runs of each Stonefish reference point. Each run has its own folder"
    echo "(\`protocol_<P>/<agents>/run<k>/\`)."
    echo
    echo "## Setup"
    echo
    echo "| Specification | Value |"
    echo "|---|---|"
    echo "| Date | $(date '+%Y-%m-%d %H:%M %Z') |"
    echo "| Operating system | $(lsb_release -ds 2>/dev/null), kernel $(uname -r) |"
    echo "| Processor | $(lscpu | sed -n 's/^Model name: *//p') |"
    echo "| GPU | $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -n 1) |"
    echo "| OpenGL renderer | $(glxinfo -B 2>/dev/null | sed -n 's/.*OpenGL renderer string: //p') |"
    echo "| NVIDIA driver | $DRIVER |"
    echo "| Stonefish | $STONEFISH_VERSION, commit $(git -C "$STONEFISH_SRC" rev-parse --short HEAD 2>/dev/null) |"
    echo "| MAX_OCEAN_CURRENTS (installed headers) | ${OCEAN_CURRENTS:-not found} |"
    echo "| Power profile | $profile |"
    echo "| Power supply | $(for ps in /sys/class/power_supply/*; do [ "$(cat "$ps/type" 2>/dev/null)" = Mains ] && { [ "$(cat "$ps/online")" = 1 ] && echo AC || echo battery; }; done | head -n 1) |"
    echo "| Displays | ${monitors:-unknown} |"
    echo "| Rendering window | 960 × 540, low quality, no vsync (fixed in Benchmark/main.cpp) |"
    echo
    echo "## Protocol"
    echo
    echo "- Warmup: $WARMUP_STEPS steps, then $MEASURE_SECONDS s of simulated time measured."
    echo "- A and B pass when the mean step is at most the budget + 2 % (204 ms for A, 30.91 ms for B)."
    echo "- D reports the mean RTF over the finished runs ± 95 % CI (Student t, n − 1 dof), min and max."
    echo "- Reference: \`$(basename "$REF_CSV")\`, sha256 $(sha256sum "$REF_CSV" | cut -d' ' -f1)."
    echo
    echo "| Protocol | Agents | Target RTF | Check |"
    echo "|---|---|---|---|"
    for point in "${ALL_POINTS[@]}"; do
        read -r p n t check floor <<< "$point"
        [[ " ${PROTOCOLS[*]} " == *" $p "* ]] || continue
        case $check in
            realtime) desc="mean step ≤ budget + 2 % in every run" ;;
            crash)    desc="crashes at start-up in every run (rendering limit of 8 agents)" ;;
            rtf)      desc="RTF compared with the reference${floor:+, > ${floor}x in every run}" ;;
        esac
        echo "| $p | $n | $t | $desc |"
    done
    echo
    echo "Statistics: \`python3 $(basename "$PROCESS") --repeats-dir <this folder> --out-dir <this folder>\`"
    echo "writes \`stonefish_repeats_per_run.csv\` and \`stonefish_repeats_summary.csv\`."
    echo "\`machine.csv\` in each run folder holds the fastest core clock, the CPU package"
    echo "temperature and the battery status, sampled every 0.2 s."
} > "$RESULTS_DIR/README.md"

# ─── Campaign ─────────────────────────────────────────────────────────────────

POINTS=()
REMAINING=0
for point in "${ALL_POINTS[@]}"; do
    read -r p n t check _ <<< "$point"
    [[ " ${PROTOCOLS[*]} " == *" $p "* ]] || continue
    POINTS+=("$point")
    rtf=$(awk -F, -v p="$(protocol_name "$p")" -v n="$n" -v t="$t" \
        'NR > 1 && $1 == p && $2 + 0 == n + 0 && $4 + 0 == t + 0 { r = $6 } END { print r + 0 }' "$REF_CSV")
    REMAINING=$((REMAINING + REPEATS * $(estimate_seconds "$p" "$check" "$rtf")))
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
