# skyshutter

Eine Nikon-Kamera über ihre eigenen Schnittstellen steuern — Livebild, Auslöser,
Zoom, Protokollwerkzeug. Zielgerät ist eine Coolpix-Superzoom; der Client
spricht generisches PTP/IP und PTP über USB.

**Der Anlass:** Diese Kamera reicht bis **3000 mm** kleinbildäquivalent — genug,
dass der Vollmond drei Viertel der Bildbreite füllt und Jupiters Wolkenbänder
erkennbar werden, ohne dass ein Teleskop aufgebaut wird. Bei dieser Vergrößerung
verwackelt allerdings jede Berührung das Bild, und der einzige Weg zur
Fernsteuerung führt bisher über die Hersteller-App auf dem Telefon.

Ausführlich, mit den Rechnungen dahinter und zwei korrigierten Irrtümern:
**[docs/einfuehrung.md](docs/einfuehrung.md)**.

**Python, ohne Abhängigkeiten.** Der Client über WLAN kommt mit der
Standardbibliothek aus. Zwei Module holen sich mehr, aber erst wenn man sie
benutzt und mit sauberem Fehler, wenn es fehlt: `ptpusb.py` braucht `pyusb`
für den Kabelweg, der Simulator nutzt `pillow`, falls vorhanden, für echte
JPEGs. Die Werkzeuge in `tools/` haben eigene Voraussetzungen — siehe
[tools/README.md](tools/README.md).

---

## Stand

| | |
|---|---|
| **PTP** | **bestätigt** — 38 Operationen und 20 Properties an der Hardware ausgelesen |
| **Live View** | **läuft** — 1552×1162, systemd-Dauerbetrieb (selbstheilend), Capture+Download validiert |
| **Zoom** | **steuerbar** — `0x9016`, EXIF-bewiesen kalibriert; ISO/EV/Drive schreibbar |
| **Kopplung** | **läuft reproduzierbar** — 40 Sekunden vom Funk-Reset bis zum Bond |
| **Zugangsdaten** | **geknackt** — SSID und Passwort per `skyshutter wifi`; das Passwort **rotiert pro Session** und wird frisch entschlüsselt |
| **WLAN-AP** | **bestätigt** — `remote-start.py` fährt den Access Point hoch (korrigierte BLE-Sequenz: CCCDs + `VALID_WAKE` + `0x2005`), von der Hardware belegt |
| **AZ-GTi-Mount** | **bewegt** — komplette Motion-API an der Hardware getestet (Goto ±0,002°); Slew-Raten sind firmwareseitig fest (1,57/2,07°/s), daher Tracking über Goto-Pulsing im Bau |
| **Satelliten** | **Passliste live** — SGP4 + celestrak auf dem Pi verifiziert; `--track` wartet auf Pulsing-Design + Alt-Freigabe |

Alles Gemessene steht in [docs/referenz.md](docs/referenz.md), der Weg dorthin
im [Messprotokoll](docs/FINDINGS.md); die belegte End-to-End-Startsequenz in
[docs/REMOTE_SEQUENCE.md](docs/REMOTE_SEQUENCE.md).

**Was heute schon geht:** über USB die Kamera abfragen, Fähigkeiten auslesen,
Bilder holen; die (rotierenden) WLAN-Zugangsdaten aus einer Kopplung
entschlüsseln; **die Kamera per BLE dazu bringen, ihr WLAN zu öffnen**; Live
View im Dauerbetrieb streamen und auslösen; den AZ-GTi-Mount über WLAN
kommandieren und Satellitenpässe berechnen.
**Was noch fehlt:** das ruckfreie Nachführen von Satelliten (Goto-Pulsing,
Design steht) und die Alt-Achse (mechanisch fest, vermutlich Klemmung).

---

## Installation

```bash
pip install -e .              # Client, ohne Abhängigkeiten
pip install -e '.[dev]'       # dazu die Testsuite
pip install -e '.[sim]'       # dazu echte JPEGs im Simulator
```

## Ohne Kamera ausprobieren

```bash
python -m skyshutter.simulator          # Terminal 1
skyshutter --host 127.0.0.1 info        # Terminal 2
skyshutter --host 127.0.0.1 stream      # Livebild auf http://localhost:8080/
```

Der Simulator bildet ab, **was an der echten Kamera gemessen wurde** — bis hin
zu der Eigenheit, dass sie nur die neuere Ereignisabfrage kennt. Ein Client, der
die ältere erwartet, scheitert deshalb schon hier statt erst am Gerät.

## An der Kamera

Über USB, sobald das Gerät angeschlossen ist:

```bash
skyshutter info                 # was die Kamera wirklich kann
```

Über WLAN, sobald der Access Point läuft:

```bash
skyshutter probe                # Kamera und Steuerport suchen
skyshutter stream               # Livebild als MJPEG
```

Die Kamera ist der DHCP-Server ihres eigenen Netzes; ihre Adresse steht im
vergebenen Lease. Der Anschluss ist in [docs/pairing.md](docs/pairing.md)
beschrieben, samt der Fallstricke, die dabei aufgetreten sind.

