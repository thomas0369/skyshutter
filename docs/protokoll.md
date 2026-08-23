# PTP/IP — Referenz und Annahmen

Diese Datei dokumentiert, was `skyshutter` auf die Leitung legt, und trennt
sauber zwischen **spezifiziert**, **aus libgphoto2 übernommen** und **für die
P1100 noch unbestätigt**.

## Transport

PTP/IP (Annex von ISO 15740) tunnelt PTP über TCP, Standardport **15740**. Es
werden zwei Verbindungen zum selben Port aufgebaut:

* **Command/Data-Kanal** — Operationen und Datenphasen
* **Event-Kanal** — asynchrone Events der Kamera

Rahmenformat, alles Little Endian:

```
+0  uint32  Länge, inklusive dieser 8 Header-Bytes
+4  uint32  Pakettyp
+8  Payload
```

| Typ | Name | Payload |
|---:|---|---|
| 1 | InitCommandRequest | GUID (16 B) + Name (UTF-16LE, NUL-terminiert) + Version (uint32, `0x00010000`) |
| 2 | InitCommandAck | ConnectionNumber (uint32) + GUID (16 B) + Name (UTF-16LE) + Version |
| 3 | InitEventRequest | ConnectionNumber (uint32) |
| 4 | InitEventAck | — |
| 5 | InitFail | Grund (uint32) |
| 6 | OperationRequest | DataPhase (uint32) + Opcode (uint16) + TransactionID (uint32) + bis zu 5 Parameter |
| 7 | OperationResponse | ResponseCode (uint16) + TransactionID (uint32) + Parameter |
| 8 | Event | EventCode (uint16) + TransactionID (uint32) + Parameter |
| 9 | StartData | TransactionID (uint32) + Gesamtlänge (uint64) |
| 10 | Data | TransactionID (uint32) + Payload |
| 11 | Cancel | TransactionID (uint32) |
| 12 | EndData | TransactionID (uint32) + Payload |
| 13 / 14 | Ping / Pong | — |

`DataPhase` ist `1` für „keine Daten oder Daten-In" und `2` für „Daten-Out".

Quelle für die Offsets: `libgphoto2/camlibs/ptp2/ptpip.c`. Das ist die einzige
breit eingesetzte Referenzimplementierung für Nikons Variante.

## Die GUID ist die Authentifizierung

Nikon-Kameras führen eine Liste gepaarter Client-GUIDs. Eine unbekannte GUID
beantwortet die Kamera mit `InitFail` — das ist der erwartete Fehler, solange
noch kein Pairing existiert. `skyshutter` legt seine GUID einmalig in
`~/.config/skyshutter/config.json` an und benutzt sie danach konstant;
`--guid` bzw. `SKYSHUTTER_GUID` überschreiben sie, z. B. mit der aus dem
SnapBridge-Pairing rekonstruierten ID.

Die GUID geht als 16 rohe Bytes über die Leitung. `skyshutter` verwendet die
RFC-4122-Byte-Reihenfolge, sodass die String-Darstellung genau der Hex-Folge im
Wireshark-Mitschnitt entspricht.

**Die GUID der Hersteller-App ist bekannt** (23.08.2026, aus dem dekompilierten
Verbindungsaufbau):

```
GUID          00112233-4455-6677-8899-AABBCCDDEEFF
Name          "Android Device"
Port          15740   (steht dort als 0x3d7c)
Timeout       300 s
```

Sie ist offensichtlich ein Platzhalter und über alle Installationen gleich —
die Kamera unterscheidet ihre Clients also nicht über die GUID. Falls ein
Verbindungsaufbau mit einer eigenen GUID scheitert, ist diese der erste
Gegentest. Sie kursierte im dslrdashboard-Forum ohne Herkunftsangabe; jetzt ist
klar, woher sie stammt.

**SSID und Passphrase des Kamera-APs sind auch über PTP erreichbar** —
`GetWmaSetting` / `SetWmaSetting` (WMA = Wireless Mobile Adapter) lesen und
**setzen** sie über Device-Properties. Das ist der Weg an der
BLE-Verschlüsselung vorbei: Über Bluetooth liegen sie chiffriert in `0x2004`,
über PTP im Klartext.

