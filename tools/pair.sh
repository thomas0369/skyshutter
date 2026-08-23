#!/bin/bash
# Kopplung mit der Kamera. Zwei Schritte, klare Ansagen dazwischen.
#
# Zeitbedarf, gemessen am 22.08.2026 um 21:56: 40 Sekunden vom Reset bis zum
# Bond, davon 25 s Funk-Hochlauf. Der eigentliche Vorgang dauert 15 Sekunden.
# Alles andere ist Warten darauf, dass jemand am Geraet steht -- deshalb sagt
# das Skript deutlich, wann das noetig ist.
#
# VORAUSSETZUNGEN
#   * WSL unter Windows. Die Bluetooth-Werkzeuge laufen unter dem
#     WINDOWS-Python, weil WSL keinen Bluetooth-Zugang hat.
#   * Dort installiert: pip install bleak pycryptodome winrt-runtime
#     winrt-Windows.Devices.Bluetooth winrt-Windows.Devices.Enumeration
#   * Die Kamera ist noch nicht gekoppelt. Steht sie schon in der Geraeteliste,
#     erst auf beiden Seiten loeschen -- siehe docs/pairing.md.
#
# ANPASSEN, falls das Windows-Python woanders liegt:
#   SKYSHUTTER_WINPY=/mnt/c/.../python.exe bash tools/pair.sh
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)

# Windows-Python finden: Umgebungsvariable schlaegt alles, sonst die ueblichen
# Orte durchgehen. Ein hartkodierter Benutzerpfad waere hier eine Falle fuer
# jeden ausser dem Autor.
find_windows_python() {
  if [ -n "${SKYSHUTTER_WINPY:-}" ]; then echo "$SKYSHUTTER_WINPY"; return; fi
  local base="/mnt/c/Users/${USER:-$(whoami)}/AppData/Local/Programs/Python"
  for candidate in \
      "$base"/Python3*/python.exe \
      /mnt/c/Users/*/AppData/Local/Programs/Python/Python3*/python.exe \
      /mnt/c/Python3*/python.exe ; do
    [ -x "$candidate" ] && { echo "$candidate"; return; }
  done
}

PY=$(find_windows_python)
PS=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe

if [ -z "$PY" ] || [ ! -x "$PY" ]; then
  echo "Kein Windows-Python gefunden." >&2
  echo "Setze SKYSHUTTER_WINPY auf den Pfad zu python.exe und starte neu." >&2
  exit 1
fi
if [ ! -x "$PS" ]; then
  echo "PowerShell nicht gefunden -- dieses Skript braucht WSL unter Windows." >&2
  exit 1
fi

