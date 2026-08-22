#!/bin/bash
# Kopplung mit der Kamera. Zwei Schritte, klare Ansagen dazwischen.
#
# Zeitbedarf, gemessen am 22.08.2026 um 21:56: 40 Sekunden vom Reset bis zum
# Bond, davon 25 s Funk-Hochlauf. Der eigentliche Vorgang dauert 15 Sekunden.
# Alles andere ist Warten darauf, dass jemand am Geraet steht -- deshalb sagt
# das Skript deutlich, wann das noetig ist.
PY='/mnt/c/Users/thoma/AppData/Local/Programs/Python/Python312/python.exe'
PS=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
BT='C:\Users\thoma\AppData\Local\Temp\bt_state.ps1'
cd /mnt/c/Users/thoma/AppData/Local/Temp || exit 1

banner() { echo; echo "################ $* ################"; echo; }

banner "0/2  BLUETOOTH-RESET  ($(date +%H:%M:%S))"
# Ohne den scheiterten fuenf Anlaeufe in Folge: der Windows-Stack findet dann
# gar nichts mehr, auch keine Geraete, die klar in Reichweite sind.
"$PS" -NoProfile -ExecutionPolicy Bypass -File "$BT" -Action Off 2>&1 | tr -d '\r' | tail -1
"$PS" -NoProfile -ExecutionPolicy Bypass -File "$BT" -Action On  2>&1 | tr -d '\r' | tail -1
sleep 14

banner ">>> JETZT: Kameramenue 'Mit Smartgeraet verbinden' oeffnen <<<"

banner "1/2  BLE-HANDSHAKE  ($(date +%H:%M:%S))"
"$PY" -u ble-probe.py --retries 40 --timeout 6 pairing --quick --register skyshutter 2>&1 \
  | tr -d '\r' | grep -vE "^  scan |^  [0-9a-f]{4} " | tee /tmp/handshake-out.txt

if ! grep -q "registered as" /tmp/handshake-out.txt; then
  banner "ABGEBROCHEN: Handshake fehlgeschlagen  ($(date +%H:%M:%S))"
  exit 1
fi
DEVICE=$(grep -oE "device=[0-9a-f]{8}" /tmp/handshake-out.txt | tail -1 | cut -d= -f2)
NONCE=$(grep -oE "nonce=[0-9a-f]{8}" /tmp/handshake-out.txt | tail -1 | cut -d= -f2)

banner ">>> JETZT: auf die Kamera schauen, bei Code sofort OK druecken <<<"

banner "2/2  KLASSISCHES BONDING  ($(date +%H:%M:%S))"
"$PY" -u classic-pair.py --seconds 45 pair 2>&1 | tr -d '\r' | tee /tmp/bond-out.txt

if ! grep -q "result: PAIRED" /tmp/bond-out.txt; then
  banner "ABGEBROCHEN: $(grep -oE 'result: [A-Z_]+' /tmp/bond-out.txt | tail -1)  ($(date +%H:%M:%S))"
  echo "  Scheitern zwei, drei Versuche hintereinander, hilft Weitermachen nicht."
  echo "  Gemessen: nach sechs Stunden Funkruhe lief derselbe Ablauf beim ersten"
  echo "  Versuch durch. Siehe docs/pairing.md, Falle 5a."
  exit 1
fi

banner "FERTIG  ($(date +%H:%M:%S))  --  die Kamera sollte 'connected' melden"

# Der Reconnect gehoert NICHT zum Normalweg. Gemessen am 22.08. um 21:57: die
# Kamera advertised danach nicht mehr, weil die Verbindung schon steht -- der
# Versuch lief ins Leere, und gekoppelt war sie trotzdem. Er bleibt hier nur
# als Reparatur stehen, fuer den Fall dass die Kamera haengenbleibt.
cat <<EOF

  Bleibt die Kamera auf "Establishing connection" stehen:
  Menue erneut oeffnen und den Reconnect nachschieben --

    "\$PY" -u ble-probe.py --retries 15 --timeout 6 pairing --quick \\
          --device $DEVICE --nonce $NONCE
EOF
