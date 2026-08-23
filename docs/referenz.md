# Referenz — was die Kamera kann

Nachschlagewerk. Alles hier ist **an der Hardware gemessen** oder aus dem
dekompilierten Herstellercode gelesen; die Herkunft steht an jedem Abschnitt.
Wer wissen will, *wann* und *wie* etwas festgestellt wurde, findet das im
chronologischen [Messprotokoll](FINDINGS.md).

| Legende | Bedeutung |
|---|---|
| **M** | an dieser Kamera gemessen |
| **H** | aus dem Herstellercode gelesen, an der Hardware unbestätigt |
| **F** | Fremdmessung an einem anderen Gerät |

---

## 1. Bluetooth Low Energy

### Dienst und Characteristics **[M]**

Vendor-Service `0000DE00-3DD4-4255-8D62-6DC7B9BD5561`, Handles `0x0029`–`0x0051`.
Alle Characteristics liegen auf derselben Vendor-Basis, **nicht** auf der
Bluetooth-Basis.

| UUID16 | Name **[H]** | Value-Handle | Properties | Ruhewert **[M]** |
|---|---|---|---|---|
| `0x2000` | AUTHENTICATION | `0x002B` | read, write, indicate | 17 Null-Bytes |
| `0x2001` | POWER_CONTROL | `0x002E` | read, write | `03` |
| `0x2002` | CLIENT_DEVICE_NAME | `0x0030` | write | — |
| `0x2003` | SERVER_DEVICE_NAME | `0x0032` | read | Gerätename, 32 B |
| `0x2004` | CONNECTION_CONFIGURATION | `0x0034` | read, write | 102 B, s. u. |
| `0x2005` | CONNECTION_ESTABLISHMENT | `0x0036` | read, write | `03` |
| `0x2006` | CURRENT_TIME | `0x0038` | read, write | 10 B |
| `0x2007` | LOCATION_INFORMATION | `0x003A` | write | — |
| `0x2008` | LSS_CONTROL_POINT | `0x003C` | read, write, notify | `1100` |
| `0x2009` | LSS_FEATURE | `0x003F` | read | `fd010000` |
| `0x2A19` | BATTERY_LEVEL | `0x0041` | read | `64` = 100 % |
| `0x200B` | LSS_SERIAL_NUMBER_STRING | `0x0043` | read | Seriennummer, 33 B |
| `0x2080` | LSS_CATEGORY_INFO | `0x0045` | read | `03000000` |
| `0x2082` | *unbekannt* | `0x0047` | read, write | 32 B Wertetabelle |
| `0x2083` | *unbekannt* | `0x0049` | write | — |
| `0x2084` | *unbekannt* | `0x004B` | read, indicate | 6 Null-Bytes |
| `0x2086` | *unbekannt* | `0x004E` | read | `03000000` |
| `0x2087` | *unbekannt* | `0x0050` | read, write, indicate | 17 Null-Bytes |

**Nicht vorhanden:** `0x200A`, `0x2020`, `0x2021`, `0x2081`, `0x2085`.

**`0x2082`–`0x2087` kennt die Hersteller-App nicht** — Volltextsuche über die
gesamte App, null Treffer. Kein Mitschnitt wird sie je zeigen, weil die App sie
nie anfasst. Sie sind nur durch Messung an der Kamera zu erschließen.

Die vier notify/indicate-fähigen Characteristics haben je einen CCCD auf
Value-Handle + 1 (`0x002C`, `0x003D`, `0x004C`, `0x0051`) — abgeleitet aus den
Handle-Lücken, nicht direkt gemessen.

### Fähigkeiten aus `0x2009` **[H]**

uint32 little-endian. Gemessen `fd010000` = `0x000001FD`:

