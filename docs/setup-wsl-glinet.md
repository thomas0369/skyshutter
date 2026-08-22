# Setup: Windows + WSL Ubuntu + GL.iNet Mini-Router

Konkrete Anleitung für die vorhandene Hardware. Ersetzt für diesen Aufbau die
allgemeine Variantentabelle in [plan.md](plan.md), Abschnitt 2.

## Hardware

* Windows-Laptop mit WSL Ubuntu (eingebautes WLAN + USB-Ethernet-Adapter)
* GL.iNet 300M Mini Smart Router (Mango, GL-MT300N-V2) am USB-Ethernet
* Coolpix P1100

## Die entscheidende Überlegung: wer redet mit der Kamera?

> **Gemessen am 22.08.2026 — die ursprüngliche Sorge war unbegründet.** Der
> Kamera-AP läuft mit **WPA2-PSK auf Kanal 6**, nicht mit WPA3-SAE, und die
> Kamera nimmt sich selbst die Adresse **192.168.0.10**. Nikons WPA3-Angabe
> betrifft diesen Modus nicht. Damit kann auch der Mango ins Kamera-Netz, und
> Variante 2 ist ohne Vorbehalt benutzbar.

Naheliegend wäre, den Mango ins Kamera-WLAN zu hängen. Der Grund, es zunächst
anders herum zu planen, war die Annahme, die Kamera verlange WPA3-SAE — was der
Mango nicht kann (GL.iNet hat es auf dieser Hardware mit Firmware 3.215
deaktiviert, für 4.x unbestätigt). Diese Annahme ist widerlegt.

Der umgekehrte Aufbau bleibt trotzdem der bequemere: **Das Laptop-WLAN geht zur
Kamera**, **der Mango liefert das Internet** aus dem Heim-WLAN. Sobald
mitgeschnitten werden soll, lohnt der Wechsel zu Variante 2.

## Variante 1 — der Alltagsaufbau (empfohlen)

```
Kamera (AP, 192.168.0.10)  ←── WLAN ──  Laptop  ── USB-Ethernet ──→ Mango ──→ Heim-WLAN → Internet
```

**1. Mango als Repeater ins Heim-WLAN.** Weboberfläche unter `http://192.168.8.1`,
Internet → Repeater → Heim-SSID wählen. Der Mango bleibt auf `192.168.8.1`, der
Laptop bekommt per DHCP `192.168.8.x`.

**2. USB-Ethernet** in einen LAN-Port des Mango. Prüfen: `ping 8.8.8.8` geht.

**3. Interface-Metriken festlegen**, damit die Kamera später nicht die
Default-Route an sich reißt. PowerShell als Administrator:

```powershell
Get-NetIPInterface -AddressFamily IPv4 | Sort-Object InterfaceMetric
Set-NetIPInterface -InterfaceAlias "Ethernet" -InterfaceMetric 10
Set-NetIPInterface -InterfaceAlias "WLAN"     -InterfaceMetric 60
```

Die Namen können abweichen — die erste Zeile zeigt die tatsächlichen Aliase.
Niedrigere Metrik gewinnt, also: Internet über Ethernet, Kamera über WLAN.

**4. Laptop-WLAN mit dem Kamera-AP verbinden**, sobald die Kamera im
Fernsteuerungsmodus ist.

**Prüfen — beides muss gleichzeitig gehen:**

```powershell
ping 192.168.0.10          # Kamera
curl.exe https://ifconfig.me   # Internet
```

Klappt nur eins von beiden, stimmen die Metriken nicht.

## Variante 2 — für Mitschnitte, später

Erst relevant, wenn ein Paketmitschnitt gebraucht wird (Phase 1b). Dann hängt der
Mango im Kamera-WLAN und schneidet mit. Die WPA2-Frage ist geklärt — die Kamera
bietet WPA2-PSK an, der Mango kommt hinein.

Zwei Details, die dir Ärger sparen:

**Keine statische Route, sondern Portweiterleitung.** Hier kollidieren die Netze
zwar nicht (Kamera `192.168.0.0/24`, Heimnetz `192.168.1.0/24`), aber die
Weiterleitung ist trotzdem der robustere Weg. Im Mango
`15740 → 192.168.0.10:15740` weiterleiten und skyshutter auf den Router
zeigen lassen:

```bash
skyshutter --host 192.168.8.1 info
```

PTP/IP baut zwei TCP-Verbindungen zum selben Port auf; eine Weiterleitung genügt.

**tcpdump ohne Speicherplatz auf dem Router.** Der Mango hat 16 MB Flash — der
Mitschnitt wird direkt über SSH auf den Laptop gestreamt:

```bash
ssh root@192.168.8.1 "opkg update && opkg install tcpdump"
ssh root@192.168.8.1 "tcpdump -i any -s 0 -U -w - host 192.168.0.10" > coolpix.pcap
```

