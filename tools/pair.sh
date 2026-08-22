#!/bin/bash
# Kopplung mit der Kamera. Drei Schritte, klare Ansagen dazwischen.
#
# Zeitbedarf, gemessen: sobald die Kamera erreichbar ist, dauert der ganze
# Vorgang rund 16 Sekunden. Alles andere ist Warten darauf, dass jemand am
# Geraet steht -- deshalb sagt das Skript deutlich, wann das noetig ist.
PY='/mnt/c/Users/thoma/AppData/Local/Programs/Python/Python312/python.exe'
PS=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
BT='C:\Users\thoma\AppData\Local\Temp\bt_state.ps1'
cd /mnt/c/Users/thoma/AppData/Local/Temp || exit 1

banner() { echo; echo "################ $* ################"; echo; }

banner "0/3  BLUETOOTH-RESET  ($(date +%H:%M:%S))"
# Ohne den scheiterten fuenf Anlaeufe in Folge: der Windows-Stack findet dann
# gar nichts mehr, auch keine Geraete, die klar in Reichweite sind.
"$PS" -NoProfile -ExecutionPolicy Bypass -File "$BT" -Action Off 2>&1 | tr -d '\r' | tail -1
"$PS" -NoProfile -ExecutionPolicy Bypass -File "$BT" -Action On  2>&1 | tr -d '\r' | tail -1
sleep 14

banner ">>> JETZT: Kameramenue 'Mit Smartgeraet verbinden' oeffnen <<<"

banner "1/3  BLE-HANDSHAKE  ($(date +%H:%M:%S))"
"$PY" -u ble-probe.py --retries 40 --timeout 6 pairing --quick --register skyshutter 2>&1 \
  | tr -d '\r' | grep -vE "^  scan |^  [0-9a-f]{4} " | tee /tmp/handshake-out.txt

if ! grep -q "registered as" /tmp/handshake-out.txt; then
  banner "ABGEBROCHEN: Handshake fehlgeschlagen  ($(date +%H:%M:%S))"
  exit 1
fi
DEVICE=$(grep -oE "device=[0-9a-f]{8}" /tmp/handshake-out.txt | tail -1 | cut -d= -f2)
NONCE=$(grep -oE "nonce=[0-9a-f]{8}" /tmp/handshake-out.txt | tail -1 | cut -d= -f2)

banner ">>> JETZT: auf die Kamera schauen, bei Code sofort OK druecken <<<"

banner "2/3  KLASSISCHES BONDING  ($(date +%H:%M:%S))"
"$PY" -u classic-pair.py --seconds 45 pair 2>&1 | tr -d '\r' | tee /tmp/bond-out.txt

if ! grep -q "result: PAIRED" /tmp/bond-out.txt; then
  banner "ABGEBROCHEN: $(grep -oE 'result: [A-Z_]+' /tmp/bond-out.txt | tail -1)  ($(date +%H:%M:%S))"
  exit 1
fi

# Nach dem Bestaetigen verlaesst die Kamera den Advertising-Modus. Fuer den
# Reconnect muss das Menue deshalb noch einmal geoeffnet werden -- ohne diesen
# Hinweis laeuft Schritt 3 zwei Minuten ins Leere.
banner ">>> JETZT: Kameramenue ERNEUT oeffnen (fuer den Abschluss) <<<"

banner "3/3  RECONNECT  ($(date +%H:%M:%S))  device=$DEVICE nonce=$NONCE"
"$PY" -u ble-probe.py --retries 15 --timeout 6 pairing --quick \
      --device "$DEVICE" --nonce "$NONCE" 2>&1 | tr -d '\r' | grep -vE "^  scan |^  [0-9a-f]{4} " \
  | tee /tmp/reconnect-out.txt

if grep -q "authenticated" /tmp/reconnect-out.txt; then
  banner "FERTIG - die Kamera sollte 'connected' melden  ($(date +%H:%M:%S))"
else
  banner "GEKOPPELT, aber Reconnect offen - Menue oeffnen und wiederholen:"
  echo "  \"\$PY\" -u ble-probe.py --retries 15 --timeout 6 pairing --quick \\"
  echo "        --device $DEVICE --nonce $NONCE"
fi