**Die Kamera-IP wird nicht geraten.** Die App liest die DHCP-Server-Adresse des
Lease, den sie im Kameranetz bekommt — die Kamera ist der DHCP-Server ihres
eigenen APs. `discovery.py` sollte denselben Weg gehen, statt eine Liste
wahrscheinlicher Adressen durchzuprobieren.

## Nikon-Vendor-Opcodes

Reverse-engineert, nicht von Nikon veröffentlicht; Werte aus `libgphoto2`:

| Opcode | Name | Zweck |
|---:|---|---|
| `0x90C0` | Capture | Auslösen (ältere Modelle) |
| `0x90C1` | AfDrive | Autofokus |
| `0x90C2` | SetControlMode | Steuerungsmodus umschalten |
| `0x90C7` | GetEvent | Event-Queue leeren |
| `0x90C8` | DeviceReady | Busy-Polling nach Kommandos |
| `0x90E0` | GetDevicePTPIPInfo | PTP/IP-spezifische Geräteinfos |
| `0x9200` | GetPreviewImg | Vorschaubild nach Auslösung |
| `0x9201` | StartLiveView | Live View starten |
| `0x9202` | EndLiveView | Live View beenden |
| `0x9203` | GetLiveViewImg | Einzelnes Live-View-Bild |
| `0x9204` | MfDrive | Manueller Fokus / Fokusschritte |
| `0x9205` | ChangeAfArea | AF-Feld setzen |
| `0x9207` | InitiateCaptureRecInMedia | Auslösen mit Speicherziel |
| `0x920A` / `0x920B` | Start/EndMovieRecInCard | Videoaufnahme |

**Maßgeblich ist immer `DeviceInfo.operations_supported`.** `skyshutter info`
gibt genau diese Liste aus; jede High-Level-Methode prüft sie, bevor sie einen
Vendor-Opcode absetzt.

### Gemessen am 23.08.2026 über USB

Firmware `V1.0`, 38 Operationen, 20 Properties, Capture-Format `3801`
(EXIF/JPEG). Erhoben mit `src/skyshutter/ptpusb.py`, nicht abgeschrieben.

```
1001 1002 1003 1004 1005 1006 1007 1008 1009 100a 100b 100c 100d 100e 100f
1014 1015 1016 101b
9016 90c1 90c2 90c4 90c8 9201 9202 9203 9205 9207 941c 941e 9520 9521 9522
9801 9802 9803 9805
```

Davon belegt: `90c1` AfDrive, `90c2` SetControlMode, `90c4` GetLargeThumb,
`90c8` DeviceReady, **`9201` StartLiveView**, **`9202` EndLiveView**,
**`9203` GetLiveViewImg**, `9205` ChangeAfArea, `9207`
InitiateCaptureRecInMedia. `9801`–`9805` sind MTP-Objekt-Properties.
Unbekannt bleiben `9016`, `941c`, `941e`, `9520`, `9521`, `9522`.

**Nicht vorhanden:** `90c0` Capture, `90c7` GetEvent, `90e0`
GetDevicePTPIPInfo, `9200` GetPreviewImg, `9204` MfDrive, `920a`/`920b`
Movie. Der manuelle Fokus über `MfDrive` fehlt dieser Kamera also — für
Astro-Fokussierung bleibt nur `AfDrive` und `ChangeAfArea`.

Properties: `5001` Batterie, `5007` Blende, **`5008` Brennweite (schreibbar,
24–3000 mm)**, `500a` Fokusmodus, `500e` Belichtungsprogramm, `500f` ISO,
`5010` Belichtungskorrektur, `5011` Datum/Zeit, `5013`, dazu die Vendor-Reihe
`d05d d0e1 d0e3 d0e4 d100 d1a2 d1a4 d1f1 d303 d406 d407`.

## Live-View-Frames