| Bit | Fähigkeit | diese Kamera |
|---|---|---|
| 0 | Client-/Servername | ja |
| 1–2 | PowerControl | **WAKE_SUPPORT** (Wert 2) |
| 3 | Bluetooth konfigurieren | ja |
| 4 | WLAN konfigurieren | ja |
| 5 | Bildübertragung | ja |
| 6 | Zeit | ja |
| 7 | Standort | ja |
| 8 | Batteriestand | ja |
| 9 | Kabelerkennung | nein |
| 10 | Verbindung-nicht-nötig | nein |
| **11** | **Kamerasteuerung** | **nein** |
| 12 | Firmware-Übertragung | nein |
| 13 | BTC-Kooperation | nein |

**Bit 11 ist null: Auslösen über Bluetooth ist an dieser Kamera nicht möglich.**
Der Fernsteuerpfad der App läuft über `0x2020`/`0x2021`, die diese Kamera nicht
anbietet — zwei unabhängige Belege für denselben Befund.

### Authentifizierung auf `0x2000` **[M]**

Vier Stufen, je 17 Byte: Stufenbyte, 8 Byte Zeitstempel, 4 Byte Geräte-ID,
4 Byte Nonce. Auf dem Draht little-endian, in der Rechnung big-endian.

```
Client  →  01 ‖ Zeitstempel ‖ Geräte-ID ‖ Nonce
Kamera  →  02 ‖ eigener Zeitstempel ‖ Challenge (2×4 B)
Client  →  03 ‖ Zeitstempel aus Stufe 1 ‖ Antwort (2×4 B)
Kamera  →  04 ‖ 8 Null-Bytes ‖ interne Seriennummer (8 B)
```

Verkettetes Blowfish/ECB, Schlüssel `ffffaa5511223300`, Startzustand
links `0x01020304`, rechts `0x05060708`. Je zwei Wörter werden mit dem Zustand
XOR-verknüpft und verschlüsselt; der Chiffretext wird zum neuen Zustand.

Acht Salt-Paare stehen zur Wahl; die Kamera nimmt eines, der Client muss es
suchen. **Die Wortreihenfolge dreht sich zwischen Suche und Antwort:** bei der
Suche `[salt_a, salt_b, cam_lo, cam_hi, our_lo, our_hi]`, bei der Antwort
`[salt_a, salt_b, our_lo, our_hi, cam_lo, cam_hi]`. Wer das vertauscht, findet
kein passendes Salt und erfährt nicht, warum.

**Die interne Seriennummer aus Stufe 4 ist nicht die aufgedruckte.** Gemessen
endet sie auf zwei Bytes, die kein ASCII sind. Die App prüft diesen Wert.

Implementierung: `tools/nikon_pairing.py`.

### `0x2005` — der WLAN-Auslöser **[H]**

Ein Byte, Bitfeld:

| Bit | Maske | Bedeutung |
|---|---|---|
| 0 | `0x01` | **WLAN aufbauen** |
| 1 | `0x02` | Bluetooth Classic aufbauen |
| 7 | `0x80` | Verbindung nicht mehr nötig |

Der Encoder schreibt alle drei Bits, der Decoder liest nur Bit 0 und 1 zurück.
**Der gemessene Wert `03` ist deshalb kein Ruhewert, sondern eine Statusmeldung:
„WLAN und Bluetooth aktiv".** Diese Verwechslung hat uns einen Tag gekostet.

Ablauf der App: `0x2004` lesen → prüfen, ob ein WLAN-Block da ist → **`0x01` auf
`0x2005` schreiben** → einbuchen.

### `0x2004` — Zugangsdaten, 102 Byte **[H]**

| Offset | Länge | Feld |
|---|---|---|
| 0 | 1 | Flags: Bit0 WLAN-Block, Bit1 BT-Block |
| 1 | 32 | SSID, verschlüsselt |
| 33 | 64 | Passwort, verschlüsselt |
| 97 | 1 | Verschlüsselungsmodus |
| 98 | 4 | `sppMaxDataLength` (nur BT-Block) |

Gemessen: `03` + 96 Null-Bytes + `03ef010000` — Flags `0x03`, Modus `0x03`,
`sppMaxDataLength` = 495. **Dass SSID und Passwort leer waren, ist selbst ein
Befund:** gelesen wurde als ungekoppelter Client.

