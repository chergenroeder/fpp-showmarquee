#!/bin/bash
set -euo pipefail

# fpp-matrixcountdown install script (FPP runs it as root)

PLUGIN_DIR=$(cd "$(dirname "$0")/.." && pwd)
. "$PLUGIN_DIR/scripts/daemon_lib.sh"

chmod +x "$PLUGIN_DIR/matrixcountdown.py"
chmod +x "$PLUGIN_DIR"/scripts/*.sh "$PLUGIN_DIR/scripts/spike_overlay.py"

mkdir -p "$MC_LOGDIR"
mkdir -p "$MC_MEDIADIR/config"

# The renderer draws frames with Pillow. FPP images usually ship it; install
# it if not (needs network access the first time).
if ! python3 -c "import PIL" 2>/dev/null; then
    echo "Pillow not found; installing python3-pil..."
    if ! (apt-get update -qq && apt-get install -y -qq python3-pil); then
        echo "WARNING: could not install python3-pil; the countdown cannot draw until it is installed" >&2
    fi
fi

# Restart the daemon so it picks up the new code. If the old one can't be
# stopped (run by hand as a user other than root), fail rather than start a
# second daemon beside it.
mc_stop_daemon
mc_start_daemon

echo "fpp-matrixcountdown install complete"
