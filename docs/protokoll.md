# PTP/IP — Referenz und Annahmen

Diese Datei dokumentiert, was `skyshutter` auf die Leitung legt, und trennt
sauber zwischen **spezifiziert**, **aus libgphoto2 übernommen** und **für die
P1100 noch unbestätigt**.

## Transport

PTP/IP (Annex von ISO 15740) tunnelt PTP über TCP, Standardport **15740**. Es
werden zwei Verbindungen zum selben Port aufgebaut:

* **Command/Data-Kanal** — Operationen und Datenphasen
* **Event-Kanal** — Handshake und Keepalive

> **Korrektur, 23.08.2026:** Hier stand „Event-Kanal — asynchrone Events der
> Kamera". Das ist in der Praxis falsch. Die Hersteller-App **parst den
> Ereignis-Pakettyp nirgends**; sie pollt Ereignisse stattdessen mit einer
> PTP-Operation (`0x941C`, ersatzweise `0x90C7`) alle fünf Sekunden. Der
> zweite Kanal wird trotzdem gebraucht — die Kamera erwartet seinen
> Init-Handshake, und der Keepalive läuft darüber.

**Keepalive:** Ping (Pakettyp `13`) über den **Ereigniskanal**, alle
**9 Sekunden**, Antwort binnen 10 erwartet. Nur auf fremde Pings zu antworten
genügt nicht — die Gegenseite sendet keine. `PtpIpConnection.ping()`.

**Reihenfolge des Aufbaus:** TCP zum Kommandokanal (`TCP_NODELAY`) →
InitCommandRequest → **zweite TCP** → InitEventRequest mit der
Verbindungsnummer → Keepalive starten → `GetDeviceInfo`. `OpenSession` gehört
nicht dazu. Beim Trennen schickt die App **kein** `CloseSession`, sondern
schließt beide Sockets.

**`SessionAlreadyOpen` (`0x201E`) ist kein Fehler**, sondern gilt wie `OK` —
die App arbeitet mit der angefragten Kennung weiter.

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

Die Spalte ganz rechts sagt, ob **diese** Kamera den Opcode anbietet — gemessen
am 23.08.2026. Die Tabelle als Ganzes ist die allgemeine Nikon-Liste; wer sie
für eine Fähigkeitsliste hält, baut auf Sand.

| Opcode | Name | Zweck | hier? |
|---:|---|---|:-:|
| `0x90C0` | Capture | Auslösen (ältere Modelle) | nein |
| `0x90C1` | AfDrive | Autofokus | **ja** |
| `0x90C2` | SetControlMode / ChangeCameraMode | Steuerungsmodus umschalten | **ja** |
| `0x90C7` | GetEvent | Ereignisse abholen | nein |
| `0x90C8` | DeviceReady | Busy-Polling nach Kommandos | **ja** |
| `0x90E0` | GetDevicePTPIPInfo | PTP/IP-spezifische Geräteinfos | nein |
| `0x9200` | GetPreviewImg | Vorschaubild nach Auslösung | nein |
| `0x9201` | StartLiveView | Live View starten | **ja** |
| `0x9202` | EndLiveView | Live View beenden | **ja** |
| `0x9203` | GetLiveViewImg | Einzelnes Live-View-Bild | **ja** |
| `0x9204` | MfDrive | Manueller Fokus | nein |
| `0x9205` | ChangeAfArea | AF-Feld setzen | **ja** |
| `0x9207` | InitiateCaptureRecInMedia | Auslösen mit Speicherziel | **ja** |
| `0x920A` / `0x920B` | Start/EndMovieRecInCard | Videoaufnahme | nein |
| `0x9016` | ZoomControl | optischer Zoom | **ja** |
| `0x941C` | GetEvent, neuere Fassung | Ereignisse abholen | **ja** |

**Maßgeblich ist immer `DeviceInfo.operations_supported`.** `skyshutter info`
gibt genau diese Liste aus; jede High-Level-Methode prüft sie, bevor sie einen
Vendor-Opcode absetzt.