# Windows-Programme koennen nicht aus einem WSL-Pfad heraus arbeiten. Deshalb
# eine Arbeitskopie im Windows-Temp anlegen und von dort starten.
WORK=$(mktemp -d /mnt/c/Users/*/AppData/Local/Temp/skyshutter-XXXXXX 2>/dev/null) \
  || WORK=$(mktemp -d)
cp "$HERE"/ble-probe.py "$HERE"/classic-pair.py "$HERE"/nikon_pairing.py \
   "$HERE"/bt_state.ps1 "$WORK"/ 2>/dev/null
WORK_WIN=$(wslpath -w "$WORK" 2>/dev/null || echo "$WORK")
cd "$WORK" || exit 1
trap 'rm -rf "$WORK"' EXIT

banner() { echo; echo "################ $* ################"; echo; }

banner "0a/2  ALTE KOPPLUNG PRUEFEN  ($(date +%H:%M:%S))"
# Gemessen am 23.08.2026: Ein Bond, den nur Windows noch kennt, macht die Kamera
# fuer den Inquiry unsichtbar -- der sucht ausschliesslich UNGEPAARTE Geraete.
# Das Symptom ist ein stiller Suchlauf, die Ursache sieht voellig anders aus.
# Zwanzig Minuten gekostet, bevor jemand nachgesehen hat.
"$PY" -u classic-pair.py --seconds 12 status 2>&1 | tr -d '\r' | tee "$WORK/status.txt"

if grep -q "STALE BOND" "$WORK/status.txt"; then
  banner ">>> ALTE KOPPLUNG GEFUNDEN <<<"
  echo "  Windows loest sie gleich selbst."
  echo "  AN DER KAMERA aber ebenfalls loeschen:"
  echo "    Netzwerkmenue -> Bluetooth -> Gekoppelte Geraete -> 'skyshutter' entfernen"
  echo
  echo "  Sonst behandelt die Kamera diesen Rechner als bekannt und oeffnet ihre"
  echo "  klassische Seite gar nicht erst."
  echo
  read -r -p "  Enter druecken, wenn der Eintrag an der Kamera geloescht ist ... " _
  "$PY" -u classic-pair.py --seconds 15 forget 2>&1 | tr -d '\r' | tail -2
fi

banner "0/2  BLUETOOTH-RESET  ($(date +%H:%M:%S))"
# Ohne den scheiterten fuenf Anlaeufe in Folge: der Windows-Stack findet dann
# gar nichts mehr, auch keine Geraete, die klar in Reichweite sind.
"$PS" -NoProfile -ExecutionPolicy Bypass -File "$WORK_WIN\\bt_state.ps1" -Action Off 2>&1 | tr -d '\r' | tail -1
"$PS" -NoProfile -ExecutionPolicy Bypass -File "$WORK_WIN\\bt_state.ps1" -Action On  2>&1 | tr -d '\r' | tail -1
sleep 14

banner ">>> JETZT: Kameramenue 'Mit Smartgeraet verbinden' oeffnen <<<"

banner "1/2  BLE-HANDSHAKE  ($(date +%H:%M:%S))"
"$PY" -u ble-probe.py --retries 40 --timeout 6 pairing --quick --register skyshutter 2>&1 \
  | tr -d '\r' | grep -vE "^  scan |^  [0-9a-f]{4} " | tee "$WORK/handshake.txt"

if ! grep -q "registered as" "$WORK/handshake.txt"; then
  banner "ABGEBROCHEN: Handshake fehlgeschlagen  ($(date +%H:%M:%S))"
  echo "  Meldet der Scan nur 'silent', ist das Kameramenue zu."
  exit 1
fi
DEVICE=$(grep -oE "device=[0-9a-f]{8}" "$WORK/handshake.txt" | tail -1 | cut -d= -f2)
NONCE=$(grep -oE "nonce=[0-9a-f]{8}" "$WORK/handshake.txt" | tail -1 | cut -d= -f2)

banner ">>> JETZT: auf die Kamera schauen, bei Code sofort OK druecken <<<"

banner "2/2  KLASSISCHES BONDING  ($(date +%H:%M:%S))"
"$PY" -u classic-pair.py --seconds 45 pair 2>&1 | tr -d '\r' | tee "$WORK/bond.txt"

if ! grep -q "result: PAIRED" "$WORK/bond.txt"; then
  banner "ABGEBROCHEN: $(grep -oE 'result: [A-Z_]+' "$WORK/bond.txt" | tail -1)  ($(date +%H:%M:%S))"
  echo "  Scheitern zwei, drei Versuche hintereinander, hilft Weitermachen nicht."
  echo "  Gemessen: nach sechs Stunden Funkruhe lief derselbe Ablauf beim ersten"
  echo "  Versuch durch. Siehe docs/pairing.md, Falle 5a."
  exit 1
fi

banner "FERTIG  ($(date +%H:%M:%S))  --  die Kamera sollte 'connected' melden"
echo "  Kennung dieser Kopplung:  device=$DEVICE  nonce=$NONCE"
echo "  Notieren -- der Reconnect und der WLAN-Start brauchen sie."

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
