#!/bin/bash
# Called by FPP before fppd stops (FPP 10+ bare metal boot path)

. "$(dirname "$0")/daemon_lib.sh"

mc_stop_daemon
echo "showmarquee stopped"
