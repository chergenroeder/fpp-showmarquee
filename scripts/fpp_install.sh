#!/bin/bash
set -euo pipefail

# fpp-matrixcountdown install script (FPP runs it as root)

PLUGIN_DIR=$(cd "$(dirname "$0")/.." && pwd)
. "$PLUGIN_DIR/scripts/daemon_lib.sh"

chmod +x "$PLUGIN_DIR/matrixcountdown.py"
chmod +x "$PLUGIN_DIR"/scripts/*.sh "$PLUGIN_DIR"/scripts/*.py
# fppd runs these directly (FPP commands and the callbacks script)
chmod +x "$PLUGIN_DIR/callbacks.sh" "$PLUGIN_DIR"/commands/*.sh

# python3-pil (to draw) and fonts-dejavu-core (the default font) are declared
# in pluginInfo.json "dependencies"; FPP installs them before this script runs
# and removes them on uninstall when nothing else needs them. Only report it
# if they're somehow missing; the settings page says the same.
python3 -c "import PIL" 2>/dev/null \
    || echo "WARNING: python3-pil is missing; the countdown can't draw until it is installed" >&2

# Restart the daemon so it picks up the new code. If the old one can't be
# stopped (run by hand as a user other than root), fail rather than start a
# second daemon beside it.
mc_stop_daemon
mc_start_daemon

echo "fpp-matrixcountdown install complete"