Die Characteristic ist **nur lesbar**; die Zugangsdaten lassen sich über BLE
nicht setzen. Über PTP schon (`GetWmaSetting`/`SetWmaSetting`).

### `0x2008` — Anforderungsfeld, kein Auslöser **[H]**

Zwei Byte, uint16 little-endian, drei Vier-Bit-Felder:

| Bits | Feld | Werte |
|---|---|---|
| 0–3 | Zeit anfordern | 0 aus, 1 an |
| 4–7 | Standort anfordern | 0 aus, 1 an, 2 mit GPS |
| 8–11 | Verbindung anfordern | 0 aus, 1 an |

Gemessen `1100` → `0x0011` → Zeit **an**, Standort **an**, Verbindung **aus**.
`00 01` setzt die Verbindungsanforderung — zweiter Kandidat für den WLAN-Start,
im Herstellercode aber nicht als solcher belegt.

### Verschlüsselung der Zugangsdaten **[M]** — geknackt

Blowfish, **vollständig nachgebaut und verifiziert** (23.08.2026, gegen die
native Bibliothek als Orakel und zwei echte Klartext-Chiffrat-Paare).
Implementierung: `src/skyshutter/lssec.py`, reines Python, keine Abhängigkeit.

Alle Blowfish-Wörter big-endian. Die Kette:

```
feste Transform : Blowfish, Schlüssel ffffaa5511223300 (= Handshake-Schlüssel),
                  CBC, IV L=0x01020304 R=0x05060708
Salt-Index      : das Salt (0-7), dessen Transform über
                  SALT ‖ cam_ts ‖ own_ts die Stufe-2-Challenge reproduziert
field_a (8 B)   : [Salt-Index] ‖ cam_ts[1:4] ‖ own_ts[0:4]
Sitzungsschlüssel: letzter CBC-Block der Transform über
                  Stufe-4-Payload ‖ Geräte-ID ‖ field_a
entschlüsseln    : Blowfish-CBC, Schlüssel = Sitzungsschlüssel, IV = 0
                  SSID = 32 B, Passwort = 64 B aus 0x2004, je nullterminiert
```

**`cam_ts` und `own_ts` sind die Handshake-Zeitstempel** (Stufe 2 bzw. Stufe 1),
nicht die device/nonce-Felder — das war der Irrtum, der es lange blockiert hat.
Der Nutzdaten-IV ist schlicht null.

**Konsequenz:** Die WLAN-Zugangsdaten lassen sich aus dem BLE-Chiffrat berechnen,
für jede Kopplung — auch wenn das Passwort rotiert. Kein Gerätegeheimnis nötig,
nur die Werte, die der Client beim Pairing ohnehin sieht.

---

## 2. Kopplung

Zwei Hälften, beide nötig. Details und Fallstricke: [pairing.md](pairing.md).

```
Kameramenü öffnen
      │
[1] BLE-Handshake auf 0x2000, dann Clientname auf 0x2002
      │
[2] klassischer Inquiry, Bonding, Zahlencode an der Kamera bestätigen
      │
   „Your camera and smart device are connected!"
```

Gemessen: **40 Sekunden** vom Funk-Reset bis zum Bond, davon 25 Sekunden
Funk-Hochlauf. Der eigentliche Vorgang dauert 15 Sekunden.

---

## 3. PTP

### Verbindungsaufbau **[H]**

```
1. TCP zum Kommandokanal, Port 15740, TCP_NODELAY
2. InitCommandRequest  → InitCommandAck
3. zweite TCP zum Ereigniskanal
4. InitEventRequest mit der Verbindungsnummer → InitEventAck
5. Keepalive starten
6. GetDeviceInfo
```

Protokollversion `0x00010000`. GUID als 16 Byte in String-Reihenfolge.
Lesepuffer 102.400 Byte. Beim Trennen schickt die App **kein** `CloseSession`.

**Keepalive:** Ping (Pakettyp `0x0D`) über den **Ereigniskanal**, alle
**9 Sekunden**, Antwort binnen 10. Wer nur auf fremde Pings antwortet, hält die
Verbindung nicht.

