#!/bin/bash
set -euo pipefail

# fpp-matrixcountdown install script (FPP runs it as root)

PLUGIN_DIR=$(cd "$(dirname "$0")/.." && pwd)
. "$PLUGIN_DIR/scripts/daemon_lib.sh"

chmod +x "$PLUGIN_DIR/matrixcountdown.py"
chmod +x "$PLUGIN_DIR"/scripts/*.sh "$PLUGIN_DIR/scripts/spike_overlay.py"

mkdir -p "$MC_LOGDIR"
mkdir -p "$MC_MEDIADIR/config"

# The renderer draws frames with Pillow, and the default style uses DejaVu
# Sans Bold. Install whichever is missing (needs network access the first
# time). Without DejaVu the countdown still draws, with another installed font.
PKGS=""
python3 -c "import PIL" 2>/dev/null || PKGS="$PKGS python3-pil"
[ -f /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf ] || PKGS="$PKGS fonts-dejavu-core"
if [ -n "$PKGS" ]; then
    echo "Installing:$PKGS"
    if ! (apt-get update -qq && apt-get install -y -qq $PKGS); then
        echo "WARNING: could not install$PKGS" >&2
    fi
fi

# Restart the daemon so it picks up the new code. If the old one can't be
# stopped (run by hand as a user other than root), fail rather than start a
# second daemon beside it.
mc_stop_daemon
mc_start_daemon

echo "fpp-matrixcountdown install complete"