### Was diese Kamera davon anbietet

Am 23.08.2026 über USB ausgelesen: Firmware `V1.0`, **38 Operationen**,
20 Properties, Capture-Format `3801` (EXIF/JPEG). Erhoben mit
`src/skyshutter/ptpusb.py`, nicht abgeschrieben.

> **Die vollständigen Listen stehen in [referenz.md](referenz.md)** —
> Operationen, Properties, Ereignisse und Fehlercodes, jeweils mit Angabe der
> Herkunft. Dieses Dokument beschreibt den Transport; was ein einzelnes Gerät
> kann, gehört dorthin. Zwei Tabellen mit denselben Zahlen laufen früher oder
> später auseinander.

Drei Befunde, die den Client unmittelbar betreffen:

- **`0x90C7 GetEvent` fehlt dieser Kamera**, `0x941C` ist der Ersatz — mit
  einem anderen Antwortformat. Ein Client, der nur den älteren Opcode kennt,
  bekommt still eine leere Ereignisliste statt eines Fehlers.
- **`0x9204 MfDrive` fehlt.** Manueller Fokus über PTP ist nicht möglich.
- **`0x920C` fehlt.** Der Bulb-Weg der Hersteller-App ist nicht verfügbar;
  lange Belichtungen laufen über die Verschlusszeit-Property `0xD100`.

## Live-View-Frames

`GetLiveViewImg` liefert einen Header vor dem JPEG. Bei diesem Modell ist er
**384 Byte lang und big-endian** — anders herum als der PTP-Rahmen darum. Er
trägt Bildmaße, Sensorgröße, sichtbaren Ausschnitt, AF-Felder und einen
Lagesensor.

> **Das vollständige Feldlayout und die Startsequenz stehen in
> [referenz.md](referenz.md)**, Abschnitt Live View.

Zwei Dinge, die beim Implementieren zählen:

- **Das Längenfeld an Offset 4 ist unzuverlässig.** Bei Kameras, die `0x9521`
  anbieten — und diese tut es — nimmt die Hersteller-App stattdessen den Rest
  des Puffers. `skyshutter` schneidet deshalb 384 Byte ab und sucht im Rest den
  SOI-Marker `FF D8 FF` bis zum letzten `FF D9`. Das funktioniert auch bei den
  Modellen, für die 8 oder 128 Byte Header berichtet wurden.
- **`0xD1A4` vor dem Start lesen.** Die Property nennt als Bitmaske, warum Live
  View gesperrt ist; Bit 24 heißt „Objektiv eingefahren" und ist der Grund,
  warum es über USB grundsätzlich nicht geht. In `nikon.py` als
  `LiveViewProhibit`.

## Was am Transport offen bleibt

Die gerätebezogenen Fragen stehen gesammelt in
[FINDINGS.md](FINDINGS.md#offene-fragen); hier nur, was den Transport selbst
betrifft:

- [ ] **Antwortet die Kamera über WLAN auf TCP 15740?** Der Port steht im
      Herstellercode, geöffnet hat sie ihn für uns noch nie. Über USB ist PTP
      bestätigt — das sagt über den TCP-Weg nichts.
- [ ] **Wird eine beliebige GUID akzeptiert?** Die Hersteller-App benutzt für
      alle Installationen dieselbe, was dagegen spricht, dass die Kamera
      darüber unterscheidet. Ungeprüft.
- [ ] **Verträgt die Kamera eine zweite Sitzung neben der App?**
- [ ] **Der Gerätename im Init-Paket:** Die App kodiert ihn als UTF-16 **BE**,
      liest ihn selbst aber als LE zurück — Encoder und Decoder widersprechen
      sich, und die Kamera nimmt es offenbar hin. `skyshutter` sendet
      spezifikationskonform LE. Falls ein Verbindungsaufbau daran scheitert,
      ist BE der erste Gegenversuch.