**Ereignisse werden gepollt, nicht empfangen.** Der Paketparser der App
behandelt den Ereignis-Pakettyp nirgends; der Kanal trägt nur Handshake und
Keepalive.

**`SessionAlreadyOpen` (`0x201E`) ist kein Fehler** — die App arbeitet mit der
angefragten Kennung weiter.

Die GUID der Hersteller-App ist für alle Installationen dieselbe:
`00112233-4455-6677-8899-AABBCCDDEEFF`, Name `Android Device`. Die Kamera
unterscheidet ihre Clients also nicht über die GUID.

### Unterstützte Operationen **[M]**

38 Stück, am 23.08.2026 über USB ausgelesen. Namen aus dem Herstellercode.

**Standard**

`1001` GetDeviceInfo · `1002` OpenSession · `1003` CloseSession ·
`1004` GetStorageIDs · `1005` GetStorageInfo · `1006` GetNumObjects ·
`1007` GetObjectHandles · `1008` GetObjectInfo · `1009` GetObject ·
`100A` GetThumb · `100B` DeleteObject · `100C` SendObjectInfo ·
`100D` SendObject · `100E` InitiateCapture · `100F` FormatStore ·
`1014` GetDevicePropDesc · `1015` GetDevicePropValue ·
`1016` SetDevicePropValue · `101B` GetPartialObject

**Vendor**

| Opcode | Name | Parameter |
|---|---|---|
| `9016` | **ZoomControl** | `[weitwinkel, tele]`, nur einer belegt |
| `90C1` | AfDrive | keine |
| `90C2` | ChangeCameraMode (bei libgphoto2: SetControlMode) | Modus |
| `90C4` | GetLargeThumb | Handle |
| `90C8` | DeviceReady | keine |
| `9201` | StartLiveView | **keine** |
| `9202` | EndLiveView | keine |
| `9203` | GetLiveViewImg | keine |
| `9205` | ChangeAfArea | `[x, y]` |
| `9207` | InitiateCaptureRecInMedia | `[auslöseart, ziel]` |
| `941C` | **GetEvent, neue Variante** | keine |
| `941E` | PowerZoomByFocalLength | unbekannt |
| `9520` | Auto-Übertragung | `0x11` start, `0x22` stop |
| `9521` | Liste markierter Objekte | `0` |
| `9522` | Teilobjekt in wählbarer Größe | `[handle, größe, 0]` |
| `9801`–`9805` | MTP-Objekt-Properties | — |

**Nicht vorhanden, obwohl bei Nikon üblich:** `90C0` Capture · `90C7` GetEvent ·
`90E0` GetDevicePTPIPInfo · `9200` GetPreviewImg · **`9204` MfDrive** ·
`920A`/`920B` Video · `920C` TerminateCapture · `9464` ZZoomDrive.

**Für die Praxis wichtig:**
- **`90C7` fehlt, `941C` ist der Ersatz.** Ein Client, der nur `90C7` kennt,
  bekommt still eine leere Ereignisliste statt eines Fehlers.
- **`9204` MfDrive fehlt.** Manueller Fokus über PTP ist nicht möglich; für die
  Astro-Fokussierung bleiben `90C1` und `9205`.
- **`920C` fehlt.** Der Bulb-Weg der App ist nicht verfügbar; lange
  Belichtungen müssen als normale Verschlusszeit über `0xD100` gesetzt werden.

### Ereignisse **[H]**

| Code | Bedeutung | Parameter |
|---|---|---|
| `4002` | ObjectAdded | Objekt-Handle |
| `4005` | StoreRemoved | Storage-ID |
| `4006` | DevicePropChanged | Property-Code |
| `400A` | StoreFull | Storage-ID |
| `400D` | CaptureComplete | Transaktions-ID |
| `C105` | Aufnahme unterbrochen | Fehler, Ziel |
| `C108` | Videoaufnahme fertig | Ziel |
| `C10A` | Videoaufnahme gestartet | Ziel |
| `C700` | LSS-Sammelcode | 1 Übertragung, 2 Zeit, 3 Ort |

