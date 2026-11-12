#!/bin/bash
set -euo pipefail

# fpp-showmarquee install script (FPP runs it as root)

PLUGIN_DIR=$(cd "$(dirname "$0")/.." && pwd)
. "$PLUGIN_DIR/scripts/daemon_lib.sh"

chmod +x "$PLUGIN_DIR/showmarquee.py"
chmod +x "$PLUGIN_DIR"/scripts/*.sh "$PLUGIN_DIR"/scripts/*.py
# fppd runs these directly (FPP commands and the callbacks script)
chmod +x "$PLUGIN_DIR/callbacks.sh" "$PLUGIN_DIR"/commands/*.sh

# python3-pil (to draw), fonts-dejavu-core (the default font) and
# python3-qrcode (the show prep page's QR code) are declared
# in pluginInfo.json "dependencies"; FPP installs them before this script runs
# and removes them on uninstall when nothing else needs them. Only report it
# if they're somehow missing; the settings page says the same.
python3 -c "import PIL" 2>/dev/null \
    || echo "WARNING: python3-pil is missing; the countdown can't draw until it is installed" >&2
python3 -c "import qrcode" 2>/dev/null \
    || echo "WARNING: python3-qrcode is missing; the show prep page shows no QR code until it is installed" >&2

# Restart the daemon so it picks up the new code. If the old one can't be
# stopped (run by hand as a user other than root), fail rather than start a
# second daemon beside it.
mc_stop_daemon
mc_start_daemon

echo "fpp-showmarquee install complete"
