#!/bin/bash
# FPP command "Show Marquee - Set Target":
#   <Christmas|New Year's Day|Custom> [date YYYY-MM-DD] [time HH:MM] [event name] [repeat yearly true|false]
. "$(dirname "$0")/common.sh"

case "$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    christmas*)   TYPE=christmas ;;
    new*)         TYPE=newyear ;;
    custom)       TYPE=custom ;;
    *) echo "showmarquee: target must be Christmas, New Year's Day or Custom (got '${1:-}')" >&2; exit 1 ;;
esac

BODY="{\"type\": \"$TYPE\""
[ -n "${2:-}" ] && BODY="$BODY, \"date\": $(mc_json_string "$2")"
[ -n "${3:-}" ] && BODY="$BODY, \"time\": $(mc_json_string "$3")"
[ -n "${4:-}" ] && BODY="$BODY, \"name\": $(mc_json_string "$4")"
[ -n "${5:-}" ] && BODY="$BODY, \"repeat\": $(mc_json_string "$5")"
mc_post target "$BODY}" >/dev/null
