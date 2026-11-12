#!/bin/bash
# FPP command "Show Marquee - Countdown": <On|Off|Toggle> turns the countdown page on or off
. "$(dirname "$0")/common.sh"

STATE=$(mc_state "${1:-On}") || exit 1
mc_post state "{\"enabled\": $STATE}" >/dev/null
