#!/bin/bash
# FPP command "Matrix Countdown - State": <On|Off|Toggle>
. "$(dirname "$0")/common.sh"

STATE=$(mc_state "${1:-On}") || exit 1
mc_post state "{\"enabled\": $STATE}" >/dev/null
