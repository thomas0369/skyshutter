#!/bin/bash
# tracker-on/off: run star_tracker as a background process with the night
# profile. Usage: tracker-on.sh [-- extra args]
# Config: /etc/skyshutter-tracker.conf (TRACKER_ARGS=...) falls vorhanden.
set -u
DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG=/tmp/star_tracker.log
CONF=/etc/skyshutter-tracker.conf

TRACKER_ARGS="--duration 3600 --zmq"
[ -f "$CONF" ] && . "$CONF"

mkdir -p /tmp
nohup python3 "$DIR/tools/cv/star_tracker.py" $TRACKER_ARGS "$@" >> "$LOG" 2>&1 &
echo $! > /tmp/star_tracker.pid
echo "tracker running: pid $(cat /tmp/star_tracker.pid), args: $TRACKER_ARGS $*"
echo "log: $LOG (tail -f zum Zuschauen), stop: $0/../tracker-off.sh"