`GetLiveViewImg` liefert einen Header vor dem JPEG. Bei diesem Modell ist er
**384 Byte lang und big-endian** — anders herum als der PTP-Rahmen drumherum.
Aus der Hersteller-App gelesen, 23.08.2026:

| Offset | Typ | Feld |
|---|---|---|
| `0x04` | u32 | JPEG-Länge (nur als Plausibilitätsprüfung, s.u.) |
| `0x08` / `0x0A` | s16 | Bildbreite / -höhe |
| `0x0C` / `0x0E` | s16 | Sensor-Gesamtgröße |
| `0x10`–`0x16` | 4× s16 | sichtbarer Ausschnitt: Breite, Höhe, Mitte x, Mitte y |
| `0x18`–`0x1E` | 4× s16 | AF-Feld, dieselben vier Werte |
| `0x25` | s8 | Drehrichtung |
| `0x26` / `0x27` | s8 | Fokus- und Zoomantrieb (nur Status) |
| `0x2E` | s16 | Selbstauslöser-Restzeit |
| `0x30` / `0x31` | s8 | Fokuszustand, Fokusfähigkeit |
| `0x34` / `0x38` / `0x3C` | s32 | **Lagesensor: Roll, Pitch, Yaw** |
| `0x40` | s32 | Video-Restzeit |
| `0x46` / `0x47` | u8 | Anzahl Gesichtsfelder, aktives Feld |
| `0x48`–`0x15F` | 35× 8 B | AF-Feld-Array |
| `0x180` | | **JPEG** |

**Belichtungswerte stehen nicht im Header** — die kommen über Properties. Einen
Zoomfaktor gibt es auch nicht; er folgt aus Sensorgröße geteilt durch sichtbaren
Ausschnitt.

**Das Längenfeld ist unzuverlässig.** Bei Kameras, die `0x9521` anbieten — und
diese tut es — nimmt die App stattdessen den Rest des Puffers. `skyshutter`
schneidet deshalb 384 Byte ab und sucht im Rest den SOI-Marker `FF D8 FF` bis
zum letzten `FF D9`. Das funktioniert auch bei den Modellen, für die 8 oder
128 Byte berichtet wurden.

### Live View starten

Die App prüft der Reihe nach, bevor sie `0x9201` schickt:

1. `0xD0BD` Fernauslöse-Sperre lesen
2. **`0xD1A4` Live-View-Sperre lesen — muss 0 sein**
3. `0xD09C` Objektivwarnung lesen
4. Kameramodus umschalten
5. Steht `0x5013` auf Serienbild, auf Einzelbild zurückstellen
6. modellabhängig 500 ms warten
7. `0xD1A2` prüfen — läuft Live View schon, `0x9201` überspringen
8. `0x9201` (**parameterlos**), dann `0x90C8` pollen

Bei `DeviceBusy` wiederholt sie `0x9201` bis zu zehnmal mit 500 ms Abstand.
Danach holt ein Timer alle **66 ms** ein Bild — rund 15 Bilder je Sekunde.
Nach fünf Fehlern in Folge bricht sie ab.

`0xD1A4` ist eine **Bitmaske**, kein Fehlercode: Bit 24 ist „Objektiv
eingefahren", daneben unter anderem Bit 23 ausgeschaltet, Bit 17 zu heiß, Bit 8
Batterie leer, Bit 19 Kartenfehler. In `nikon.py` als `LiveViewProhibit`.

## Offene Fragen für die P1100

- [ ] Antwortet die Kamera im Remote-Modus überhaupt auf TCP 15740?
- [ ] Wird eine ungepaarte GUID akzeptiert, oder ist der BLE-Handshake Pflicht?
- [ ] Welche Vendor-Opcodes stehen in `operations_supported`?
- [ ] Live View vorhanden — und mit welcher Header-Länge und Auflösung?
- [ ] Gibt es Vendor-Properties für den 125×-Zoom (die eigentliche Motivation)?
- [ ] Verträgt die Kamera parallele Sessions neben SnapBridge?
