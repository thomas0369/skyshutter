#!/bin/bash
# auto-pair: continuous scan-driven pairing -- the maker-app experience.
#
# ble-watch (always on) publishes every camera sighting; the moment a Nikon
# camera is FRESH, NEAR and UNBONDED, this service fires the pair.sh-replica
# flow automatically: handshake (no establish) -> LE disconnect -> inquiry ->
# classic pair against the camera's static BR/EDR address. The code popping up
# on the camera display must still be confirmed by a HUMAN (the bt-agent
# auto-confirms our side).
#
# Falle-5a protection (pairing.md): after 3 consecutive failures the service
# sleeps 6 h -- "weitermachen verschlimmert es" is a measured camera trait.
CAM=7C:B8:DA:A6:4F:FE
RSLOG=/tmp/rs.log
LOG=/tmp/autopair.log
cd /home/thomas/projekte_hardware/skyshutter
BW=".venv/bin/python tools/ble-watch.py"

FAILS=0
LASTTRY=0

log() { echo "$(date +%T)  $*" >> "$LOG"; }

# bonded = ANY known camera address carries a bond (the classic identity can
# rotate after unpairing -- measured 23./24.08., four different addresses)
bonded() {
    for D in $(bluetoothctl devices 2>/dev/null | grep -i "P1100" | awk '{print $2}'); do
        bluetoothctl info "$D" 2>/dev/null | grep -q "Paired: yes" && return 0
    done
    return 1
}

# find the camera in a LIVE classic inquiry by its device class 0x080620
# (imaging/camera) -- the same anchor classic-pair.py used on Windows. A fixed
# MAC fails when the identity rotates; the class never lies.
find_camera_classic() {
    timeout 20 hcitool inq 2>/dev/null | grep -i "080620" | head -1 | awk '{print $1}'
}

log "=== auto-pair Dienststart (Ziel $CAM) ==="
while true; do
    if bonded; then
        FAILS=0
        sleep 60
        continue
    fi

    OUT=$($BW status 2>/dev/null)
    [ $? -ne 0 ] && { sleep 10; continue; }

    RSSI=$(echo "$OUT" | sed -n 's/.*rssi=\(-\?[0-9]*\).*/\1/p')
    [ -z "$RSSI" ] && RSSI=0

    NOW=$(date +%s)
    if [ $((NOW - LASTTRY)) -lt 10 ]; then sleep 10; continue; fi
    if [ "$FAILS" -ge 3 ]; then
        log "Falle-5a-Ruhe: 3 Fehlversuche -> 6 h Pause (pairing.md)"
        sleep 21600
        FAILS=0
    fi
    if [ "$RSSI" -lt -80 ]; then sleep 20; continue; fi

    LASTTRY=$NOW
    log "Kamera frisch (rssi $RSSI), kein Bond -> Handshake"
    timeout 90 .venv/bin/python tools/remote-start.py --register skyshutter \
        --hold 0 --wait-for-ad --no-establish > "$RSLOG" 2>&1
    if ! grep -q "registered as" "$RSLOG"; then
        log "  kein auth/registry"
        FAILS=$((FAILS + 1))
        sleep 30
        continue
    fi
    log "  registriert, LE getrennt; 3 s warten (Kamera oeffnet Classic-Seite)"
    sleep 3

    # live classic inquiry; the device cache also lists stale sightings
    TARGET=$(find_camera_classic)
    [ -z "$TARGET" ] && TARGET=$(timeout 22 bluetoothctl scan on 2>&1 | grep -m1 "$CAM" | grep -oE '([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}')
    if [ -z "$TARGET" ]; then
        log "  Kamera nicht live im Inquiry"
        FAILS=$((FAILS + 1))
        continue
    fi
    log "  Inquiry-Treff: $TARGET"

    log "  PAIR -> CODE AM KAMERA-DISPLAY JETZT BESTAETIGEN"
    bluetoothctl trust "$TARGET" >/dev/null 2>&1
    bluetoothctl --timeout 30 pair "$TARGET" >/dev/null 2>&1
    if bonded; then
        log "  BOND_OK -- Kamera gekoppelt, Automat geht in Ruhe"
        FAILS=0
    else
        FAILS=$((FAILS + 1))
        log "  Pair fehlgeschlagen (Versuch $FAILS/3)"
    fi
done
