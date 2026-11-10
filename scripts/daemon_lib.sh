#!/bin/bash
# Shared daemon start/stop for the plugin's lifecycle scripts (sourced, not run).
#
# The daemon is found by its command line, so nothing needs a PID file: that
# also finds one the web UI's Start button launched. FPP runs these scripts as
# root; run as another user they cannot signal a root daemon, so stopping
# reports failure rather than letting the caller start a second daemon beside it.

MC_PLUGIN_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MC_DAEMON="$MC_PLUGIN_DIR/matrixcountdown.py"
# FPP provides MEDIADIR/LOGDIR; fall back to the default install paths
MC_MEDIADIR="${MEDIADIR:-/home/fpp/media}"
MC_LOGDIR="${LOGDIR:-$MC_MEDIADIR/logs}"
MC_LOGFILE="$MC_LOGDIR/plugin-fpp-matrixcountdown.log"

# PIDs of running daemons (anchored so a shell whose command line merely
# mentions the path doesn't match)
mc_daemon_pids() {
    pgrep -f "^(/usr/bin/)?python3 $MC_DAEMON\$" || true
}

# Stop every running daemon. Returns 1 if any survive.
mc_stop_daemon() {
    local pids
    pids=$(mc_daemon_pids)
    if [ -n "$pids" ]; then
        echo "Stopping matrixcountdown (PID $(echo $pids))..."
        kill $pids 2>/dev/null || true
        for _ in $(seq 1 20); do
            [ -z "$(mc_daemon_pids)" ] && break
            sleep 0.1
        done
        pids=$(mc_daemon_pids)
        if [ -n "$pids" ]; then
            kill -9 $pids 2>/dev/null || true
            sleep 0.2
        fi
    fi
    pids=$(mc_daemon_pids)
    if [ -n "$pids" ]; then
        echo "ERROR: could not stop matrixcountdown (PID $(echo $pids), owner $(ps -o user= -p $(echo $pids | cut -d' ' -f1))); run as root" >&2
        return 1
    fi
}

# Start the daemon unless one is already running.
mc_start_daemon() {
    local pids
    pids=$(mc_daemon_pids)
    if [ -n "$pids" ]; then
        echo "matrixcountdown already running (PID $(echo $pids))"
        return 0
    fi
    mkdir -p "$MC_LOGDIR"
    local commit
    commit=$(git -C "$MC_PLUGIN_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    echo "Starting matrixcountdown daemon @ $commit..."
    # The daemon writes its own log; this only catches a crash traceback
    MEDIADIR="$MC_MEDIADIR" LOGDIR="$MC_LOGDIR" python3 "$MC_DAEMON" >> "$MC_LOGFILE" 2>&1 &
    echo "matrixcountdown started (PID $!)"
}
