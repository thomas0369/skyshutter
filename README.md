# skyshutter

Eine Nikon-Kamera über ihre eigenen Schnittstellen steuern — Livebild, Auslöser,
Zoom, Protokollwerkzeug. Zielgerät ist eine Coolpix-Superzoom; der Client
spricht generisches PTP/IP und PTP über USB.

Der Zweck ist Astrofotografie: 3000 mm Brennweite, ferngesteuert, ohne die
Hersteller-App.

**Python, ausschließlich Standardbibliothek.** Optionale Zusätze nur für
Werkzeuge, nicht für den Client.

---

## Stand

| | |
|---|---|
| **PTP** | **bestätigt** — 38 Operationen und 20 Properties an der Hardware ausgelesen |
| **Live View** | **vorhanden** — `9201`, `9202`, `9203` stehen in `operations_supported` |
| **Zoom** | Operation bekannt (`9016`), an der Hardware noch nicht ausgelöst |
| **Kopplung** | **läuft reproduzierbar** — 40 Sekunden vom Funk-Reset bis zum Bond |
| **WLAN** | Auslöser bekannt (`0x01` auf `0x2005`), Wirkung noch nicht gemessen |

Alles Gemessene steht in [docs/referenz.md](docs/referenz.md), der Weg dorthin
im [Messprotokoll](docs/FINDINGS.md).

**Was heute schon geht:** über USB die Kamera abfragen, ihre Fähigkeiten
auslesen, Bilder holen. **Was noch nicht geht:** das Livebild — dafür muss die
Kamera ihr WLAN öffnen, und dieser Auslöser ist zwar bekannt, aber ungetestet.

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
| `skyshutter btsnoop datei.log` | Bluetooth-Mitschnitt auswerten |

Global: `--host`, `--port`, `--guid`, `--name`, `--timeout`, `-v`.

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

Die beiden Transporte teilen sich eine Schnittstelle: Alles oberhalb von
`transaction()` — Vendor-Ebene, Livebild-Server, Kommandozeile — läuft
unverändert über Kabel wie über Funk.

## Dokumentation

| Datei | Inhalt |
|---|---|
| [referenz.md](docs/referenz.md) | **Nachschlagewerk** — was die Kamera kann, mit Herkunftsangabe |
| [FINDINGS.md](docs/FINDINGS.md) | Messprotokoll, chronologisch |
| [pairing.md](docs/pairing.md) | Kopplung: Ablauf und Fallstricke |
| [protokoll.md](docs/protokoll.md) | PTP/IP-Referenz |
| [plan.md](docs/plan.md) | Phasenplan |
| [playbook.md](docs/playbook.md) | Arbeitsweise, Sicherheitsregeln |
| [recherche.md](docs/recherche.md) | Stand der Technik |
| [setup-wsl-glinet.md](docs/setup-wsl-glinet.md) | Laboraufbau |

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
