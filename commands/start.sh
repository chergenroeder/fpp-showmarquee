#!/bin/bash
# FPP command "Show Marquee - Start": start the plugin's background program if it
# isn't running. fppd runs command scripts as root, which the program needs (it
# writes into the overlay buffer fppd creates) with no extra privileges. The
# settings page's Start button runs this command through FPP's command API.
export PATH=/usr/local/bin:/usr/bin:/bin
. "$(dirname "$0")/../scripts/daemon_lib.sh"
mc_start_daemon >/dev/null