## Befehle

| Befehl | Zweck |
|---|---|
| `skyshutter probe` | Portscan und PTP/IP-Handshake |
| `skyshutter info` | Fähigkeiten der Kamera, mit aufgelösten Namen |
| `skyshutter shoot -n 5 --interval 30` | auslösen, optional als Reihe |
| `skyshutter liveview -o frames/ -n 100` | Livebilder auf die Platte |
| `skyshutter stream --http-port 8080` | Livebild im Browser |
| `skyshutter events` | Ereignisse der Kamera mitlesen |
| `skyshutter raw 0x9203 -o frame.bin` | beliebige Operation absetzen |
| `skyshutter wifi pairing.json` | SSID und Passwort aus der Kopplung entschlüsseln |
| `skyshutter btsnoop datei.log` | Bluetooth-Mitschnitt auswerten |
| `skyshutter mount status` / `watch` / `stop` | AZ-GTi-Mount lesen und stilllegen |
| `skyshutter mount slew --az-dps 0.5 --allow-motion` | Mount drehen (Gate: ohne Flag kein Byte) |
| `skyshutter mount satellite --norad 25544 --lat 50.1 --lon 8.7 --passes` | ISS-Pässe der nächsten 12 h; `--now` aktuelle Position, `--track --allow-motion` verfolgt (im Bau) |

Global: `--host`, `--port`, `--guid`, `--name`, `--timeout`, `-v`.

## WLAN-Zugangsdaten gewinnen

Die Kamera gibt SSID und Passwort ihres Access Points verschlüsselt über
Bluetooth heraus, und das Passwort wechselt. `skyshutter wifi` rechnet beides
aus dem zurück, was beim Koppeln ohnehin über die Leitung geht — ohne
Gerätegeheimnis, für jede Kopplung neu.

```bash
# beim Koppeln die Handshake-Werte mitschreiben (Windows-Werkzeug, s. tools/):
python tools/ble-probe.py pairing --register skyshutter --pairing-json pairing.json

# daraus die Zugangsdaten entschlüsseln:
skyshutter wifi pairing.json
skyshutter wifi pairing.json --connect     # gibt zusätzlich die nmcli-Zeile aus
```

Das Verfahren ist die Nikon-eigene Blowfish-Kette, aus der Hersteller-App
rekonstruiert und gegen echte Hardware verifiziert — Details in
[docs/referenz.md](docs/referenz.md), Abschnitt „Verschlüsselung der
Zugangsdaten".

## Als Bibliothek

```python
from skyshutter import NikonCamera

with NikonCamera.open("192.168.0.10") as camera:
    print(camera.device_info.model)

    if reason := camera.live_view_prohibit():
        print(f"Livebild gesperrt: {reason!r}")

    camera.zoom(+200)                       # Richtung Tele
    for frame in camera.stream_live_view(fps=15):
        ...                                 # frame.jpeg, frame.zoom, frame.roll
```

---

## Aufbau

```
src/skyshutter/
  ptp.py          Protokollkern: Opcodes, Datasets, DeviceInfo
  ptpip.py        Transport über TCP: Rahmen, Handshake, Keepalive
  ptpusb.py       Transport über USB: dieselbe Schnittstelle, andere Rahmen
  nikon.py        Vendor-Ebene: Zoom, Auslöser, Live View, Properties
  ble.py          die gemessene BLE-Characteristic-Tabelle
  discovery.py    Kamera und Steuerport im Netz finden
  mjpeg.py        Livebild als HTTP-Stream
  btsnoop.py      Bluetooth-Mitschnitte auswerten
  config.py       GUID und Voreinstellungen in ~/.config/skyshutter/
  simulator.py    Kamera-Nachbau für Entwicklung ohne Hardware
  cli.py          Kommandozeile

tools/            Werkzeuge für die Messung an echter Hardware
  ble-probe.py    BLE-Client: scannen, Handshake, koppeln
  classic-pair.py klassisches Bluetooth-Bonding
  ble-proxy.py    zwischen Hersteller-App und Kamera mitlesen
  ble-camera-sim.py  die Kamera für die App nachspielen
  nikon_pairing.py   der Authentifizierungs-Handshake
  pair.sh         der Kopplungsablauf als Kommandoblock
```

### Wie die Teile zusammenhängen

```
   cli.py            mjpeg.py              tools/*.py
      │                  │                     │
      └────────┬─────────┘                     │  Bluetooth, nur Windows
               │                               │  (koppeln, WLAN starten)
           nikon.py          ble.py ───────────┘
      Zoom · Auslöser · Live View       gemessene Characteristics
               │
      ┌────────┴────────┐        beide bieten transaction()
   ptpip.py         ptpusb.py
   TCP 15740        USB-Bulk
      │                 │
      └────────┬────────┘
            ptp.py
   Opcodes · DeviceInfo · Fehlercodes
```

**Der Angelpunkt ist `transaction()`.** Beide Transporte bieten dieselbe
Methode, und alles darüber — Vendor-Ebene, Livebild-Server, Kommandozeile —
kennt den Unterschied zwischen Kabel und Funk nicht. Ein dritter Transport
bräuchte nur diese eine Methode.

