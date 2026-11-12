#!/bin/bash

# fpp-showmarquee uninstall script (safe to run more than once)

. "$(dirname "$0")/daemon_lib.sh"

mc_stop_daemon

# Settings (config/plugin.fpp-showmarquee.json) are kept, as FPP itself
# keeps plugin settings: FPP 10.3 and earlier don't tell a Reinstall from an
# uninstall, and "Reinstall All" after an OS upgrade would otherwise wipe them.

echo "fpp-showmarquee uninstall complete"
