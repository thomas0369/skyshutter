# Stand der Recherche (August 2026)

Ziel des Projekts: eine eigene API für **Livebild + Steuerung** der Nikon Coolpix
P1100 über WLAN. Kein existierendes Open-Source-Projekt deckt Coolpix-WiFi-Remote
ab — die Vorarbeit für beide Hälften (BLE-Handshake und WiFi-Protokoll) existiert
aber, sodass nur das Coolpix-spezifische Stück selbst reverse-engineert werden muss.

## Existierende Projekte

| Projekt | Deckt ab | Coolpix-relevant | Status |
|---|---|---|---|
| [gkoh/furble](https://github.com/gkoh/furble) (ESP32, C++) | ML-L7-BLE-Remote-Protokoll, reverse-engineered via Wireshark/HCI-Snoop | **Ja** — Coolpix B600 bestätigt; P1100 unterstützt ML-L7 → sehr wahrscheinlich kompatibel. Nur Shutter, kein Fokus/GPS/Bild | Aktiv |
| [hurui200320/nsg](https://github.com/hurui200320/nsg) (Kotlin/ESP32) | SnapBridge-Smart-Device-BLE-Protokoll: Pairing, Auth, Payload-Format, basiert auf furble-RE | Z-Serie verifiziert; Pairing-Mechanik vermutlich identisch | Aktiv (Push 15.08.2026) |
| [HowenXu/snapbridge-id-extractor](https://github.com/HowenXu/snapbridge-id-extractor) | Rekonstruiert die SnapBridge-DeviceID (invertiert `java.util.Random(timestamp).nextBytes(8)`) | Ja — nötig, um neben SnapBridge zu koexistieren | Neu (Aug 2026) |
| libgphoto2 | PTP/PTP-IP generisch | **Nein** — P1000-Support-Anfrage (Issue #477) seit Feb 2020 offen. Coolpix fehlt in der Remote-Liste | Keine Coolpix-Arbeit |
| Zeris Remote (Reddit-Alpha) | Direkter WiFi-Client ohne Bluetooth, Live View + Shutter | Nein — explizit nur Z-Serie, closed source | Beweist: Nikon-Remote via PTP/IP über WiFi ist machbar |
| Vorbilder anderer Marken | [hkr/fuji-cam-wifi-tool](https://github.com/hkr/fuji-cam-wifi-tool), [petabyt/fudge](https://github.com/petabyt/fudge), [frank26080115/alpha-fairy](https://github.com/frank26080115/alpha-fairy) | Methodik-Blaupausen | — |

## Die Lücke

Das WiFi-Protokoll der Coolpix im SnapBridge-Remote-Modus ist nirgends öffentlich
dokumentiert. Bei Z-Kameras ist es PTP/IP (TCP 15740, GUID-Auth aus dem
BLE-Pairing); die Coolpix-Linie nutzt mit hoher Wahrscheinlichkeit dasselbe
Grundprotokoll mit Nikon-Vendor-Opcodes für Live View und Zoom — **verifiziert ist
das für die P1100 nicht.** Genau diese Annahme prüft `skyshutter probe`.

## Hardware-Randbedingung

HDMI-Out und WLAN schließen sich an der P1100 laut Handbuch gegenseitig aus. Ein
WiFi-Livebild ist damit kein Zusatz zum HDMI-Weg, sondern dessen Alternative.

## Arbeitsplan

1. **BLE-Seite:** Android-Handy, Bluetooth-HCI-Snoop-Log aktivieren, SnapBridge-Pairing +
   Remote-Start mitschneiden → Handshake, der die WiFi-Credentials aushandelt
   (nsg-Code als Referenz).
2. **WiFi-Seite:** Im Kamera-AP `tcpdump` auf dem Phone, oder den Phone-Traffic über
   den GL-X3000 routen und dort mitschneiden → Port, Protokoll, Live-View-Opcodes.
   Details in [reverse-engineering.md](reverse-engineering.md).
3. **Client:** Wenn PTP/IP bestätigt ist, greift der Client in diesem Repo direkt.
   Abweichungen landen in [protokoll.md](protokoll.md).
4. **Quick-Win parallel:** furble auf einem ESP32 flashen und gegen die P1100 testen —
   kostet einen Abend und liefert sofort einen stabilen BLE-Auslöser (nur Shutter).

Ein MCP-Server auf Basis des fertigen Clients wäre ein naheliegender nächster
Schritt, sobald das Protokoll steht — vorher nicht.
