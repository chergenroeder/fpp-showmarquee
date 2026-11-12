#!/bin/bash

# fpp-showmarquee uninstall script (safe to run more than once)

. "$(dirname "$0")/daemon_lib.sh"

mc_stop_daemon || true

# A real uninstall removes everything the plugin keeps outside its folder: its
# settings and its data (a typed-in weather location). FPP 10.4 and later pass
# FPP_PLUGIN_REINSTALL=1 when this runs as part of a Reinstall: keep them then.
# (FPP 10.3 and earlier don't, so a Reinstall there also clears the settings;
# the README says to download them first.)
if [ "${FPP_PLUGIN_REINSTALL:-}" != "1" ]; then
    rm -f "$MC_MEDIADIR/config/plugin.fpp-showmarquee.json"
    rm -rf "$MC_MEDIADIR/plugindata/fpp-showmarquee"
fi

echo "fpp-showmarquee uninstall complete"
