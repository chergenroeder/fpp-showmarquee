#!/bin/bash
# fpp-showmarquee callbacks
#
# The plugin needs no playlist or media callbacks, but FPP only registers a
# plugin's commands/descriptions.json at install time, without an fppd
# restart, when the plugin has a callbacks script declaring at least one
# callback type. Declare "lifecycle" and do nothing with it: the daemon is
# started and stopped by scripts/postStart.sh and scripts/preStop.sh.

case "$1" in
    --list)
        echo "lifecycle"
        ;;
esac
exit 0
