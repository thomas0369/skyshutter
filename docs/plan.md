# Plan: von der Recherche zur P1100-API

Dieser Plan beschreibt, wie aus den existierenden Projekten plus eigenem Reverse
Engineering eine vollständige API für die Coolpix P1100 wird — und vor allem:
**wer davon was macht.**

Die Arbeitsweise dahinter steht in [playbook.md](playbook.md), der belegte Stand in
[FINDINGS.md](FINDINGS.md).

## 1. Rollenverteilung

Ich arbeite in einem Cloud-Container. Kein WLAN zur Kamera, kein Bluetooth, keine
USB-Ports, keine Sichtverbindung zur Hardware. Das ist keine Kleinigkeit, sondern
bestimmt den ganzen Arbeitsmodus:

| Ich kann | Ich kann nicht |
|---|---|
| Code, Parser, Tests, Doku | Mich mit der Kamera verbinden |
| Deine Mitschnitte auswerten (pcap, Hex-Dumps, Logs) | Einen Mitschnitt selbst erzeugen |
| Fremde Repos lesen und deren Protokollwissen übersetzen | Ein Gerät flashen oder ein Kabel stecken |
| Hypothesen bauen und in Kommandos gießen, die du ausführst | Verifizieren, ob sie stimmen |

**Du bist Hände und Augen.** Der Loop ist immer derselbe: ich gebe dir ein bis drei
Kommandos, du führst sie aus, du gibst mir die Ausgabe, ich baue daraus Code und
Tests. Ein Durchlauf dauert bei dir selten mehr als fünf Minuten.

Damit dein Aufwand klein bleibt, gilt: **Textausgabe pasten reicht.** Nur wo es
wirklich Binärdaten braucht (pcap, rohes Live-View-Paket), landen Dateien im Repo.

## 2. Dein WLAN-Setup — die vier Varianten

Das Kernproblem: die Kamera ist ein Access Point. Wer mit ihr redet, hängt in
*ihrem* Netz — und damit normalerweise nicht mehr im Internet. Genau deshalb ist
die Frage nach dem Interface die richtige erste Frage.

| Variante | Hardware | Gleichzeitig Internet? | Mitschnitt möglich? | Aufwand |
|---|---|---|---|---|
| **A** Laptop, ein WLAN | nichts | nein | ja (lokal, offline) | null |
| **B** Laptop + USB-WLAN-Stick | Stick ~15 € | ja (wlan0 Heimnetz, wlan1 Kamera) | ja | 10 min |
| **C** GL-X3000 als Repeater | vorhanden | ja (5G als WAN) | ja, direkt auf dem Router | 20 min |
| **D** Raspberry Pi als Agent | Pi + LAN-Kabel | ja | ja | 30 min |

**Empfehlung: B für die tägliche Arbeit, C für die Mitschnitte.**

Mit **B** arbeitest du normal weiter (Chat mit mir über das Heimnetz) und schickst
skyshutter gezielt über den zweiten Adapter zur Kamera. Das ist der bequemste
Dauerzustand.

**C** ist dein Heimvorteil: Der GL-X3000 hängt sich im Repeater-Modus ins
Kamera-WLAN, holt sein Internet über 5G, und du kannst auf dem Router selbst
`tcpdump` laufen lassen — der Mitschnitt entsteht dort, wo der Traffic ohnehin
vorbeikommt, ohne Root auf dem Handy.

**D** ist die sauberste Dauerlösung für Astro-Nächte: Pi am Teleskop/Stativ, per
Ethernet im Heimnetz, per WLAN an der Kamera. Wenn du keinen ganzen Pi hast (der
Pico aus dem CD8150-Projekt zählt nicht), überspring das.

### Drei Fallen, die dich sonst eine Stunde kosten

1. **Subnetz-Kollision.** Die Kamera ist sehr wahrscheinlich `192.168.1.1` — dasselbe
   Netz, das viele Heimrouter benutzen. Bei Variante C den Router-LAN vorher auf
   etwas anderes legen (GL.iNet-Default `192.168.8.1` ist gut). Bei B prüfen, dass
   dein Heimnetz nicht ebenfalls `192.168.1.0/24` ist, sonst gehen Routen kaputt.
