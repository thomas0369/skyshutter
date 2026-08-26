#!/bin/bash
# Stoppt den Hintergrund-star_tracker (PID-Datei, sanft).
set -u
PIDFILE=/tmp/star_tracker.pid
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if kill "$PID" 2>/dev/null; then
        echo "tracker $PID gestoppt"
    else
        echo "tracker $PID lief nicht mehr"
    fi
    rm -f "$PIDFILE"
else
    echo "kein PID-File -- laeuft der Tracker?"
fi
