# Setup: Windows + WSL Ubuntu + GL.iNet Mini-Router

Konkrete Anleitung für die vorhandene Hardware. Ersetzt für diesen Aufbau die
allgemeine Variantentabelle in [plan.md](plan.md), Abschnitt 2.

## Hardware

* Windows-Laptop mit WSL Ubuntu (eingebautes WLAN + USB-Ethernet-Adapter)
* GL.iNet 300M Mini Smart Router (Mango, GL-MT300N-V2) am USB-Ethernet
* Coolpix P1100

## Die entscheidende Überlegung: wer redet mit der Kamera?

Naheliegend wäre, den Mango ins Kamera-WLAN zu hängen. Das ist hier aber der
schlechtere Weg: **Der Mango kann kein WPA3-SAE** — GL.iNet hat es auf dieser
Hardware mit Firmware 3.215 deaktiviert, für 4.x ist es unbestätigt. Nikon gibt
für die P1100 WPA3-SAE an. Der Router würde also möglicherweise gar nicht erst ins
Kamera-Netz kommen, und du säßest an einem Problem, das nichts mit dem eigentlichen
Projekt zu tun hat.

Deshalb wird es umgedreht: **Das Laptop-WLAN geht zur Kamera** (moderner Adapter,
Windows-Treiber, WPA3 kein Thema), **der Mango liefert das Internet** aus dem
Heim-WLAN. Das Risiko landet damit auf der Seite, die du kontrollierst — dein
Heimnetz kann WPA2, die Kamera muss nichts können.

## Variante 1 — der Alltagsaufbau (empfohlen)

```
Kamera (AP, 192.168.1.1)  ←── WLAN ──  Laptop  ── USB-Ethernet ──→ Mango ──→ Heim-WLAN → Internet
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
ping 192.168.1.1          # Kamera
curl.exe https://ifconfig.me   # Internet
```

Klappt nur eins von beiden, stimmen die Metriken nicht.

## Variante 2 — für Mitschnitte, später

Erst relevant, wenn ein Paketmitschnitt gebraucht wird (Phase 1b). Dann hängt der
Mango im Kamera-WLAN und schneidet mit — **falls die Kamera WPA2 anbietet.** Viele
Geräte laufen im WPA2/WPA3-Übergangsmodus; ob die P1100 dazugehört, sehen wir am
Repeater-Dialog des Mango.

Zwei Details, die dir Ärger sparen:

**Keine statische Route, sondern Portweiterleitung.** Kamera und Heimnetz benutzen
gern beide `192.168.1.0/24` — eine statische Route wäre dann mehrdeutig. Stattdessen
im Mango `15740 → 192.168.1.1:15740` weiterleiten und skyshutter auf den Router
zeigen lassen:

```bash
skyshutter --host 192.168.8.1 info
```

PTP/IP baut zwei TCP-Verbindungen zum selben Port auf; eine Weiterleitung genügt.

**tcpdump ohne Speicherplatz auf dem Router.** Der Mango hat 16 MB Flash — der
Mitschnitt wird direkt über SSH auf den Laptop gestreamt:

```bash
ssh root@192.168.8.1 "opkg update && opkg install tcpdump"
ssh root@192.168.8.1 "tcpdump -i any -s 0 -U -w - host 192.168.1.1" > coolpix.pcap
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
skyshutter --host 192.168.1.1 probe --ports 15740 80 8080 443 49152 5000
```

Beide Ausgaben vollständig zurückmelden — daran hängt die Entscheidung über die
nächste Phase ([plan.md](plan.md), Phase 1).