**Was der Mango nicht sieht:** Wenn das Handy direkt im Kamera-WLAN hängt, läuft
SnapBridge-Traffic gar nicht über den Router. Für die SnapBridge-Analyse also
**PCAPdroid** auf dem Handy — kostenlos, ohne Root.

## WSL-Besonderheiten

* **Ausgehend reicht NAT.** WSL2 hängt hinter einem NAT des Windows-Hosts; Verbindungen
  von WSL zur Kamera laufen über die Windows-Routingtabelle und funktionieren.
  Statische Routen gehören deshalb nach **Windows**, nicht nach WSL.
* **Wenn WSL die Kamera trotzdem nicht erreicht:** in `%USERPROFILE%\.wslconfig`
  `networkingMode=mirrored` setzen (Windows 11, WSL ≥ 2.0), dann teilt WSL die
  Interfaces des Hosts direkt. `wsl --shutdown` danach.
* **MJPEG-Stream:** `skyshutter stream --bind 0.0.0.0`, im Windows-Browser
  `http://localhost:8080/` — das localhost-Forwarding von WSL2 erledigt den Rest.
* **Fallback nativ unter Windows:** skyshutter benutzt nur die Standardbibliothek
  und keine POSIX-spezifischen Aufrufe, läuft also auch direkt unter Windows-Python.
  Falls die WSL-Netzwerkschicht zickt, ist das der kürzere Weg statt der Fehlersuche.

## Das Handy an adb bekommen — zwei Fallen (gemessen 22.08.2026)

Für den Bluetooth-Mitschnitt muss `adb` das Phone sehen. Auf diesem Rig scheitert
das zweimal hintereinander, beide Male irreführend.

**Falle 1: WSL sieht überhaupt kein USB.** Es gibt kein `/dev/bus/usb`, `lsusb`
ist leer. Das Kabel hängt am Windows-Host, der Linux-Kernel in WSL kennt es
nicht. Also nicht das adb aus WSL benutzen, sondern das von Windows:

```bash
ADB=/mnt/c/Users/thoma/AppData/Local/Android/Sdk/platform-tools/adb.exe
```

Ob Windows das Gerät überhaupt am Bus hat, beantwortet usbipd — das ist der
Test, der zwischen „Kabel/Treiber kaputt" und „Software" trennt:

```cmd
usbipd list
```

Steht dort eine Zeile wie `2-1  22d9:2765  OnePlus 12, ADB Interface`, ist die
Hardwareseite in Ordnung und der Fehler liegt weiter oben.

**Falle 2: Port 5037 ist im Mirrored-Modus belegt.** Läuft WSL mit
`networkingMode=mirrored`, teilen sich Windows und WSL den Loopback. Der
adb-Server kann dann nicht auf seinem Standardport starten und meldet
`could not read ok from ADB Server` — und zwar auch dann, wenn `netstat` und
`ss` den Port als frei zeigen und kein einziger adb-Prozess läuft. Die
Fehlermeldung führt in die Irre; es ist kein Prozesskonflikt, den man killen
könnte. Abhilfe ist ein anderer Port, konsequent bei **jedem** Aufruf:

```bash
"$ADB" -P 5038 devices -l
```

