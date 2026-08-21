# skyshutter

Nikon-Kameras über ihr eigenes WLAN steuern — Livebild, Auslöser, Protokoll-Werkzeug.
Zielgerät ist die **Coolpix P1100**; der Client ist generisches PTP/IP und sollte mit
jeder Nikon funktionieren, die PTP/IP spricht.

> **Status: unbestätigt.** Ob die P1100 im SnapBridge-Remote-Modus überhaupt PTP/IP
> auf TCP 15740 anbietet, ist nirgends dokumentiert und hier noch nicht gemessen.
> Der Code ist gegen den mitgelieferten Simulator getestet, **nicht gegen echte
> Hardware.** Genau dafür gibt es `skyshutter probe`. Wie es weitergeht:
> [docs/plan.md](docs/plan.md), Hintergrund: [docs/recherche.md](docs/recherche.md).

## Installation

```bash
pip install -e .            # plus '.[dev]' für Tests, '.[sim]' für echte Simulator-JPEGs
```

Keine Laufzeit-Abhängigkeiten — nur die Standardbibliothek.

## Erster Versuch an der Kamera

Kamera in den Fernsteuerungsmodus bringen, mit ihrem WLAN verbinden, dann:

```bash
skyshutter probe                    # Ports scannen + PTP/IP-Handshake versuchen
skyshutter info                     # DeviceInfo: was kann die Kamera wirklich?
```

`probe` sucht die Kamera selbstständig unter den üblichen AP-Adressen
(192.168.1.1, 192.168.0.1, …); mit `--host` geht es explizit.

Die drei möglichen Ausgänge und was daraus folgt, stehen in
[docs/reverse-engineering.md](docs/reverse-engineering.md).

## Ohne Kamera ausprobieren

```bash
python -m skyshutter.simulator      # Terminal 1: gefakte Kamera auf 127.0.0.1:15740
skyshutter --host 127.0.0.1 info    # Terminal 2
skyshutter --host 127.0.0.1 stream  # Livebild auf http://localhost:8080/
```

Der Simulator antwortet auf denselben Handshake wie eine echte Kamera. Er bildet
ab, was Nikons üblicherweise können — **keine Messung an der P1100.**

## Befehle

| Befehl | Zweck |
|---|---|
| `skyshutter probe` | Portscan + PTP/IP-Handshake; erster Test überhaupt |
| `skyshutter info` | DeviceInfo mit aufgelösten Opcode-Namen |
| `skyshutter shoot -n 5 --interval 30` | Auslösen, optional als Intervallreihe |
| `skyshutter liveview -o frames/ -n 100` | Live-View-Bilder auf Platte schreiben |
| `skyshutter stream --http-port 8080` | Live View als MJPEG im Browser |
| `skyshutter events` | Event-Queue der Kamera mitlesen |
| `skyshutter raw 0x9203 -o frame.bin` | beliebige PTP-Operation absetzen (RE-Werkzeug) |

Global: `--host`, `--port`, `--guid`, `--name`, `--timeout`, `-v` (mehrfach für
Paket-Logging).

## Als Bibliothek

```python
from skyshutter import NikonCamera

with NikonCamera.open("192.168.1.1") as camera:
    print(camera.device_info.model)
    camera.autofocus()
    camera.capture()

    for frame in camera.stream_live_view(fps=10):
        ...  # jedes frame ist ein fertiges JPEG
```

## GUID / Pairing

Nikon-Kameras merken sich die GUIDs gepaarter Clients. skyshutter legt einmalig
eine eigene in `~/.config/skyshutter/config.json` an und benutzt sie danach
konstant. Antwortet die Kamera mit `InitFail`, ist die GUID nicht gepaart — dann
muss sie aus dem SnapBridge-Pairing rekonstruiert und per `--guid` bzw.
`SKYSHUTTER_GUID` gesetzt werden.

## Aufbau

```
src/skyshutter/
  ptp.py         PTP-Konstanten, Datasets, DeviceInfo
  ptpip.py       Transport: Rahmen, Handshake, Transaktionen
  nikon.py       Vendor-Opcodes, Auslöser, Live View
  discovery.py   Kamera und Steuerport auf dem AP finden
  mjpeg.py       Live View als HTTP-Stream
  simulator.py   gefakte Kamera für Entwicklung ohne Hardware
  cli.py         Kommandozeile
docs/
  plan.md                 Phasenplan und Rollenverteilung — hier anfangen
  setup-wsl-glinet.md     Aufbau für Windows/WSL + GL.iNet Mini-Router
  playbook.md             Arbeitsweise: Kern-Loop, Sicherheitsregeln, Backlog
  FINDINGS.md             Messprotokoll — was an echter Hardware belegt ist
  recherche.md            Stand der Technik, wer was schon gemacht hat
  protokoll.md            PTP/IP-Referenz + offene Fragen zur P1100
  reverse-engineering.md  Playbook: BLE-Snoop, Mitschnitt, Auswertung
```

## Entwicklung

```bash
python -m pytest        # 41 Tests, ohne Hardware, gegen den Simulator
ruff check .
```

## Dank

Die Protokollkenntnis stammt aus fremder Vorarbeit: [libgphoto2](http://gphoto.org/)
(PTP/IP-Referenzimplementierung), [gkoh/furble](https://github.com/gkoh/furble)
und [hurui200320/nsg](https://github.com/hurui200320/nsg) (Nikon-BLE),
[HowenXu/snapbridge-id-extractor](https://github.com/HowenXu/snapbridge-id-extractor)
(SnapBridge-DeviceID).

## Lizenz

MIT, siehe [LICENSE](LICENSE).