`ble.py` steht bewusst daneben statt darunter: Bluetooth trägt keine
PTP-Operationen, sondern koppelt und schaltet das WLAN ein. Beide Wege treffen
sich erst in der Kamera.

Zwei Regeln, die im Code sichtbar sind: **Jede Methode prüft
`operations_supported`, bevor sie eine Vendor-Operation absetzt** — was die
Kamera nicht anbietet, wird nicht gesendet. Und **der Simulator bildet die
Messung ab, nicht das Wünschenswerte**; er meldet dieselben Operationen wie die
echte Kamera, samt ihrer Eigenheiten.

## Dokumentation

**Wer das Projekt übernimmt, liest in dieser Reihenfolge:**

1. [einfuehrung.md](docs/einfuehrung.md) — worum es geht: welche Kamera, warum
   sie für Astrofotografie taugt, und was die App daran hindert.
2. [referenz.md](docs/referenz.md) — was die Kamera kann. Jeder Abschnitt sagt,
   ob er gemessen oder aus dem Herstellercode gelesen ist.
3. [FINDINGS.md](docs/FINDINGS.md) — der Stand-Block ganz oben nennt das
   aktuelle Gate und den nächsten Schritt.
4. [tools/README.md](tools/README.md) — falls eine Kamera zur Hand ist. Die
   Bluetooth-Werkzeuge laufen nur unter Windows.
5. [playbook.md](docs/playbook.md) — wie hier gearbeitet wird, und was man an
   echter Hardware **nicht** tut.

| Datei | Inhalt |
|---|---|
| [einfuehrung.md](docs/einfuehrung.md) | **Worum es geht** — Kamera, Zweck, Problem, Stand |
| [referenz.md](docs/referenz.md) | **Nachschlagewerk** — was die Kamera kann, mit Herkunftsangabe |
| [FINDINGS.md](docs/FINDINGS.md) | Messprotokoll, chronologisch, mit „Widerlegtes" |
| [tools/README.md](tools/README.md) | die Werkzeuge: Plattform, Reihenfolge, Sicherheitsregeln |
| [pairing.md](docs/pairing.md) | Kopplung: Ablauf und sechs Fallstricke |
| [protokoll.md](docs/protokoll.md) | PTP/IP-Referenz |
| [plan.md](docs/plan.md) | Phasenplan mit Stand |
| [playbook.md](docs/playbook.md) | Arbeitsweise, Sicherheitsregeln |
| [recherche.md](docs/recherche.md) | Stand der Technik, was andere schon versucht haben |
| [setup-wsl-glinet.md](docs/setup-wsl-glinet.md) | Laboraufbau |

### Konventionen

- **Nichts steht hier, weil es plausibel ist** — jede Aussage über die Hardware
  ist gemessen oder als unbelegt gekennzeichnet.
- **Widerlegtes wird nicht gelöscht**, sondern durchgestrichen und begründet.
  Ein Irrweg, den man zweimal geht, kostet doppelt.
- Dokumentation auf Deutsch, Code und Commits auf Englisch.

### Zu `captures/`

Dort liegt ein verschlüsseltes Archiv mit Bluetooth-Mitschnitten. **Die
Passphrase liegt bewusst nicht im Repository** — die Rohdaten enthalten SSID,
WLAN-Passphrase, Kopplungskennung und Seriennummer eines realen Geräts.

Alles, was daraus an Protokollwissen gewonnen wurde, steht geschwärzt in
[referenz.md](docs/referenz.md) und [FINDINGS.md](docs/FINDINGS.md). Das Archiv
ist Beleg, keine Voraussetzung: Wer das Projekt übernimmt, braucht es nicht.
`.gitignore` lässt in `captures/` ausschließlich `*.gpg` durch, damit
Klartext-Mitschnitte gar nicht erst versehentlich hineinrutschen.

## Entwicklung

```bash
python -m pytest        # 128 Tests, ohne Hardware
ruff check .
```

Jede Messung an echter Hardware wird von einem Test festgehalten. Weicht der
Simulator von der Realität ab, gilt das als Fehler.

---

## Herkunft der Protokollkenntnis

Die Grundlagen stammen aus fremder Vorarbeit: [libgphoto2](http://gphoto.org/)
als PTP/IP-Referenz, [gkoh/furble](https://github.com/gkoh/furble) und
[hurui200320/nsg](https://github.com/hurui200320/nsg) für die BLE-Seite.

Alles, was darüber hinausgeht, wurde an der eigenen Kamera gemessen oder durch
Analyse der Hersteller-App gewonnen. Letzteres ist nach **§ 69e UrhG**
(Dekompilierung zur Herstellung der Interoperabilität) zulässig; der Code wurde
zur Verifikation gelesen, nicht übernommen.

## Lizenz

MIT, siehe [LICENSE](LICENSE). libgphoto2 steht unter LGPL-2.1 — fremde
Opcode-Tabellen und Codestücke werden gelesen, nicht kopiert.
