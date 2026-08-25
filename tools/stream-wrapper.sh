#!/bin/bash
# skyshutter stream-wrapper: hält die Verbindung zur Nikon P1100 und den Stream am Leben

DIR="/home/thomas/projekte_hardware/skyshutter"
VENV="$DIR/.venv"
PYTHON="$VENV/bin/python3"
CREDS_FILE="/tmp/skyshutter_creds.txt"
CAMERA_IP="192.168.0.10"

echo "=== skyshutter stream-wrapper start ==="

while true; do
    echo "1. Wecke Kamera über BLE (remote-start.py)..."
    # Führe remote-start.py im Vordergrund aus, um den AP zu triggern und Creds zu schreiben.
    # --hold 300 hält den BLE-Link für 5 Minuten, während wir streamen.
    $PYTHON "$DIR/tools/remote-start.py" --register skyshutter --hold 300 > /tmp/remote_start_run.log 2>&1 &
    PID_BLE=$!

    # Warte kurz, bis remote-start die Zugangsdaten generiert
    sleep 10

    if [ -f "$CREDS_FILE" ]; then
        SSID=$(sed -n '1p' "$CREDS_FILE")
        PASS=$(sed -n '2p' "$CREDS_FILE")
        echo "2. Verbinde mit WLAN SSID: $SSID ..."
        
        # Versuche 10-mal, das WLAN zu verbinden
        CONNECTED=false
        for i in {1..10}; do
            if nmcli device wifi connect "$SSID" password "$PASS"; then
                echo "WLAN erfolgreich verbunden."
                CONNECTED=true
                break
            fi
            sleep 3
        done

        if [ "$CONNECTED" = true ]; then
            # Prüfe, ob wir die Kamera pingen können
            if ping -c 2 "$CAMERA_IP" > /dev/null 2>&1; then
                echo "3. Starte skyshutter stream auf Port 8080..."
                # Starte den Stream. Wenn er abstürzt, bricht die Schleife ab und wir fangen von vorne an.
                $PYTHON -m skyshutter.cli --host "$CAMERA_IP" stream --bind 0.0.0.0 --http-port 8080
                echo "Stream-Server beendet."
            else
                echo "Kamera-IP $CAMERA_IP ist nicht pingbar. Starte neu..."
            fi
        else
            echo "WLAN-Verbindung fehlgeschlagen."
        fi
    else
        echo "Keine Zugangsdaten in $CREDS_FILE gefunden (BLE Handshake fehlgeschlagen?)."
    fi

    # Aufräumen: Töte den BLE-Hold-Prozess, falls er noch läuft
    if kill -0 $PID_BLE > /dev/null 2>&1; then
        echo "Töte BLE-Hold-Prozess ($PID_BLE)..."
        kill -9 $PID_BLE
    fi

    echo "Warte 5 Sekunden vor dem nächsten Versuch..."
    sleep 5
done
