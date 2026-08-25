#!/bin/bash
# auto-measure: wartet auf Kamera-Advertising, faehrt dann die volle Kette:
# remote-start (AP) -> WLAN-Join -> probe (ControlMode 1 + Live-View-Timing)
# Ergebnis nach /tmp/measure_result.txt
OUT=/tmp/measure_result.txt
cd /home/thomas/projekte_hardware/skyshutter
: > "$OUT"

log() { echo "$(date +%T)  $*" | tee -a "$OUT"; }

log "=== auto-measeure wartet auf Kamera ==="
for i in $(seq 1 120); do
    FRESH=$(python3 -c "
import json,time
try:
    d=json.load(open('/tmp/camera_seen.json'))
    print('1' if time.time()-d['ts']<30 else '0')
except: print('0')
")
    [ "$FRESH" = "1" ] && break
    sleep 5
done
[ "$FRESH" = "1" ] || { log "Timeout: Kamera sendete in 10 Min nicht"; exit 1; }
log "Kamera frisch -> remote-start"

.venv/bin/python tools/remote-start.py --register skyshutter --hold 600 >> "$OUT" 2>&1 &
RSPID=$!
sleep 12

JOINED=0
SSID="$(sed -n '1p' /tmp/skyshutter_creds.txt)"
for i in $(seq 1 12); do
    if nmcli dev wifi connect "$SSID" password "$(sed -n '2p' /tmp/skyshutter_creds.txt)" 2>/dev/null; then
        JOINED=1; break
    fi
    sleep 3
done
[ "$JOINED" = "1" ] && log "WLAN-Join OK" || { log "WLAN-Join FAIL"; kill $RSPID; exit 1; }

if ping -c1 -W2 192.168.0.10 >/dev/null 2>&1; then
    log "Kamera pingbar -> Messung startet"
    python3 /tmp/probe_mode.py >> "$OUT" 2>&1
    log "=== Messung fertig ==="
else
    log "Kamera nicht pingbar"
fi
kill $RSPID 2>/dev/null
