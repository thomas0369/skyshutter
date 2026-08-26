#!/bin/bash
# skyshutter stream-wrapper: haelt die Verbindung zur Nikon P1100 und den Stream am Leben

DIR="/home/thomas/projekte_hardware/skyshutter"
VENV="$DIR/.venv"
PYTHON="$VENV/bin/python3"
CREDS_FILE="/tmp/skyshutter_creds.txt"
CAMERA_IP="192.168.0.10"

echo "=== skyshutter stream-wrapper start ==="

while true; do
    CYCLE_START=$(date +%s)

    # Stromausfall-Race (26.08.2026 gemessen): nach kaltem Boot kommt bluetoothd
    # manchmal vor hci0 hoch und sieht dann NIEMALS einen Controller, bis der
    # Daemon neu startet. Jeder BLE-Weckversuch laeuft sonst 90 s ins Leere.
    if [ -z "$(bluetoothctl list 2>/dev/null)" ]; then
        echo "1a. bluetoothd sieht keinen Controller - Neustart des Daemons..."
        sudo -n systemctl restart bluetooth || systemctl restart bluetooth
        sleep 3
    fi

    echo "1. Wecke Kamera ueber BLE (remote-start.py)..."
    # --hold 300 haelt den BLE-Link fuer 5 Minuten, während wir streamen.
    $PYTHON "$DIR/tools/remote-start.py" --register skyshutter --hold 300 > /tmp/remote_start_run.log 2>&1 &
    PID_BLE=$!

    # Warte, bis remote-start DIESEN Lauf mit frischen Creds beliefert hat
    # (die Datei kann von einem frueheren Lauf stammen -- Passwort rotiert je Session).
    # BLE-Handshake dauert bis ~60 s; alte Creds -> Join scheitert garantiert.
    CREDS_READY=false
    for i in $(seq 1 45); do
        if [ -f "$CREDS_FILE" ]; then
            MTIME=$(stat -c %Y "$CREDS_FILE" 2>/dev/null || echo 0)
            if [ "$MTIME" -ge "$CYCLE_START" ]; then
                CREDS_READY=true
                break
            fi
        fi
        sleep 2
    done

    if [ "$CREDS_READY" = true ]; then
        echo "2. Verbinde mit WLAN (Creds frisch von $(date -d @$MTIME '+%H:%M:%S')) ..."

        # Join-Versuche: Creds JE VERSUCH neu lesen (rotieren ggf. nach), SSID muss sichtbar sein.
        CONNECTED=false
        for i in $(seq 1 20); do
            SSID=$(sed -n '1p' "$CREDS_FILE")
            PASS=$(sed -n '2p' "$CREDS_FILE")
            if [ -z "$SSID" ] || [ -z "$PASS" ]; then
                sleep 3
                continue
            fi
            if nmcli device wifi connect "$SSID" password "$PASS" >/dev/null 2>&1; then
                echo "WLAN erfolgreich verbunden (Versuch $i)."
                CONNECTED=true
                break
            fi
            sleep 3
        done

        if [ "$CONNECTED" = true ]; then
            # Pruefe, ob wir die Kamera pingen koennen
            if ping -c 2 "$CAMERA_IP" > /dev/null 2>&1; then
                echo "3. Starte skyshutter stream auf Port 8080 (full res)..."
                # Full resolution (1552x1162, ~60 kB, ~6 fps measured 26.08.):
                # NO --remote here -- ControlMode 1 would shrink frames to
                # 640x480. Astro framing wants the pixels.
                # --keepalive-secs 25: measured 26.08. -- pure frame pulling
                # dies after ~55 s (auto power off); a GetEvent poll resets it.
                # -v: INFO so keepalive polls land in the journal.
                $PYTHON -m skyshutter.cli -v --host "$CAMERA_IP" stream --bind 0.0.0.0 --http-port 8080 --fps 6 --keepalive-secs 25
                echo "Stream-Server beendet."
            else
                echo "Kamera-IP $CAMERA_IP ist nicht pingbar. Starte neu..."
            fi
        else
            echo "WLAN-Verbindung fehlgeschlagen."
        fi
    else
        echo "Keine frischen Zugangsdaten in $CREDS_FILE (BLE Handshake fehlgeschlagen?)."
    fi

    # Aufraeumen: Toete den BLE-Hold-Prozess, falls er noch laeuft
    if kill -0 $PID_BLE > /dev/null 2>&1; then
        echo "Toete BLE-Hold-Prozess ($PID_BLE)..."
        kill $PID_BLE
        sleep 2
        kill -9 $PID_BLE 2>/dev/null
    fi

    # Zombie-LE-Links aufloesen (kill -9 hinterlaesst offene Verbindungen,
    # die die Kamera am erneuten Advertising hindern -- gemessen 25.08.).
    # NUR die rotierende RPA (Alias P1100) trennen, NIE den Classic-Bond 7C:B8:DA:A6:4F:FE.
    for RPA in $(bluetoothctl devices Connected 2>/dev/null | grep 'P1100' | awk '{print $2}'); do
        if [ "$RPA" != "7C:B8:DA:A6:4F:FE" ]; then
            echo "Loese Zombie-LE-Link $RPA ..."
            bluetoothctl disconnect "$RPA" >/dev/null 2>&1
            bluetoothctl remove "$RPA" >/dev/null 2>&1
        fi
    done

    echo "Warte 5 Sekunden vor dem naechsten Versuch..."
    sleep 5
done