Danach erscheint das Gerät zunächst als `unauthorized` — der RSA-Dialog auf dem
Handy muss bestätigt werden („Diesem Computer immer vertrauen"). Erscheint der
Dialog nicht, in den Entwickleroptionen *USB-Debugging-Autorisierungen
widerrufen* und das Kabel neu stecken.

Der Vollständigkeit halber: usbipd könnte das Handy auch nach WSL durchreichen
(`usbipd bind --busid 2-1`, dann `usbipd attach --wsl`). Das braucht
Administratorrechte und löst ein Problem, das man mit `-P 5038` nicht hat.

## Den Bluetooth-Mitschnitt vom Handy holen

**Falle 3: `adb shell ls /data/misc/bluetooth/logs` gibt `Permission denied.`**
Ohne Root kommt man an das Verzeichnis nicht heran. `adb bugreport` schon — es
startet `dumpstate` mit erhöhten Rechten und packt genau diese Verzeichnisse
mit ein:

```bash
"$ADB" -P 5038 bugreport 'C:\Users\thoma\Downloads\skyshutter-bt.zip'
cp /mnt/c/Users/thoma/Downloads/skyshutter-bt.zip captures/
```

Ein Windows-Zielpfad, kein WSL-Pfad — das Windows-adb kann mit `\\wsl$\…`
nicht zuverlässig umgehen.

**Falle 4: die Datei heißt nicht `btsnoop_hci.log`.** Auf OxygenOS liegen die
Bluetooth-Logs als `FS/data/misc/bluetooth/logs/bluetooth_<zeitstempel>.log`.
Wer im Zip nach `snoop` sucht, findet nur ein NFC-Log und schließt fälschlich,
es gäbe keine Bluetooth-Daten. Richtig ist die Suche nach `bluetooth`.

**Und der wichtige Unterschied:** Diese OEM-Dateien sind **Textlogs des Stacks**,
kein btsnoop. Sie zeigen die GATT-Struktur — Services, Handles, Property-Bits —
aber **keine Nutzdaten**. Für Handle-Werte und Payloads muss vor dem Pairing in
den Entwickleroptionen *Bluetooth-HCI-Snoop-Log* aktiviert und das Handy neu
gestartet werden; erst dann entsteht ein echtes btsnoop, das
`skyshutter.btsnoop` lesen kann.

## Die Kamera direkt über Bluetooth ansprechen (gemessen 22.08.2026)

Der schnellere Weg als der Umweg über das Handy: der Laptop redet selbst mit
der Kamera. Kein Pairing nötig — die Verbindung kam ohne zustande, obwohl die
Kamera mit dem Handy gekoppelt ist.

**WSL hat kein Bluetooth.** Kein Adapter, kein BlueZ. Das Werkzeug läuft
deshalb unter dem Windows-Python:

```bash
PY='/mnt/c/Users/thoma/AppData/Local/Programs/Python/Python312/python.exe'
$PY -m pip install --user bleak
cp tools/ble-probe.py /mnt/c/Users/thoma/AppData/Local/Temp/
$PY 'C:\Users\thoma\AppData\Local\Temp\ble-probe.py' scan
```

**Falle 5: der Bluetooth-Funk ist aus, und bleak sagt es unmissverständlich**
(`BleakBluetoothNotAvailableError: Bluetooth radio is not powered on`).
Einschalten ohne Klick in den Einstellungen geht über die Radio-API:

```powershell
Add-Type -AssemblyName System.Runtime.WindowsRuntime
# Radio.RequestAccessAsync(), dann SetStateAsync('On') auf dem Kind 'Bluetooth'
```

Das vollständige Skript steht in der Messung vom 22.08.2026 in
[FINDINGS.md](FINDINGS.md). PowerShell **5.1** benutzen, nicht 7 — nur dort
sind die WinRT-Typen direkt erreichbar.

**Falle 6: die Kamera advertised in Schüben.** Ein einzelner Scan, der in eine
stille Phase fällt, beweist nichts. `ble-probe.py` scannt deshalb bis zu
viermal. Nach einer getrennten Verbindung wird sie länger still — vermutlich
Energiesparen; dann hilft nur, sie am Gerät aufzuwecken.

**Falle 7: die BLE-Adresse rotiert.** Sie ist eine Resolvable Private Address
und sieht bei jedem Scan anders aus. Nie auf die Adresse verbinden, immer auf
den Namen.

Weil jede Verbindung einen Scan kostet und die Kamera nicht immer wach ist,
holt `session` alles in einem Zug — Baum, Werte und Live-Verkehr:

```bash
$PY 'C:\…\ble-probe.py' session --seconds 60
```

### Mitschnitte im Repo

Rohmitschnitte enthalten Seriennummern, Geräteadressen und potenziell SSID und
Passphrase. Sie gehen nur **verschlüsselt** ins öffentliche Repo; `.gitignore`
lässt in `captures/` ausschließlich `*.gpg` durch. Ein Bugreport als Ganzes
gehört nicht hinein — er enthält Dateilisten und Dokumente, die mit dem Projekt
nichts zu tun haben. Verschlüsselt wird nur, was ausgewertet wurde:

```bash
tar -czf - -C /tmp/btlogs bluetooth_2026*.log |
  gpg --symmetric --cipher-algo AES256 -o captures/bt-logs-2026-08-22.tar.gz.gpg
```

Wieder heraus:

```bash
gpg -d captures/bt-logs-2026-08-22.tar.gz.gpg | tar -xzf - -C /tmp/btlogs
```

Die Passphrase steht nirgends im Repo.

## Installation in WSL

```bash
sudo apt update && sudo apt install -y python3-venv git
git clone -b claude/coolpix-wifi-remote-api-92dw8v https://github.com/thomas0369/skyshutter.git
cd skyshutter
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

## Trockentest, bevor die Kamera ins Spiel kommt

Erst beweisen, dass das Werkzeug funktioniert — dann ist ein Fehlschlag an der
Kamera eindeutig ein Kamera- oder Netzproblem und keine kaputte Installation:

```bash
python -m skyshutter.simulator &
skyshutter --host 127.0.0.1 probe
skyshutter --host 127.0.0.1 info
kill %1
```

Erwartung: `PTP/IP handshake OK: COOLPIX P1100` und eine Opcode-Liste.

## Die erste echte Messung

Kamera in den Fernsteuerungsmodus, Laptop-WLAN mit dem Kamera-AP verbinden, dann:

```bash
skyshutter probe
skyshutter --host 192.168.0.10 probe --ports 15740 80 8080 443 49152 5000
```

Beide Ausgaben vollständig zurückmelden — daran hängt die Entscheidung über die
nächste Phase ([plan.md](plan.md), Phase 1).