Die beiden Abfragen haben **verschiedene Antwortformate**: `90C7` zählt in
16 Bit mit genau einem Parameter je Ereignis, `941C` in 32 Bit mit variabler
Parameterzahl.

### Properties **[M]**

20 Stück gemessen. Namen aus dem Herstellercode.

| Code | Name | Anmerkung |
|---|---|---|
| `5001` | Batteriestand | |
| `5007` | Blende | |
| `5008` | Brennweite | **nur lesen** — gezoomt wird über `9016` |
| `500A` | Fokusmodus | `0001` manuell, `80xx` diverse AF-Modi |
| `500E` | Belichtungsprogramm | M nötig für lange Zeiten |
| `500F` | ISO | |
| `5010` | Belichtungskorrektur | |
| `5011` | Datum und Zeit | |
| `5013` | Aufnahmemodus | Einzel, Serie, Selbstauslöser |
| `D05D` | AF-Messfeld | |
| `D0E1` | Objektivtyp | |
| `D0E3` / `D0E4` | Brennweite min / max | gemessen 24 mm / **3000 mm** |
| `D100` | **Verschlusszeit** | Zähler/Nenner; `ffff/ffff` = Bulb |
| `D1A2` | Live-View-Status | |
| `D1A4` | **Live-View-Sperrgrund** | Bitmaske, s. u. |
| `D1F1` | verbleibende Aufnahmen | |
| `D303`, `D406`, `D407` | *unbekannt* | kommen in der App nicht vor |

**Nicht vorhanden:** `500D` ExposureTime (die App liest sie als Vorbedingung),
`5018` BurstNumber, `D06B` Rauschunterdrückung.

### Live View **[H]**

Der Header ist **384 Byte lang und big-endian** — anders herum als der
PTP-Rahmen darum.

| Offset | Typ | Feld |
|---|---|---|
| `0x04` | u32 | JPEG-Länge (unzuverlässig, s. u.) |
| `0x08` / `0x0A` | s16 | Bildbreite / -höhe |
| `0x0C` / `0x0E` | s16 | Sensor-Gesamtgröße |
| `0x10`–`0x16` | 4× s16 | sichtbarer Ausschnitt: B, H, Mitte x, Mitte y |
| `0x18`–`0x1E` | 4× s16 | AF-Feld, dieselben vier Werte |
| `0x25` | s8 | Drehrichtung |
| `0x2E` | s16 | Selbstauslöser-Restzeit |
| `0x30` / `0x31` | s8 | Fokuszustand, Fokusfähigkeit |
| `0x34` / `0x38` / `0x3C` | s32 | **Lagesensor: Roll, Pitch, Yaw** |
| `0x40` | s32 | Video-Restzeit |
| `0x46` / `0x47` | u8 | Gesichtsfelder: Anzahl, aktives |
| `0x48`–`0x15F` | 35× 8 B | AF-Feld-Array |
| `0x180` | | **JPEG** |

Belichtungswerte stehen **nicht** im Header. Einen Zoomfaktor gibt es auch
nicht — er folgt aus Sensorgröße geteilt durch sichtbaren Ausschnitt.

**Das Längenfeld ist unzuverlässig:** Bei Kameras, die `9521` anbieten — und
diese tut es — nimmt die App stattdessen den Rest des Puffers.

**Startsequenz der App:** `D0BD` Fernauslöse-Sperre lesen → **`D1A4` lesen, muss
0 sein** → `D09C` Objektivwarnung → Kameramodus umschalten → Serienbild auf
Einzelbild → 500 ms warten → `D1A2` prüfen → `9201` → `90C8` pollen. Bei
`DeviceBusy` bis zu zehnmal mit 500 ms Abstand. Danach ein Bild alle **66 ms**,
also rund 15 je Sekunde; nach fünf Fehlern in Folge Abbruch.

### `D1A4` — warum Live View blockiert **[H]**

Bitmaske, kein Fehlercode; mehrere Gründe können gleichzeitig gelten.