2. **WPA3-SAE.** Nikon gibt für die P1100 WPA3-SAE an. Alte USB-Sticks und alte
   Treiber können das nicht. Beim Kauf auf einen Chipsatz mit `mac80211`-Treiber im
   Mainline-Kernel achten (MediaTek MT7601/MT7612 oder Realtek RTL8188EU/RTL8812AU
   mit aktuellem Treiber) und `wpa_supplicant` ≥ 2.10. 2,4 GHz genügt — die Kamera
   ist 802.11 b/g/n.
3. **Metrik/Default-Route.** Bei zwei WLANs will NetworkManager gern die
   Kamera-Verbindung zur Default-Route machen; dann ist das Internet weg, obwohl
   beide Adapter verbunden sind. Auf der Kamera-Verbindung
   `ipv4.never-default yes` setzen.

### Checkliste Hardware

- [x] Coolpix P1100 (hast du)
- [x] GL-X3000 (hast du) — für Variante C und für Mitschnitte
- [ ] Android-Handy mit SnapBridge — **notwendig** für den BLE-Teil (Phase 5)
- [ ] USB-Kabel Handy↔Rechner — für `adb bugreport` (HCI-Snoop-Log holen)
- [ ] optional: USB-WLAN-Stick für Variante B
- [ ] optional: ESP32 für den furble-Quick-Win (Phase 0)

## 3. Phasenplan

Jede Phase hat ein Gate. Ist das Gate nicht erreicht, ist die nächste Phase sinnlos —
dann greift der jeweils genannte Umweg.

