#!/bin/bash
# FPP command "Show Marquee - Output": <On|Off|Toggle> turns the whole sign on or off
. "$(dirname "$0")/common.sh"

STATE=$(mc_state "${1:-On}") || exit 1
mc_post output "{\"enable_output\": $STATE}" >/dev/null
