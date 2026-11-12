#!/bin/bash
# Shared by the FPP command scripts (sourced, not run). fppd runs a command
# script with only MEDIADIR/FPPDIR/SCRIPTDIR set and waits for it to finish -
# with the scheduler, MultiSync and other commands waiting too - so set PATH
# and keep every request short.
#
# Requests go straight to the plugin's own daemon on 127.0.0.1, not through
# FPP's web server: a stopped daemon then fails at once, and the worst case
# (a daemon that accepts but never answers) is the 2 s --max-time below.

export PATH=/usr/local/bin:/usr/bin:/bin

MC_API="${MC_API:-http://127.0.0.1:32330/api/plugin/showmarquee}"

# mc_post <endpoint> <json body>; prints the daemon's reply, fails on an error
mc_post() {
    local out
    out=$(curl -s --connect-timeout 1 --max-time 2 -X POST "$MC_API/$1" \
          -H 'Content-Type: application/json' -d "$2" -w '\n%{http_code}') \
        || { echo "showmarquee: $1 request failed (daemon not running?)" >&2; return 1; }
    local code="${out##*$'\n'}" body="${out%$'\n'*}"
    if [ "$code" != "200" ]; then
        echo "showmarquee: $1: $body" >&2
        return 1
    fi
    echo "$body"
}

# mc_state <On|Off|Toggle>  ->  true | false | "toggle" (JSON)
mc_state() {
    case "$(echo "$1" | tr '[:upper:]' '[:lower:]')" in
        on|true|1)   echo true ;;
        off|false|0) echo false ;;
        toggle)      echo '"toggle"' ;;
        *) echo "showmarquee: state must be On, Off or Toggle (got '$1')" >&2; return 1 ;;
    esac
}

# mc_json_string <text>  ->  the text as a JSON string
mc_json_string() {
    python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$1"
}
