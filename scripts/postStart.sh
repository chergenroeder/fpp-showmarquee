#!/bin/bash
# Called by FPP after fppd starts (FPP 10+ bare metal boot path)

. "$(dirname "$0")/daemon_lib.sh"

mc_start_daemon