### Phase 0 — Quick-Win, parallel und unabhängig
**Ziel:** Ein funktionierender Auslöser, egal was das WiFi-Protokoll macht.
**Du:** [furble](https://github.com/gkoh/furble) auf einen ESP32 flashen, gegen die
P1100 koppeln (die Kamera spricht ML-L7-BLE).
**Ich:** nichts.
**Gate:** Kamera löst aus → du hast ab sofort eine Rückfallebene für Astro-Serien,
während der Rest noch offen ist.

### Phase 1 — Ist es PTP/IP?
**Ziel:** Die eine Annahme prüfen, auf der alles Weitere steht.
**Du:** Kamera in den Fernsteuerungsmodus, Rechner ins Kamera-WLAN, dann:
```bash
skyshutter probe
skyshutter --host 192.168.1.1 probe --ports 15740 80 8080 443 49152 5000
```
Ausgabe pasten. Mehr nicht.
**Ich:** Auswerten und den nächsten Schritt bestimmen.
**Gates:**

| Ausgabe | Bedeutung | Weiter mit |
|---|---|---|
| `PTP/IP handshake OK` | Jackpot, ungepairte GUID wird akzeptiert | Phase 2 |
| Port 15740 offen, `InitFail` | PTP/IP da, aber Pairing nötig | Phase 5, dann Phase 2 |
| 15740 zu, andere Ports offen | anderes Protokoll | Phase 1b |
| nichts offen | falscher Kameramodus oder falsches Netz | Setup prüfen |

### Phase 1b — Nur falls Phase 1 nichts findet
**Ziel:** Herausfinden, was SnapBridge tatsächlich spricht.
**Du:** Mitschnitt, während SnapBridge fernsteuert (Details in
[reverse-engineering.md](reverse-engineering.md)) — auf dem GL-X3000:
```bash
tcpdump -i br-lan -s 0 -w /tmp/coolpix.pcap host 192.168.1.1
```
Datei bereitstellen.
**Ich:** pcap in Python zerlegen (den Decoder baue ich, siehe Abschnitt 6) und das
Protokoll benennen.
**Gate:** Wir wissen, welches Protokoll auf welchem Port läuft.

### Phase 2 — DeviceInfo: der wichtigste Messwert des Projekts
**Ziel:** Die Liste dessen, was die Kamera wirklich kann.
**Du:** `skyshutter info` → Ausgabe pasten. Zusätzlich
`skyshutter raw 0x1001 -o deviceinfo.bin` als Rohdatei, falls das Parsen klemmt.
**Ich:** Aus `operations_supported` und `device_properties_supported` ergibt sich der
komplette Rest des Projekts — welche Vendor-Opcodes existieren, ob Live View da ist,
ob der Zoom steuerbar ist. Ich trage die Liste in `protokoll.md` ein und schneide
den Client darauf zu.
**Gate:** Vendor-Opcodes ≥ `0x9000` sind in der Liste → die Kamera ist steuerbar,
nicht nur ein Dateiserver.

### Phase 3 — Live View und Auslöser
**Ziel:** Das eigentliche Produkt: Bild sehen, Bild machen.
**Du:**
```bash
skyshutter raw 0x9201                    # StartLiveView
skyshutter raw 0x9203 -o frame.bin       # ein rohes Frame
skyshutter shoot
skyshutter stream                         # Browser auf http://localhost:8080/
```
`frame.bin` ins Repo, Rest pasten.
**Ich:** Header-Länge und Bildformat aus `frame.bin` bestimmen, Live-View-Pfad
festnageln, Auslöse-Opcode auf das festlegen, was die Kamera tatsächlich mag.
**Gate:** Ein JPEG im Browser und eine Datei auf der Speicherkarte.

### Phase 4 — Properties: Zoom, Belichtung, Fokus
**Ziel:** Aus „auslösen" wird „steuern" — der 125×-Zoom ist der halbe Grund für die Kamera.
**Du:** Eine Schleife, die ich dir als Skript gebe: alle Property-Codes aus Phase 2
abfragen, Wert notieren, an der Kamera etwas verstellen, erneut abfragen.
Das Diff verrät, welcher Code welche Funktion ist.
**Ich:** Property-Tabelle bauen, typisierte Getter/Setter, `camera.zoom`, `camera.iso`,
`camera.shutter_speed` etc.
**Gate:** Zoomfahrt per Kommando.

### Phase 5 — BLE-Pfad
**Ziel:** Kamera ohne Handy aufwecken und ihr WLAN einschalten; GUID-Pairing lösen.
Nötig, sobald Phase 1 an `InitFail` scheitert — und ohnehin für „Kamera schläft im
Garten, ich starte die Session vom Rechner".
**Du:**
1. Entwickleroptionen → Bluetooth-HCI-Snoop-Log an, Bluetooth aus/ein.
2. SnapBridge: entkoppeln, neu koppeln, Fernsteuerung starten.
3. `adb bugreport` → `btsnoop_hci.log` extrahieren → bereitstellen.
**Ich:** Handshake gegen [nsg](https://github.com/hurui200320/nsg) und
[snapbridge-id-extractor](https://github.com/HowenXu/snapbridge-id-extractor)
abgleichen, in Python mit `bleak` nachbauen, GUID-Ableitung implementieren.
**Gate:** `skyshutter wake` schaltet das Kamera-WLAN ein, ohne dass SnapBridge läuft.

### Phase 6 — Robustheit
**Ziel:** Aus einem Demo-Skript wird etwas, das eine Nacht durchhält.
Reconnect nach WLAN-Abriss, Keepalive/Ping, Session-Recovery, Timeouts, Verhalten
bei leerem Akku und vollem Speicher.
**Du:** Eine lange Session laufen lassen und mir das Logfile geben.
**Gate:** Vier Stunden Intervallaufnahme ohne Handgriff.

### Phase 7 — Astro-Features
Intervallometer mit Drift-Korrektur, Belichtungsreihen, Langzeit-/Bulb-Serien,
Fokus-Feinsteuerung über `MfDrive`, automatischer Download der Aufnahmen.
Erst hier wird die API „perfekt" im Sinne deiner eigentlichen Anwendung.

### Phase 8 — MCP-Server
Der Client als MCP-Server für mcp-hub.stream. Naheliegend, aber sinnlos, bevor
Phase 3 steht.

## 4. Wie die existierenden Projekte konkret eingesetzt werden

| Projekt | Wie genau | Lizenz |
|---|---|---|
| **libgphoto2** | Referenz für PTP/IP-Rahmenformat und Opcode-Bedeutungen; außerdem als unabhängige Gegenprobe: `gphoto2 --port ptpip:192.168.1.1 --summary` | LGPL-2.1 — **kein Code und keine Tabellen 1:1 übernehmen**, siehe Abschnitt 5 |
| **gkoh/furble** | Sofortiger BLE-Auslöser (Phase 0); dessen RE-Notizen beschreiben die ML-L7-Charakteristiken | GPL |
| **hurui200320/nsg** | Vorlage für den SnapBridge-BLE-Handshake in Phase 5 | prüfen vor Verwendung |
| **HowenXu/snapbridge-id-extractor** | Rekonstruktion der DeviceID/GUID, damit wir neben SnapBridge koexistieren | prüfen vor Verwendung |
| **fuji-cam-wifi-tool / fudge / alpha-fairy** | Nur Methodik: wie andere Marken erfolgreich zerlegt wurden | — |

## 5. Lizenz- und Sicherheitshygiene

**Lizenzen.** skyshutter ist MIT, libgphoto2 ist LGPL-2.1. Opcode-Tabellen aus
`ptp.h` wörtlich zu kopieren wäre ein Lizenzbruch. Vorgehen: Werte, die wir selbst
an der Kamera messen, schreiben wir selbst auf; fremde Implementierungen dienen zur
Verifikation, nicht als Copy-Paste-Quelle. Bei nsg und dem ID-Extractor prüfe ich
vor jeder Übernahme die Lizenzdatei.

**Dein Repo ist öffentlich.** Mitschnitte enthalten potenziell die SSID und die
Passphrase des Kamera-APs, die Pairing-GUID und die Seriennummer der Kamera. Vor dem
Commit also: sensible Felder schwärzen, oder mir den relevanten Ausschnitt als Hex
pasten statt die ganze Datei zu pushen. `.gitignore` blockt `*.pcap` bereits
absichtlich — ein `git add -f` sollte eine bewusste Entscheidung sein.

**Recht.** Reverse Engineering zur Interoperabilität mit selbst gekaufter Hardware
ist in der EU durch Art. 6 der Software-Richtlinie (2009/24/EG) und § 69e UrhG
gedeckt. Wir veröffentlichen eigenen Code und Protokollwissen, keine Nikon-Software.

## 6. Was ich parallel ohne Hardware bauen kann

Damit deine Messungen nicht auf Werkzeug warten:

1. **pcap-Decoder** (`skyshutter pcap datei.pcap`) — zerlegt einen Mitschnitt in
   PTP/IP-Pakete und benennt Opcodes. Reines Python, kein Wireshark nötig. Macht
   Phase 1b und die Auswertung von SnapBridge-Sessions zu einer Ein-Zeilen-Sache.
2. **`skyshutter bundle`** — sammelt in einem Rutsch alles, was ich für eine
   Ferndiagnose brauche (Probe, DeviceInfo roh und geparst, ein Live-View-Frame,
   Logs) in ein Verzeichnis, das du mir gibst. Ein Kommando statt sechs.
3. **Property-Explorer** — das Skript für Phase 4.
4. **BLE-Gerüst** mit `bleak`, gegen die nsg-Beschreibung gebaut, von dir testbar.

## 7. Definition of Done

Die API ist „perfekt", wenn dieses Skript durchläuft:

```python
from skyshutter import Camera

with Camera.discover() as cam:          # BLE-Wake, WLAN an, PTP/IP-Session
    cam.zoom(to_mm=2000)
    cam.focus.manual(steps=-3)
    cam.iso, cam.shutter, cam.aperture = 800, "15s", 5.6
    for shot in cam.interval(count=200, every="20s", download=True):
        print(shot.path, shot.exif.temperature)
```

Alles darunter — Handshake, Vendor-Opcodes, Reconnect nach WLAN-Abriss — ist
Implementierungsdetail und für dich unsichtbar.

## 8. Nächster Schritt, heute

Genau ein Kommando entscheidet über die nächsten zwei Wochen:

```bash
skyshutter probe
```

Der Rest des Plans hängt an dessen Ausgabe.
