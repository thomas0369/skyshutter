#!/usr/bin/env bash
# Run the Phase 1 measurements while this machine is joined to the camera's
# access point, without anyone watching the terminal.
#
# The problem it solves: joining the camera AP drops the home network, so the
# session that would normally drive skyshutter is gone. This script waits for
# the network to change, measures, and waits for it to come back.
#
# Usage:  bash tools/first-contact.sh
# Output: measurements/first-contact-<timestamp>.txt  (plus a redacted copy)

set -uo pipefail

cd "$(dirname "$0")/.."

SKYSHUTTER=${SKYSHUTTER:-.venv/bin/skyshutter}
CAMERA_HOST=${CAMERA_HOST:-192.168.1.1}   # override to dry-run against the simulator
WAIT_FOR_SWITCH=${WAIT_FOR_SWITCH:-300}   # seconds to wait for the camera network
WAIT_FOR_RETURN=${WAIT_FOR_RETURN:-600}   # seconds to wait for the home network
NETSH=/mnt/c/Windows/System32/netsh.exe

if [ ! -x "$SKYSHUTTER" ]; then
    echo "no skyshutter at $SKYSHUTTER — run: .venv/bin/pip install -e '.[dev]'" >&2
    exit 1
fi

mkdir -p measurements
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="measurements/first-contact-$STAMP.txt"

current_ssid() {
    [ -x "$NETSH" ] || return 1
    "$NETSH" wlan show interfaces 2>/dev/null \
        | awk -F': ' '/^ *SSID *:/ { gsub(/\r/, "", $2); print $2; exit }'
}

# The home gateway may live at the same address the camera uses as an access
# point. Its MAC is what tells the two apart.
gateway_mac() {
    local gw
    gw=$(ip route show default | awk '/default/ { print $3; exit }')
    [ -n "$gw" ] || return 1
    ping -c1 -W1 "$gw" >/dev/null 2>&1
    ip neigh show "$gw" | awk '/lladdr/ { print $5; exit }'
}

# Record every command with its exit status, so a failure is still a measurement.
run() {
    echo "" >>"$OUT"
    echo "\$ $*" >>"$OUT"
    "$@" >>"$OUT" 2>&1
    local rc=$?
    echo "[exit $rc]" >>"$OUT"
    return $rc
}

HOME_SSID=$(current_ssid || true)
HOME_GW_MAC=$(gateway_mac || true)

{
    echo "skyshutter first contact — $STAMP"
    echo "home SSID at start: ${HOME_SSID:-<unknown>}"
    echo "home gateway MAC:   ${HOME_GW_MAC:-<unknown>}"
    echo "host address:       $(ip -4 -br addr show scope global | tr -s ' ' | tr '\n' ' ')"
} >"$OUT"

echo "Messprotokoll: $OUT"

if [ -n "$HOME_SSID" ]; then
    echo "Warte bis zu $WAIT_FOR_SWITCH s darauf, dass du das WLAN von '$HOME_SSID' auf den"
    echo "Kamera-AP wechselst. Jetzt umschalten."
    waited=0
    while [ "$waited" -lt "$WAIT_FOR_SWITCH" ]; do
        now=$(current_ssid || true)
        if [ -n "$now" ] && [ "$now" != "$HOME_SSID" ]; then
            echo "Kamera-Netz erkannt: $now"
            echo "camera SSID: $now" >>"$OUT"
            sleep 5   # let DHCP settle
            break
        fi
        sleep 3
        waited=$((waited + 3))
    done
    if [ "$waited" -ge "$WAIT_FOR_SWITCH" ]; then
        echo "Kein WLAN-Wechsel innerhalb von $WAIT_FOR_SWITCH s — messe trotzdem." | tee -a "$OUT"
    fi
else
    # No Windows interop: fall back to a fixed grace period.
    echo "SSID nicht auslesbar. Wechsle jetzt das WLAN, ich messe in 60 s."
    sleep 60
fi

NOW_GW_MAC=$(gateway_mac || true)
{
    echo "addresses after switch: $(ip -4 -br addr show scope global | tr -s ' ' | tr '\n' ' ')"
    echo "gateway MAC now:        ${NOW_GW_MAC:-<unknown>}"
} >>"$OUT"

# Without this check an open port 80 on the home router reads like a camera.
if [ -n "$HOME_GW_MAC" ] && [ "$NOW_GW_MAC" = "$HOME_GW_MAC" ]; then
    WARN="WARNUNG: Gateway-MAC unverändert — dies ist noch das Heimnetz, nicht die Kamera.
Alles unterhalb dieser Zeile beschreibt den Router, nicht die P1100."
    echo "$WARN" | tee -a "$OUT"
fi

echo "Messe gegen $CAMERA_HOST ..."
run "$SKYSHUTTER" probe
run "$SKYSHUTTER" --host "$CAMERA_HOST" probe --ports 15740 80 8080 443 49152 5000
run "$SKYSHUTTER" --host "$CAMERA_HOST" info
run "$SKYSHUTTER" --host "$CAMERA_HOST" raw 0x1001 -o "measurements/deviceinfo-$STAMP.bin"

echo "Messung fertig."

# A redacted copy is what goes into the public repo: DeviceInfo carries the
# camera's serial number, and the camera AP's SSID identifies the device.
RED="measurements/first-contact-$STAMP-redacted.txt"
sed -E 's/^(serial +).*/\1<redacted>/; s/^(camera SSID: ).*/\1<redacted>/' "$OUT" >"$RED"
echo "Geschwärzte Fassung für den Commit: $RED"

if [ -n "$HOME_SSID" ]; then
    echo "Warte bis zu $WAIT_FOR_RETURN s auf die Rückkehr ins Heimnetz '$HOME_SSID'."
    waited=0
    while [ "$waited" -lt "$WAIT_FOR_RETURN" ]; do
        [ "$(current_ssid || true)" = "$HOME_SSID" ] && { echo "Wieder im Heimnetz."; break; }
        sleep 3
        waited=$((waited + 3))
    done
fi

echo
echo "Diese Datei zurückmelden:  $RED"