| Bit | Grund |
|---|---|
| 2 | Ablauffehler |
| 5 | minimale Blende |
| 8 | Batterie zu schwach |
| 9 | TTL-Fehler |
| 11 | kein CPU-Objektiv |
| 12 | Bild im Zwischenspeicher |
| 14 | keine Karte, Auslöser gesperrt |
| 15 | Aufnahmebefehl läuft |
| 17 | Temperatur zu hoch |
| 18 | Karte schreibgeschützt |
| 19 | Kartenfehler |
| 20 | Karte nicht formatiert |
| 21 | Zeitautomatik aktiv |
| 22 | Spiegelvorauslösung |
| 23 | ausgeschaltet |
| **24** | **Objektiv eingefahren** |
| 31 | Belichtungsmodus unpassend (von der App ignoriert) |

**Bit 24 ist das, was jeden USB-Versuch blockiert** — die Kamera zieht das
Objektiv ein, sobald ein Kabel steckt.

### Aufnahmepfad **[H]**

```
0x9207 (auslöseart, ziel)   auslöseart: -1 normal, -2 mit Autofokus
                            ziel: 0 Karte, 1 Zwischenspeicher, 2 beides
0x90C8                      pollen, bis nicht mehr DeviceBusy (0x2019)
Ereignis 0x4002             liefert den Handle
0x1008                      Größe ermitteln
0x101B                      in 1-MiB-Blöcken holen, mit Fortsetzungs-Offset
```

Die App benutzt **`0x1009` GetObject nie** — alles läuft über
`GetPartialObject`, ohne Größenschwelle. Das macht Übertragungen fortsetzbar.

Speicherziel `1` schreibt in den Zwischenspeicher statt auf die Karte. Die App
setzt immer `0`; die Kamera kann beides.

### Vendor-Fehlercodes **[H]**

`A001` Hardwarefehler · `A002` Fokus nicht gefunden · `A003` Moduswechsel
fehlgeschlagen · `A004` ungültiger Zustand · `A00B` **nicht im Live View** ·
`A00C`/`A00E` Fokusantrieb am Anschlag · `A021` Speicherfehler ·
`A022` Karte nicht formatiert · `A200` Bulb belegt · `A201` Leise-Auslöser
belegt · `A206` kein JPEG vorhanden · `A208` Spiegelvorauslösung läuft ·
`A20C`/`A20D` Vorschau wird erzeugt.

---

## 4. WLAN

**Der Access Point lässt sich am Kameramenü nicht starten** [Herstellerdoku].
Das Netzwerkmenü hat nur Konfiguration: SSID (1–32 Zeichen), Verschlüsselung
(offen, WPA2-PSK-AES, WPA3-SAE, gemischt), Passwort (8–36 Zeichen), Kanal,
Subnetzmaske `255.255.255.0`, DHCP-Server-IP `192.168.0.10`.

Der Start kommt über BLE — `0x01` auf `0x2005`.

**Die Kamera-IP wird nicht geraten:** Sie ist der DHCP-Server ihres eigenen
Netzes, ihre Adresse steht im vergebenen Lease.

**Das Passwort wechselt** bei jedem Verbindungsaufbau. Es ist deshalb nicht
einmalig abschreibbar, sondern muss aus `0x2004` entschlüsselt oder nach dem
Verbindungsaufbau über PTP gelesen werden.

---

## 5. USB

USB-ID `04b0:0234`. PTP über USB funktioniert vollständig — `operations_supported`
oben wurde darüber gemessen.

**Live View über USB ist unmöglich**, und zwar prinzipiell: Die Kamera zieht
beim Anstecken das Objektiv ein und meldet über `D1A4` Bit 24, dass Live View
gesperrt ist. `ChangeCameraMode` lässt sich nicht dagegen setzen. Das erklärt
zwei Fremdberichte, die genau daran hängengeblieben sind. **[M]**

Damit bleibt WLAN der einzige Weg, der Bild und Steuerung gleichzeitig liefert:
HDMI schaltet den Funk ab, USB zieht das Objektiv ein.
