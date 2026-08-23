# Messprotokoll

Die einzige Quelle der Wahrheit über die echte Kamera. Alles hier steht, weil es
**gemessen** wurde, nicht weil es plausibel ist. Widerspricht ein Chatverlauf
diesem Dokument, gewinnt dieses Dokument.

> **Wer nachschlagen will, was die Kamera kann, ist in
> [referenz.md](referenz.md) besser aufgehoben.** Dieses Dokument ist
> chronologisch und beantwortet die andere Frage: *wann* wurde etwas
> festgestellt, *womit*, und was folgte daraus.

**Aufbau:** [Stand](#stand) · [Offene Fragen](#offene-fragen) ·
[Messungen](#messungen) (neueste zuerst) · [Fremdmessungen](#fremdmessungen) ·
[Widerlegtes](#widerlegtes)

Pflege: [playbook.md](playbook.md), Abschnitt 2, Schritt 3.

---

## Stand

Diesen Block liest eine neue Session zuerst. Er wird bei jeder Runde überschrieben.

| | |
|---|---|
| **Phase** | 1 abgeschlossen — **PTP ist bestätigt**, Live View existiert. Phase 2: das Bild holen |
| **Erreicht** | 38 Operationen und 20 Properties gemessen · Kopplung reproduzierbar in 40 s · zweiter Transport (USB) im Repo · Protokoll der Hersteller-App gelesen |
| **Offenes Gate** | Startet `0x01` auf `0x2005` als **gekoppelter** Client den Access Point? Der Befehl steht fest, die Wirkung ist ungemessen |
| **Fehlende Messung** | Ein Schreibversuch als gekoppelter Client, danach ein WLAN-Scan |
| **Nächster Schritt** | Funk-Reset → Kameramenü → `ble-probe.py pairing --device … --nonce … --establish 01` → `netsh wlan show networks` |
| **Danach** | `0x2004` als gekoppelter Client lesen — dann steht statt der Nullen das Chiffrat da, und die Entschlüsselung lässt sich gegen das angezeigte Passwort prüfen |
| **Unsere Kennung** | wechselt bei jedem Pairing; die vom letzten Lauf steht im Protokoll |
| **Stand vom** | 2026-08-23 |

**Erste echte Messung liegt vor** (22.08.2026, BLE-GATT-Baum, unten). Der
PTP/IP-Pfad ist davon unberührt: der gesamte Code in `ptp.py`, `ptpip.py`,
`nikon.py` ist weiterhin ausschließlich gegen den Simulator getestet.

---

## Offene Fragen

Abgehakt wird nur mit Messung. Beantwortetes bleibt stehen — die Antwort ist
oft mehr wert als die Frage.

### Offen

- [ ] **Startet `0x01` auf `0x2005` den Access Point?** Der Befehl ist aus dem
      Herstellercode belegt, die Wirkung ungemessen. Das aktuelle Gate.
- [ ] Antwortet die Kamera im WLAN-Modus auf TCP 15740? Der Port steht im
      Herstellercode, die Kamera hat ihn noch nie für uns geöffnet.
- [ ] Wird eine beliebige GUID akzeptiert? Die App benutzt für alle
      Installationen dieselbe, was dagegen spricht, dass die Kamera darüber
      unterscheidet.
- [ ] Verträgt die Kamera eine zweite Sitzung neben der Hersteller-App?
- [ ] Wie groß sind die Live-View-Bilder wirklich, und welche Bildrate hält
      die Kamera durch?
- [ ] Lässt sich der Zoom über `0x9016` tatsächlich fahren, und in welchen
      Schritten?
- [ ] Was tun `0x2082`–`0x2087`? Sechs Characteristics, die die Hersteller-App
      **nicht kennt** — nur an der Kamera selbst zu erschließen.
- [ ] Was sind die Properties `D303`, `D406`, `D407`? Ebenfalls in der App
      nicht auffindbar.
- [ ] Stimmt die CCCD-Ableitung (Value-Handle + 1)?
- [ ] Ist dieses Modell ML-L7-kompatibel? Die Feature-Bits sprechen dagegen
      (Kamerasteuerung über BLE ist abgeschaltet).

### Beantwortet

- [x] **Welche Operationen unterstützt die Kamera?** 38 Stück, am 23.08.2026
      über USB ausgelesen. Vollständig in [referenz.md](referenz.md).
- [x] **Gibt es Live View?** Ja — `9201`, `9202`, `9203` stehen in der Liste.
- [x] **Wie sieht ein Live-View-Bild aus?** 384 Byte Header, big-endian, mit
      Bildmaßen, AF-Feld und Lagesensor. Aus dem Herstellercode.
- [x] **Wie zoomt man?** Über `0x9016`, nicht über Property `5008` — die wird
      nur gelesen. Bereich laut Kamera 24–3000 mm.
- [x] **Warum verweigert Live View am USB-Kabel?** Property `D1A4` Bit 24:
      Objektiv eingefahren. Die Kamera zieht es beim Anstecken ein; das ist
      keine Fehlfunktion, sondern Absicht.
- [x] **Was startet den WLAN-Access-Point?** `0x01` auf `0x2005` — ein Bitfeld,
      kein Zustandswert. Am Kameramenü geht es nicht (Herstellerdoku).
- [x] **Welche IP hat die Kamera?** Sie ist DHCP-Server ihres eigenen Netzes;
      die Adresse steht im Lease. Voreinstellung `192.168.0.10`.
- [x] **Kann man über Bluetooth auslösen?** Nein. Feature-Bit 11 ist null, und
      die dafür nötigen Characteristics fehlen.
- [x] **Wie sind die WLAN-Zugangsdaten geschützt?** Blowfish-CBC. Der Schlüssel
      entsteht aus Werten, die alle über BLE sichtbar oder frei wählbar sind —
      der Nachbau ist möglich, aber noch nicht durchgeführt.

---

## Messungen

Neueste zuerst. Vorlage für jeden Eintrag:

```
### TT.MM.JJJJ — Kurztitel
Kommando:   das wörtliche Kommando
Aufbau:     Kameramodus, Netz, welches Interface
Ergebnis:   was tatsächlich herauskam
Folge:      welcher Code, welcher Test, welche Doku sich geändert hat
```

### 23.08.2026 — Deep Dive in die Hersteller-App: Opcodes, Events, Zoom, Verschlüsselung
Quelle:     Dieselbe dekompilierte App wie unten, acht Agenten auf getrennten
            Bereichen. **Rang: dekompilierter Herstellercode**, an unserer
            Hardware nicht verifiziert, sofern nicht anders vermerkt.

Ergebnis:   **Alle sechs unbekannten Opcodes unserer Messung sind benannt:**

            | Opcode | Name | Parameter |
            |---|---|---|
            | `0x9016` | **ZoomControl** | 2× uint32 `[wide, tele]`, nur einer belegt |
            | `0x941C` | **GetEvent, neue Variante** | keine; Antwort anders als `0x90C7` |
            | `0x941E` | PowerZoomByFocalLength | in der App nur als Fähigkeitsflag |
            | `0x9520` | Auto-Übertragung start/stop | 1× `0x11` / `0x22` |
            | `0x9521` | Liste markierter Objekte | 1× `0` |
            | `0x9522` | Teilobjekt in wählbarer Größe | `[handle, größe, 0]`, Größe 4 = 8 MP |

            **Drei Abweichungen unseres Codes, alle korrigiert:**
            1. **`0x90C7` hat diese Kamera nicht, `0x941C` schon.** Die App
               wählt genauso. Unser `get_events()` fragte nur nach `0x90C7` und
               hätte für immer eine leere Liste geliefert — der schlimmste
               Fehlertyp, weil er nicht auffällt. Die Antwortformate sind
               verschieden: `0x90C7` zählt in 16 Bit mit einem Parameter je
               Ereignis, `0x941C` in 32 Bit mit variabler Parameterzahl.
            2. **Events werden gepollt, nicht empfangen.** Der Paketparser der
               App behandelt Pakettyp 8 nirgends. Der Ereigniskanal trägt nur
               den Init-Handshake und den Keepalive.
            3. **Der Keepalive läuft aktiv über den Ereigniskanal**, alle
               **9 Sekunden**, Antwort binnen 10. Wir haben bisher nur auf
               fremde Pings geantwortet. Neu: `PtpIpConnection.ping()`.

            **`SessionAlreadyOpen` (`0x201E`) ist kein Fehler** — die App
            arbeitet mit der angefragten Kennung weiter. Auch korrigiert.

            **Verbindungsaufbau der App**, der Reihe nach: TCP zum Kommandokanal
            (Port 15740, `TCP_NODELAY`) → InitCommandRequest → **zweite TCP**
            zum Ereigniskanal → InitEventRequest mit der Verbindungsnummer →
            Keepalive starten → `GetDeviceInfo`. `OpenSession` gehört nicht dazu.
            Version `0x00010000`, GUID big-endian, Lesepuffer 102.400 Byte.
            Beim Trennen schickt sie **kein** `CloseSession`, sondern schließt
            die Sockets hart.

            **Zoom:** `0x5008` Focal Length wird von der App **nur gelesen** —
            unsere frühere Notiz „schreibbar" war eine Fehldeutung des
            Property-Flags. Gezoomt wird über `0x9016`, und das ist ausdrücklich
            der Weg der Kompaktkameras; die spiegellosen nutzen `0x9464`, das
            unsere Kamera nicht hat.

            **Vendor-Properties, jetzt benannt** (aus unserer Messung):
            `d05d` AF-Messfeld · `d0e1` Objektivtyp · `d0e3`/`d0e4` Brennweite
            min/max · `d100` **Verschlusszeit** (Zähler/Nenner, `ffff/ffff` =
            Bulb) · `d1a2` **Live-View-Status** · `d1a4` **Live-View-Sperrgrund**
            (−1 = frei; das ist die Quelle von „Lens is retracting") ·
            `d1f1` verbleibende Aufnahmen.
            **`d303`, `d406`, `d407` kennt die App nicht** — die verrät nur die
            Kamera selbst.

            **Aufnahmepfad**, vollständig mit unseren Opcodes fahrbar:
            `0x9207 (-1, 0)` auslösen — Parameter 1: `-1` normal, `-2` mit
            Autofokus; Parameter 2: `0` Karte, `1` **SDRAM**, `2` beides —
            dann `0x90C8` pollen, bis nicht mehr `DeviceBusy` (`0x2019`), dann
            Ereignis `0x4002` für den Handle, `0x1008` für die Größe, `0x101B`
            in **1-MiB-Blöcken** mit Fortsetzungs-Offset. **Die App benutzt
            `0x1009 GetObject` nie.**

            **Ereignisse**, die die App auswertet: `0x4002` ObjectAdded ·
            `0x4005` StoreRemoved · `0x4006` DevicePropChanged · `0x400A`
            StoreFull · `0x400D` CaptureComplete · `0xC105`/`0xC108`/`0xC10A`
            Video · `0xC700` LSS-Sammelcode · `0xC702`.

            **Vendor-Fehlercodes** sind vollständig bekannt, u.a. `0xA002`
            OutOfFocus · `0xA004` InvalidStatus · `0xA00B` **NotLiveView** ·
            `0xA200` BulbReleaseBusy · `0xA021` StoreError.

            **Auslösen über Bluetooth geht an dieser Kamera nicht.** Der
            Fernsteuerpfad der App liegt auf `0x2021`, das unsere Kamera nicht
            hat — und `0x2009` bestätigt es: die Feature-Bits `fd010000`
            dekodieren zu Bit 11 (CameraControl) = **0**. Was BLE kann:
            Aufwecken (Bits 1–2 = WAKE_SUPPORT), WLAN-Konfiguration,
            Bildtransfer-Anstoß, Zeit, Standort, Batterie.
            `0x2008` ist kein Auslöser, sondern ein Anforderungsfeld: drei
            Vier-Bit-Felder, unser Ruhewert `1100` heißt „schick mir Zeit und
            Standort". `00 01` setzt ConnectionRequest — zweiter Kandidat für
            den WLAN-Start, im Code aber nicht als solcher belegt.

            **Die Verschlüsselung der WLAN-Zugangsdaten ist Blowfish** —
            gesichert: die native Bibliothek trägt Quellpfade auf
            `blowfishLib/LsBlowfish.c`, im Nur-Lese-Segment stehen das
            unveränderte P-Array (`243f6a88 85a308d3 …`) und die S-Box, und
            eine Assertion prüft die 56-Byte-Schlüsselgrenze. Kein AES, kein
            OpenSSL, kein eingebetteter Schlüssel.

            **Aber der Schlüssel steht nicht auf der Leitung.** Die Kette ist
            `init(Zufallszahl)` → `Stage1st` → `Stage3rd` → **`generateKey(
            Stufe-4-Payload, Geräte-ID)`**, und `init` baut internen Zustand
            auf, der nie gesendet wird. Der gespeicherte Kontext hat exakt die
            Gestalt eines Blowfish-Schlüsselplans: `long[18]` P-Array,
            `long[1024]` vier S-Boxen, dazu drei 8-Byte-Blöcke.

            **Praktisch entscheidend:** Der Kontext ist **pro Kopplung stabil**
            — nur der Chiffretext wechselt. Wer ihn einmal hat, kann alle
            künftigen Passwörter dieser Kopplung lesen.
Folge:      `nikon.py`: `ZOOM_CONTROL`, `GET_EVENT_EX` und vier weitere Opcodes,
            `NikonProperty` neu, `get_events()` wählt das richtige Verfahren.
            `ptpip.py`: `ping()` neu, `open_session()` toleriert `0x201E`.
            Sechs neue Tests nageln das fest.

### 23.08.2026, 02:00 — Der WLAN-Auslöser, aus der Hersteller-App gelesen
Quelle:     SnapBridge 2.13.3, per `adb pull` vom eigenen Handy geholt (68 MB,
            signiert, kein Drittanbieter-Download), mit baksmali in 11.721
            Smali-Dateien zerlegt. Vier Agenten haben unabhängig voneinander
            gesucht; die Kernaussagen decken sich.
            **Rang: dekompilierter Herstellercode.** Kein Messwert an der
            Hardware — die Wirkung ist noch nicht bestätigt.
            Rechtsgrundlage: § 69e UrhG, Dekompilierung zur Herstellung von
            Interoperabilität. Gelesen zur Verifikation, nicht kopiert.

Ergebnis:   **`0x2005` ist ein Bitfeld, kein Zustandswert.** Ein Byte,
            little-endian:

            | Bit | Maske | Bedeutung | wer schreibt es |
            |---|---|---|---|
            | 0 | `0x01` | **WLAN aufbauen** | der WiFi-Pfad des Backends |
            | 1 | `0x02` | Bluetooth Classic aufbauen | der BT-Pfad |
            | 7 | `0x80` | Verbindung nicht mehr nötig | eigener Task, niedrigste Priorität |

            **Der AP-Start ist ein einziges Byte `0x01` auf `0x2005`.** Der
            Encoder setzt alle drei Bits, der Decoder liest nur Bit 0 und 1
            zurück — Bit 7 wird beim Lesen verworfen.

            **Der Ablauf davor**, aus dem WiFi-Anwendungsfall des Backends:
            1. `0x2004` **lesen**
            2. prüfen, ob ein WLAN-Block vorhanden ist; fehlt er, Abbruch
            3. SSID, Passwort, Verschlüsselungsmodus entnehmen
            4. **`0x01` auf `0x2005` schreiben** — der AP-Start
            5. erst danach android-seitig ins Netz einbuchen

            **`0x2004` wird nur gelesen, nie geschrieben.** Die App kann die
            Zugangsdaten der Kamera über BLE nicht setzen. Layout der 102 Byte:

            | Offset | Länge | Feld |
            |---|---|---|
            | 0 | 1 | Flags: Bit0 WLAN-Block, Bit1 BT-Block |
            | 1 | 32 | SSID, verschlüsselt |
            | 33 | 64 | Passwort, verschlüsselt |
            | 97 | 1 | Verschlüsselungsmodus |
            | 98 | 4 | `sppMaxDataLength`, nur im BT-Block |

            **Das deckt sich Byte für Byte mit unserer eigenen Messung**
            (`03` + 96 Nullbytes + `03ef010000`): Flags `0x03` = beide Blöcke
            vorhanden, Modus `0x03`, `sppMaxDataLength` = 495. Dass SSID und
            Passwort null waren, ist selbst ein Befund — wir haben als
            **ungekoppelter** Client gelesen.

            **Die Zugangsdaten sind auf dem BLE-Draht verschlüsselt**, über eine
            native Bibliothek mit eigenem Schlüsselaustausch beim Pairing. Der
            Algorithmus liegt nicht im Bytecode. **Wir brauchen ihn nicht:** die
            Zugangsdaten stehen im Kameramenü, und über PTP gibt es sie im
            Klartext (unten).

            **Pflicht-Abonnements vor dem Handshake:** nur `0x2000` (Indication)
            und `0x2008` (Notification, bis zu 50 Versuche mit 100 ms Abstand).
            Die weiteren, die die App behandelt — `0x200A`, `0x2081`, `0x2020`,
            `0x2021` — sind optional und **existieren an dieser Kamera nicht**.
            Unser Client abonniert damit bereits das Richtige.

            **Jeder Schreibzugriff ist synchron**: die App wartet auf die
            Bestätigung, bevor der nächste folgt, und pausiert vorher. Einen
            expliziten Write-Typ setzt sie nie — er folgt den Properties aus der
            Discovery. `0x2005` hat `0x0a`, also *write with response*.

            **Aus dem PTP-Teil derselben App:**
            - Port **15740** steht als `0x3d7c` fest im Verbindungsaufbau
            - Initiator-GUID **`00112233-4455-6677-8899-AABBCCDDEEFF`**,
              Gerätename `Android Device`, Timeout 300 s
            - **SSID und Passwort sind auch über PTP lesbar und setzbar**
              (`Get`/`SetWmaSettingAction`, WMA = Wireless Mobile Adapter) —
              der Weg an der BLE-Verschlüsselung vorbei
            - Die Kamera-IP wird **nicht geraten**: die App liest die
              DHCP-Server-Adresse des vergebenen Lease. Die Kamera ist der
              DHCP-Server ihres eigenen Netzes.

            **Sechs Characteristics unserer Kamera kennt die App nicht:**
            `0x2082`, `0x2083`, `0x2084`, `0x2086`, `0x2087` — Volltextsuche
            über alle 11.721 Dateien, null Treffer. Kein Mitschnitt wird sie je
            zeigen, weil die App sie nie anfasst.
Folge:      Der Widerlegt-Eintrag zu `0x2005` wird korrigiert (unten) — die
            Annahme war richtig, die Deutung des Rückgabewerts falsch.
            Nächster Schritt: `0x01` als **gekoppelter** Client schreiben.

### 23.08.2026, 00:05 — `operations_supported` gemessen: Live View ist da
Kommando:   `PtpUsbConnection.open(product=0x0234)` → `get_device_info()`
            (eigener Code, `src/skyshutter/ptpusb.py`, über USB-C)
Aufbau:     Kamera per USB am Laptop, über `usbipd-win` an WSL durchgereicht.
            Kein WLAN, kein Bluetooth beteiligt.
Ergebnis:   `Nikon Corporation P1100`, Firmware `COOLPIX P1100 V1.0`.
            **38 Operationen**, 20 Device-Properties, Capture-Format `3801`
            (EXIF/JPEG).

            | Opcode | Name |
            |---|---|
            | 1001–100b | DeviceInfo, Session, Storage, Objekte, Thumb, Delete |
            | 100c–100f | SendObjectInfo, SendObject, InitiateCapture, FormatStore |
            | 1014–1016 | GetDevicePropDesc / GetValue / **SetValue** |
            | 101b | GetPartialObject |
            | 9016 | unbekannt |
            | 90c1 | AfDrive |
            | 90c2 | SetControlMode |
            | 90c4 | GetLargeThumb |
            | 90c8 | DeviceReady |
            | **9201** | **StartLiveView** |
            | **9202** | **EndLiveView** |
            | **9203** | **GetLiveViewImg** |
            | 9205 | ChangeAfArea |
            | 9207 | InitiateCaptureRecInMedia |
            | 941c, 941e, 9520, 9521, 9522 | unbekannt, Nikon-Vendor |
            | 9801–9805 | MTP-Objekt-Properties (Microsoft) |

            Properties: `5001 5007 5008 500a 500e 500f 5010 5011 5013` und die
            Vendor-Reihe `d05d d0e1 d0e3 d0e4 d100 d1a2 d1a4 d1f1 d303 d406 d407`.

            **Live View ist vorhanden** — alle drei Opcodes stehen in der Liste.
            Damit ist die Frage, die das Projekt seit Beginn trägt, beantwortet.

            **Und trotzdem läuft es über USB nicht.** Die Kamera antwortet auf
            `9201` mit `Liveview cannot start: Lens is retracting`, und
            `liveviewprohibit` nennt **genau diese eine** Bedingung. Grund,
            von Thomas am Gerät beobachtet: **Die Kamera zieht das Objektiv ein,
            sobald USB angeschlossen wird.** Das ist keine fehlende
            Implementierung, sondern ein Zustand — und er erklärt rückwirkend
            beide Fremdberichte (Issue #1201 hier, Issue #780 zum P950), die
            das offengelassen hatten.

            `SetControlMode` (`90c2`) steht zwar in der Liste, aber der Wert `1`
            (PC-Steuerung) wird abgelehnt: `Failed to set new configuration
            value 1`. Das Objektiv lässt sich über PTP nicht ausfahren.

            **Über USB messbar, ohne Live View:** Brennweite (`5008`) ist
            **schreibbar**, und die Kamera meldet `minfocallength 24 mm`,
            `maxfocallength 3000 mm` — der volle 125×-Bereich. ISO (`500f`)
            und Belichtungskorrektur (`5010`) ebenfalls schreibbar.
Folge:      Neu `src/skyshutter/ptpusb.py` — zweiter Transport, gleiche
            `transaction()`-Schnittstelle wie PTP/IP, damit `nikon.py`,
            `mjpeg.py` und die CLI unverändert darauf laufen.
            Liste übernommen in [protokoll.md](protokoll.md).

            **Konsequenz für den Plan:** Der WLAN-Weg ist damit nicht mehr eine
            von mehreren Optionen, sondern der **einzige**, der Bild und
            Steuerung gleichzeitig liefern kann. HDMI schließt Funk aus, USB
            zieht das Objektiv ein. Nur über WLAN bleibt die Kamera im
            Aufnahmezustand — und dort greift die einzige bekannte Sperre nicht.

### 22.08.2026, 23:28 — Eine gekoppelte Kamera duldet keinen fremden Client
Kommando:   `tools/ble-proxy.py --keepalive 2` (ohne Identität)
Aufbau:     Wie unten, aber die Kamera ist inzwischen mit dem Handy gekoppelt.
Ergebnis:   ```
            23:28:15  camera connected, mtu=515
            23:28:42  ! the camera dropped the link
            ```
            **27 Sekunden, obwohl der Keepalive fehlerfrei lief** — keine
            einzige `keepalive read failed`-Meldung. Vor der Kopplung hielt
            dieselbe Verbindung über vier Minuten. Eine gekoppelte Kamera wirft
            einen nicht authentifizierten Client also raus, auch wenn er redet.

            Damit steht der Proxy in einer Zwickmühle:

            | Betrieb | Folge |
            |---|---|
            | ohne eigenen Handshake | die gekoppelte Kamera trennt nach ~30 s |
            | mit eigenem Handshake | die App wird mit `0x80` abgewiesen |

            **Der Ausweg ist ein Hybrid:** bei der Kamera authentifizieren, den
            Handshake der App aber selbst beantworten — mit der **echten
            Stufe 4 der Kamera**, die wir dabei mitschneiden. Alles andere geht
            weiter durch. In `ble-proxy.py` gebaut, **noch nicht an Hardware
            getestet**.

            **Nebenbefund, widerspricht Falle 2 aus [pairing.md](pairing.md):**
            Ein Scan um 23:35 zeigte die Kamera mit ihrem **vollen** Namen
            `P1100_SSSSSSSS` im Advertising, nicht mit dem abgeschnittenen
            `P110`. Wann sie welchen sendet, ist offen.
Folge:      `--device`/`--nonce` sind jetzt der empfohlene Betrieb, nicht der
            gemiedene. Der Keepalive protokolliert Fehler, statt sie zu
            schlucken — sein Schweigen hat einen Abend gekostet.

### 22.08.2026, 23:12 — Die App spricht durch den Proxy mit der echten Kamera
Kommando:   `tools/ble-proxy.py --keepalive 2` (ohne `--device`/`--nonce`)
Aufbau:     Proxy an der Kamera, App auf dem Handy verbindet sich mit dem Proxy.
Ergebnis:   **Der vollständige Handshake lief zwischen App und echter Kamera
            durch uns hindurch:**
            ```
            23:12:58  WRITE  0x2000  <- 01…  (App, Stufe 1)
            23:12:58  NOTIFY 0x2000  -> 02…  (Kamera, Stufe 2)
            23:12:58  WRITE  0x2000  <- 03…  (App, Stufe 3)
            23:12:58  NOTIFY 0x2000  -> 04…30325160  (Kamera, Stufe 4)
            23:12:58  WRITE  0x2002  <- Android_CPH2581_4311
            23:12:59  READ   0x2003  -> P1100_SSSSSSSS   <- echter Name
            23:12:59  WRITE  0x2006  <- Uhr
            23:12:59  READ   0x2009  -> fd010000
            ```
            Die App hat sich damit bei der **echten** Kamera registriert — was
            der Doppelgänger nie erreicht hat, weil er den Namen nicht führen
            konnte.

            **Ein Keepalive-Handshake des Proxys blockiert die App.** Läuft der
            Proxy mit `--device`/`--nonce`, weist die Kamera den Handshake der
            App mit `GATT Protocol Error: Application-specific Error 0x80` ab:
            pro Verbindung nimmt sie nur einen. Lesezugriffe allein halten die
            Verbindung genauso gut — **eine Authentifizierung ist dafür nicht
            nötig**, über vier Minuten ohne Abbruch gemessen. Also ohne
            `--device` fahren.

            **Bekannte Grenze, noch nicht behoben:** Die App macht nach dem
            ersten Handshake sofort einen zweiten. Trennt sie zwischendurch ihre
            Seite, bleibt unsere Kamera-Verbindung bestehen und trägt den alten
            Zustand — der zweite Handshake scheitert dann ebenfalls mit `0x80`.
            Richtig wäre, die Kamera-Verbindung zu erneuern, sobald die App ihre
            trennt. Ungetestet, deshalb nicht eingebaut.

            **Zum Koppeln taugt der Proxy nicht.** Beim Pairing sucht die App
            nach dem Advertising-Namen; die Kamera sendet `P110`, wir senden den
            Windows-Gerätenamen, und `GattServiceProvider` bietet kein Feld, das
            zu ändern. Die App bricht mit „Kamera nicht gefunden" ab. Beim
            *Reconnect* sucht sie über die Service-UUID und findet uns sofort.
            Wer das Koppeln über den Proxy braucht, muss den Computernamen auf
            den Kameranamen setzen (Adminrechte, Neustart).

            **Kein Bonding ohne Erstregistrierung.** Die App meldete sich in
            jedem Lauf mit derselben gespeicherten Kennung, also als Reconnect —
            und die Kamera öffnete ihre klassische Seite nicht, es kam kein
            Zahlencode. Das bestätigt Falle 3 aus [pairing.md](pairing.md) von
            der anderen Seite.
Folge:      `tools/ble-proxy.py` läuft ohne `--device`/`--nonce`.

### 22.08.2026, 22:41 — BLE-Proxy zwischen App und Kamera; die Kamera wirft stille Clients raus
Kommando:   `tools/ble-proxy.py --device DDDDDDDD --nonce NNNNNNNN --keepalive 3`
Aufbau:     Kamera im Menü *Mit Smartgerät verbinden*. Der Laptop hält
            gleichzeitig eine BLE-Client-Verbindung zur Kamera (bleak) und einen
            BLE-GATT-Server für die App (WinRT). **Beide Rollen auf demselben
            Adapter funktionieren.**
Ergebnis:   ```
            22:41:23  camera connected, mtu=515 -- it has stopped advertising
            22:41:23  authenticated with the camera (salt #0)
            22:41:23  mirroring 18 characteristics
            22:41:23  advertising as the camera
            ```
            **Die Kamera trennt einen Client, der nichts sagt — nach 8 bis 9
            Sekunden, auch einen authentifizierten.** Zweimal gemessen
            (22:31:02 → 22:31:10, 22:37:10 → 22:37:19). Ein Lesezugriff alle
            drei Sekunden (`0x2006`) hält die Verbindung; danach lief sie über
            acht Minuten ohne Abbruch. Das erklärt rückwirkend mehrere
            Fehlschläge, bei denen zwischen zwei Schritten zu viel Zeit verging.

            **Sobald wir verbunden sind, advertisiert die Kamera nicht mehr.**
            Das ist der Hebel des Proxys: Die App kann sie dann nicht mehr
            finden und sieht nur uns.

            Der Funk-Reset ist auch hier Vorbedingung: 28 Verbindungsversuche in
            Folge kamen mit `mtu=23` hoch (unbrauchbar), nach `Off`/`On` sofort
            `mtu=515` beim ersten Versuch.
Folge:      Neu `tools/ble-proxy.py`. `--keepalive` ist der Messwert als Code.

### 22.08.2026, 22:15 — Was die Hersteller-App über BLE tut, gegen unseren Doppelgänger
Kommando:   `tools/ble-camera-sim.py --host-name|--serial … --auth-serial …`
Aufbau:     Laptop als GATT-Server mit den 18 gemessenen Characteristics, die
            echte Kamera ausgeschaltet. Die App auf dem Handy verbindet sich
            damit. Drei Läufe mit unterschiedlichen Werten in `0x2003`.
Ergebnis:   **Die App beantwortet unsere gerechnete Challenge korrekt** — der
            Handshake ist damit in beide Richtungen verifiziert. Ihr Ablauf:

            | Schritt | was |
            |---|---|
            | abonniert | nur `0x2000` und `0x2008` — die vier indicate-Kanäle nicht |
            | schreibt `0x2000` | Stufen 1 und 3 |
            | schreibt `0x2002` | ihren Namen, 32 B ASCII |
            | liest | `0x2003`, `0x2009` |
            | schreibt `0x2006` | die Uhr, 10 B — **nur bei akzeptierter Kamera** |

            **Sie führt eine gespeicherte Kennung mit:** `device` und `nonce`
            waren über alle Läufe hinweg identisch, nur der Zeitstempel wechselte.
            Ein Löschen der Kamera *in der App* setzte das nicht zurück.

            **Sie prüft den Gerätenamen.** Mit dem Kameranamen in `0x2003` kam
            sie bis zum Uhrstellen; mit dem Rechnernamen brach sie nach dem
            Lesen von `0x2003`/`0x2009` ab und begann von vorn — im Sekundentakt.

            **Die interne Seriennummer ist nicht die abgedruckte.** Stufe 4 der
            echten Kamera endet auf `…30325160`: sechs ASCII-Zeichen, dann zwei
            Bytes, die keine sind. Der Doppelgänger braucht diesen Wert
            wörtlich (`--auth-serial`), geraten aus der aufgedruckten Nummer
            reicht nicht.
Folge:      Grenze des Doppelgängers benannt: Windows nimmt seinen klassischen
            Bluetooth-Namen zwingend vom Computernamen, also können BLE-Name und
            klassischer Name nicht beide stimmen. Deshalb der Proxy.

### 22.08.2026 — Der WLAN-Access-Point lässt sich am Kameramenü nicht starten
Quelle:     Herstellerdokumentation, Referenzhandbuch dieses Modells,
            Netzwerkmenü und Abschnitt Drahtlosverbindungen. **Rang: Primär.**
Ergebnis:   Das Netzwerkmenü hat acht Einträge: Flugzeugmodus, Verbindung
            auswählen, Mit Smartgerät verbinden, Verbindung zur Fernbedienung,
            Während der Aufnahme senden, Wi-Fi, Bluetooth, Standardeinstellungen
            wiederherstellen. Unter **Wi-Fi** stehen genau zwei Punkte:
            *Netzwerkeinstellungen* (SSID 1–32 Zeichen, Auth: Open /
            WPA2-PSK-AES / WPA3-SAE / gemischt, Passwort 8–36, Kanal,
            Subnetzmaske `255.255.255.0`, DHCP-Server-IP `192.168.0.10`) und
            *Aktuelle Einstellungen* — beides Anzeige und Konfiguration.

            **Ein Punkt, der eine WLAN-Verbindung herstellt, existiert nicht.**
            Der Hersteller schreibt, der Wechsel geschehe durch Auswahl der
            Download- oder Fernaufnahme-Funktion *in der App*. Neuere Modelle
            anderer Baureihen haben den Menüpunkt *Wi-Fi-Verbindung (AP mode)*;
            dieses Modell hat ihn nicht.

            Gegenprobe am 22.08. um 22:0x: `netsh wlan show networks` findet nur
            das Heimnetz. Der AP läuft nicht von selbst.
Folge:      Der WLAN-Start muss über BLE kommen. `0x2005` ist widerlegt (unten),
            die übrigen Kandidaten sind `0x2004`, `0x2007`, `0x2082`, `0x2083`,
            `0x2087`. Kein öffentliches Projekt dokumentiert das Kommando —
            weder furble, noch der ESP32-Aufsatz, noch das dslrdashboard-Forum.

### 22.08.2026, 21:56 — Kopplung in 40 Sekunden, erster Versuch, nach langer Funkpause
Kommando:   In Etappen von Hand, sonst identisch mit `tools/pair.sh`:
            Funk `Off`/`On`, 12 s, `ble-probe.py pairing --quick --register skyshutter`,
            direkt danach `classic-pair.py --seconds 45 pair`.
Aufbau:     Kamera frisch im Menü *Mit Smartgerät verbinden*, auf beiden Seiten
            ungekoppelt. Letzter Funkverkehr sechs Stunden zuvor.
Ergebnis:   Der bisher schnellste und einzige völlig glatte Durchlauf:
            ```
            21:56:25  Funk-Reset fertig
            21:56:50  connected  mtu=515
            21:56:51  salt #0 -> authenticated, registriert als 'skyshutter'
                      Kennung: device=DDDDDDDD nonce=NNNNNNNN
            21:56:59  inquiry: 'P1100_SSSSSSSS' unpaired class=0x080620
            21:57:01  *** code 034488 ***
            21:57:05  result: PAIRED  (custom 1/3)
            ```
            **40 Sekunden vom Reset bis zum Bond.** Der Abstand zwischen dem
            Ende des Handshakes und dem Fund im Inquiry betrug **9 Sekunden**,
            nicht die zuvor als ausreichend dokumentierten 35.

            Kontrolle danach: `classic-pair.py list` (ungepaarter Selektor)
            findet die Kamera **nicht** mehr — sie ist auf die gepaarte Seite
            gewechselt. Thomas meldet den Vorgang an der Kamera als erfolgreich.

            **Was diesen Lauf von der Fehlschlagserie 14:12–15:39 unterscheidet,
            ist nicht der Ablauf.** Die Schritte, die Zeiten und der Code waren
            dieselben; in jener Serie scheiterte das Bonding neunmal mit
            `AUTHENTICATION_TIMEOUT`, und auch Windows' eigene Routine gab
            `FAILED` zurück. Der einzige messbare Unterschied ist die
            **sechsstündige Ruhephase** davor. Das stützt die Erschöpfungs-These
            aus [pairing.md](pairing.md), Fallen 5a/5b — beweist sie aber nicht,
            weil in der Pause weder Kamera noch Windows kontrolliert wurden.
            **Vermutung, nicht Messung.**

            **Der abschließende Reconnect-Handshake ist kein Pflichtschritt.**
            Er lief 20 s nach dem Bond los und scheiterte:
            ```
            connect 1/15 to 66:09:D2:33:57:34: TimeoutError
            connect 2/15: unusable (mtu=23)
            ...
            camera not advertising - open the smart-device menu on the camera
            ```
            Die Kamera advertisierte nicht mehr — **weil die Verbindung bereits
            stand**. Der Vorgang war an der Kamera trotzdem erfolgreich. Schritt 3
            ist damit eine Reparatur für den Fall, dass die Kamera nach dem Bond
            auf „Establishing connection" hängenbleibt, nicht Teil des Normalwegs.
Folge:      `docs/pairing.md`: Zeitfenster korrigiert, Schritt 3 als bedingt
            gekennzeichnet, Ruhephase als Bedingung aufgenommen.
            `tools/pair.sh`: Schritt 3 nur noch bei Bedarf.

### 22.08.2026 — Kopplung reproduzierbar; der Bluetooth-Stack braucht davor einen Reset
Kommando:   Der vollständige Ablauf steht in [pairing.md](pairing.md).
Ergebnis:   Zweiter erfolgreicher Bond, diesmal **beim ersten Versuch**, nachdem
            der Funk vorher aus- und eingeschaltet wurde:
            ```
            0. Bluetooth Off -> On, 15 s warten
            1. BLE-Handshake, salt #5, registriert als 'skyshutter'
            2. inquiry: 'P1100_SSSSSSSS' unpaired  <-- gefunden
               *** code 018564 -- OK an der Kamera ***
               result: PAIRED
            ```
            **Der Reset ist keine Vorsichtsmaßnahme, er ist notwendig.** Ohne
            ihn scheiterten fünf Anläufe nacheinander: Der klassische Inquiry
            meldete **null Geräte** — nicht einmal einen Fernseher, der
            durchgehend in Reichweite war und Minuten zuvor noch gefunden
            wurde. Nach `Off`/`On` und ~15 s Wartezeit fand derselbe Code
            sofort wieder alles. Der Windows-Stack verschluckt sich nach
            mehreren Verbindungs- und Watcher-Zyklen.

            **Irrweg, damit ihn niemand wiederholt:** Der Verdacht, ein
            einzelner `DeviceWatcher` mache nur eine Suchrunde und müsse
            wiederholt neu gestartet werden, war falsch. Das Umbauen auf
            Runden machte es schlimmer — dann fand er gar nichts mehr, weil
            Windows `EnumerationCompleted` schon nach einer Sekunde meldet,
            lange bevor der Funk tatsächlich gesucht hat. Ein Watcher, der
            das ganze Fenster durchläuft, ist richtig.

            **Nach dem Bond bleibt die Kamera bei „Establishing connection"
            stehen**, auch wenn ein RFCOMM-Dienst (Serial Port,
            `00001101-…`) angeboten wird und das Bonding erfolgreich war.
            Sie baut keine Verbindung zu diesem Dienst auf. Was sie
            stattdessen erwartet, ist offen.
Folge:      `docs/pairing.md` neu — der Ablauf als Kommandoblock.
            `tools/classic-pair.py` behält den einfachen Watcher.

### 22.08.2026 — Vollständige Kopplung: skyshutter steht in der Geräteliste der Kamera
Kommando:   `tools/ble-probe.py pairing --register skyshutter` (ohne `--device`/`--nonce`!),
            direkt danach `tools/classic-pair.py pair`
Aufbau:     Kamera im Menü *Mit Smartgerät verbinden*. Laptop, Windows-Bluetooth.
            Kein Handy beteiligt.
Ergebnis:   ```
            BLE-Handshake: salt #3, stage 4 -> authenticated
            registriert als 'skyshutter'
            Kennung vergeben: device=01dcca74 nonce=877b17f2
            CLASSIC: 'P1100_SSSSSSSS'  unpaired  <-- gefunden
            pairing with 'P1100_SSSSSSSS'
            *** code 629949 -- OK an der Kamera gedrückt ***
            result: PAIRED
            ```
            **An der Kamera steht `skyshutter` jetzt unter den gekoppelten
            Geräten.** Windows führt umgekehrt `P1100_SSSSSSSS` mit Status OK.

            Die Kopplung besteht aus zwei Teilen, die beide nötig sind:
            1. **BLE-Pairing-Handshake** — vier Stufen auf `0x2000`, danach
               Clientname (32 B ASCII) auf `0x2002`.
            2. **Klassisches Bluetooth-Bonding** — Inquiry, Gerät über den
               Namen finden, `BTA_DmBond`, Zahlencode an der Kamera mit OK
               bestätigen. Zeitfenster rund 30 Sekunden.
Folge:      Neu `tools/classic-pair.py` (`list`, `pair`, `forget`) und
            `tools/rfcomm-listen.py`.

            **Zwei Fallen, beide gemessen:**

            *Der Handshake muss als **unbekannter** Client laufen.* Mit
            `--device`/`--nonce` ist es ein Reconnect, und nach einem Reconnect
            macht sich die Kamera **nicht** für klassisches Bluetooth sichtbar.
            Genau daran scheiterten die ersten Versuche: BLE lief durch, der
            anschließende Inquiry fand nichts.

            *Der Inquiry braucht einen `DeviceWatcher` auf dem Selektor für
            **ungepaarte** Geräte.* `DeviceInformation.find_all_async` liefert
            nur den Windows-Cache, und der ist für ungepaarte Geräte leer — die
            Suche meldet null Geräte, obwohl die Kamera sendet.

            Nach dem Bonding wartet die Kamera darauf, dass der Client eine
            serielle Verbindung anbietet; sie zeigt dabei „establishing
            connection". Ohne einen solchen Dienst endet das in „could not
            connect". Nach einem **Reconnect**-Handshake mit der beim Pairing
            vergebenen Kennung kehrt sie ins normale Menü zurück.

### 22.08.2026 — Authentifizierung: Stufe 2 gemessen, Handshake offline reproduziert
Kommando:   `python tools/ble-probe.py --retries 12 --timeout 15 handshake`
Aufbau:     Kamera im Menü *Mit Smartgerät verbinden*. Laptop, ungekoppelt.
            Erster schreibender Zugriff auf die Kamera in diesem Projekt,
            freigegeben von Thomas.
Ergebnis:   ```
            0x2000 before   04 0000000000000000 3230303130325160
            stage 1 write   01 a4f393a6e83b5231 010ec1e5 791879b3
            stage 2 read    02 0000039300003282 83fc0efc c9b2caab
            ```
            Der Vorzustand war **Stufe 4** und trug ASCII `200102…` — die
            Kamera hielt noch die Authentifizierung der App. Auf unsere Stufe 1
            antwortete sie mit einer Challenge in Stufe 2.

            **Offline nachgerechnet und getroffen:** Salt **#6**
            (`0xcd32687f`, `0xa9e28a30`) reproduziert `83fc0efc c9b2caab`
            exakt aus den beiden Zeitstempeln. Ein Zufallstreffer über 64 Bit
            ist auszuschließen. Damit ist das Verfahren an dieser Kamera belegt,
            nicht nur der fremden Quelle nacherzählt.

            Daraus folgt Stufe 3: `03 a4f393a6e83b5231 859463d4 73422394`.
Folge:      Neu `tools/nikon_pairing.py`. Der Hash ist Blowfish/ECB mit festem
            Schlüssel `ffffaa5511223300`, verkettet: Startzustand
            `0x01020304`/`0x05060708`, je zwei Eingabewörter werden mit dem
            Zustand XOR-verknüpft, verschlüsselt, das Chiffrat wird der neue
            Zustand. **Innen big-endian, auf dem Draht little-endian.**

            **Die Wortreihenfolge ist die Falle:** Bei der Salt-Suche steht der
            Zeitstempel der Kamera zuerst, in der Antwort der eigene. Vertauscht
            passt kein einziger Salt, und nichts sagt einem warum — genau
            dieser Fehler kostete hier den ersten Anlauf.

### 22.08.2026 — Wann die Kamera überhaupt erreichbar ist
Kommando:   `python tools/ble-probe.py scan --seconds 10`, `pair`, `unpair`, `session`
Ergebnis:   **1. Der Beacon hängt am Menü.** Die Kamera advertised nur, solange
            *Mit Smartgerät verbinden* auf ihrem eigenen Display offen steht.
            Menü verlassen → binnen Sekunden still. Alle vorherigen „silent"-
            Läufe und Verbindungs-Timeouts hatten diese eine Ursache. Zuvor als
            Energiesparen gedeutet — falsch.

            **2. Der advertisierte Name ist gekürzt.** Im Advertising steht
            `'P110'`, nicht `P1100_SSSSSSSS`. Der 128-Bit-Service-UUID belegt 16
            der 31 Byte Nutzlast, für den vollen Namen bleibt kein Platz, also
            schickt die Kamera einen *Shortened Local Name*. **Folge: nie über
            den Namen suchen.** Die Service-UUID `0000de00-…` ist der
            zuverlässige Marker; die Adresse taugt nicht, sie rotiert.

            **3. Kopplung gelingt einseitig und schadet nicht.** `pair` legte
            in Windows einen Bond an (`Get-PnpDevice` zeigt `P1100_SSSSSSSS`,
            Status OK), ohne dass an der Kamera eine Taste gedrückt wurde.
            bleak 3.0.2 gibt dabei `None` statt `True` zurück — das ist kein
            Fehlschlag. `unpair` entfernt den Bond wieder.

            **4. Verbindungen scheitern reproduzierbar, unabhängig vom Bond.**
            Nach dem ersten erfolgreichen Dump lief jeder weitere
            Verbindungsversuch in `TimeoutError`, obwohl der Scan das Gerät
            sofort fand — gekoppelt wie entkoppelt. Der erste, erfolgreiche
            Versuch fand statt, als am Handy nicht gearbeitet wurde.
Folge:      `tools/ble-probe.py` sucht jetzt über die Service-UUID statt über
            den Namen und kennt `pair`/`unpair`.
            **Offene Vermutung, ungeprüft:** Die Kamera erlaubt nur eine
            BLE-Verbindung gleichzeitig, und die App hält sie. Prüfbar, indem
            Bluetooth am Handy ausgeschaltet und danach verbunden wird.

### 22.08.2026 — Alle lesbaren BLE-Characteristics ausgelesen
Kommando:   `python tools/ble-probe.py session --seconds 0`
Aufbau:     Wie unten. Ohne Pairing, ohne Handy. Kein einziger Lesezugriff wurde
            mit `Insufficient Authentication` abgelehnt — die Kamera gibt alles
            an einen fremden Client heraus.
Ergebnis:   Rohwerte, Seriennummer geschwärzt (`SSSSSSSS`, achtstellig):

            | UUID | Bytes | Wert |
            |---|---|---|
            | 0x2000 | 17 | `00…00` (alles null) |
            | 0x2001 | 1 | `03` |
            | 0x2003 | 32 | `P1100_SSSSSSSS` + Nullen |
            | 0x2004 | 102 | `03` + Nullen, endet auf `03ef010000` |
            | 0x2005 | 1 | `03` |
            | 0x2006 | 10 | `ea070816090332040100` |
            | 0x2008 | 2 | `1100` |
            | 0x2009 | 4 | `fd010000` (LE 509) |
            | 0x2a19 | 1 | `64` (100) |
            | 0x200b | 33 | `SSSSSSSS` + Nullen |
            | 0x2080 | 4 | `03000000` |
            | 0x2082 | 32 | `0202 0303 0f0f 1111 1212 1313 1414 2828 2929 2020 2121` + Nullen |
            | 0x2084 | 6 | `000000000000` |
            | 0x2086 | 4 | `03000000` |
            | 0x2087 | 17 | `00…00` (alles null) |

            Standard-Services nebenbei: `0x2a00` = derselbe Gerätename,
            `0x2a04` = `ffffffff0000ffff` (keine bevorzugten Verbindungsparameter),
            `0x2aa6` = `01`, `0x2b2a` (Database Hash) = `000000000000180ac1cca828c1d597b0`.
Folge:      **Belegt:** `0x2006` ist die Uhr. `ea07`=2026, `08`, `16`=22, `09`,
            `03`, `32`=50 — also 2026-08-22 09:03:50, und das stimmte auf die
            Minute mit der Laborzeit überein. Die letzten drei Bytes `040100`
            sind unklar (Wochentag passt nicht: der 22.08.2026 ist ein Samstag).
            `0x2003` und `0x200b` tragen Gerätename und Seriennummer.

            **Deutung, nicht belegt:** `0x2a19` = `0x64` = 100 sieht nach
            Ladezustand in Prozent aus — es steht auf der Vendor-Base, aber die
            Zahl passt zum SIG-Muster. `0x2082` besteht aus elf Paaren
            identischer Bytes (2,3,15,17,18,19,20,40,41,32,33) und riecht nach
            einer Fähigkeiten- oder Kommandoliste. `0x2000` und `0x2087` sind
            beide 17 Byte lang, beide read+write+indicate und beide leer — das
            Muster eines Kommando- und eines Antwortkanals.

            Nicht lesbar und damit weiter unbekannt: `0x2002`, `0x2007`,
            `0x2083`. Eine davon startet vermutlich das WLAN.

### 22.08.2026 — GATT-Baum an der Kamera bestätigt, WLAN-Parameter, kein AP im Menümodus
Kommando:   `python tools/ble-probe.py scan`, dann `dump` (Windows-Python, bleak)
            `netsh wlan show networks mode=bssid` / `netsh wlan connect`
Aufbau:     Kamera eingeschaltet, Menü *Mit Smartgerät verbinden*. Bluetooth des
            Laptops (Qualcomm FastConnect 7800), Handy nicht beteiligt.
Ergebnis:   **1. Die Kamera advertised den Vendor-Service direkt.**
            `name='P1100_xxxxxxxx'`, `services: ['0000de00-3dd4-4255-8d62-6dc7b9bd5561']`,
            RSSI −65. Die BLE-Adresse ist eine Resolvable Private Address und
            weicht von der im Stack-Log ab — sie rotiert, taugt nicht als Kennung.

            **2. Verbindung ohne Pairing gelingt.** `connected: True, mtu=515`.
            Ein Pairing mit dem Laptop war nicht nötig, obwohl die Kamera mit
            dem Handy gekoppelt ist.

            **3. Der GATT-Baum stimmt in jedem Feld mit dem Stack-Log überein** —
            Service 0xde00 bei 0x0029, 18 Characteristics, alle Handles, alle
            Property-Bits. Die zuvor nur abgeleiteten CCCDs sind bestätigt:
            0x002c, 0x003d, 0x004c, 0x0051, je einen über dem Value-Handle.
            Zusätzlich sichtbar: 0x1800 GAP (0x0001), 0x1801 GATT (0x0010),
            **0x180a Device Information (0x006f)** mit 0x2a24/0x2a26/0x2a28/0x2a29
            — Modell, Firmware, Software, Hersteller, alle lesbar.

            **4. WLAN-Parameter (vom Kameradisplay abgelesen):** WPA2-PSK, Kanal 6,
            DHCP-Adresse der Kamera `192.168.0.10`, SSID = der BLE-Gerätename.
            Damit ist der zweite der beiden IP-Kandidaten bestätigt und der
            erste (`192.168.1.1`) für dieses Modell hinfällig.

            **5. Der AP läuft im Modus *Mit Smartgerät verbinden* nicht.**
            Fünf Scans über mehrere Minuten zeigten nur Fremdnetze. Ein
            Verbindungsversuch mit hinterlegtem Profil und `nonBroadcast=true`
            (aktives Probing, findet auch versteckte SSIDs) blieb erfolglos:
            Windows meldet Erfolg, bleibt aber im Heimnetz. Das Wi-Fi-Menü der
            Kamera bietet keinen Eintrag, der die Verbindung startet — nur die
            Anzeige der Parameter.

            **6. Nach dem Trennen stellt die Kamera das Advertising ein.**
            Drei Verbindungsversuche über eine Minute: `not advertising`.
            Vermutlich Energiesparen; nicht abschließend geklärt.
Folge:      `src/skyshutter/ble.py` und `tests/test_ble.py` unverändert gültig,
            Kommentare von „abgeleitet" auf „bestätigt" korrigiert.
            Neu `tools/ble-probe.py` — Messwerkzeug außerhalb des Pakets
            (braucht `bleak`, läuft unter Windows-Python, weil WSL keinen
            Bluetooth-Adapter hat). Unterkommandos `scan`, `dump`, `read`,
            `watch`, `write`; `write` verweigert ohne `--i-know`.
            WPA3-SAE-Frage erledigt: die Kamera bietet WPA2-PSK an, der
            Laptop-Adapter beherrscht ohnehin WPA3-Personal (H2E).
            Nächster Schritt: `read` auf die zehn lesbaren Characteristics und
            `watch` auf die vier notify/indicate-fähigen, während die App das
            WLAN startet — dort muss das Kommando sichtbar werden.

### 22.08.2026 — BLE-GATT-Baum der P1100 aus dem Bluetooth-Stack-Log
Kommando:   `adb -P 5038 bugreport C:\Users\thoma\Downloads\skyshutter-bt.zip`,
            danach Auswertung von `FS/data/misc/bluetooth/logs/bluetooth_20260822_071644_18937.log`
Aufbau:     Kamera BLE-gepaart mit der Hersteller-App auf dem Android-Phone
            (OnePlus, OxygenOS). Kein WLAN, kein PTP/IP. Kamera nicht im
            Fernsteuerungsmodus. Session 07:17–07:18.
Ergebnis:   Identität belegt:
            `btm_ble_sec.cc: BTM_GetRemoteDeviceName: bd_addr:xx:xx:xx:xx:xx:xx name:P1100_xxxxxxxx`
            (137×; der Gerätename trägt eine achtstellige Kennung, geschwärzt.
            Dieselbe Adresse ist mit 1234 Zeilen die dominante im Log und trägt
            die unten genannte Service-Discovery).

            Ein einziger Vendor-Service trägt die gesamte Fernsteuerung:
            `0000de00-3dd4-4255-8d62-6dc7b9bd5561`, Handles 0x0029–0x0051.
            Alle 18 Characteristics liegen auf derselben Vendor-Base
            `-3dd4-4255-8d62-6dc7b9bd5561` — **nicht** auf der Bluetooth-Base.

            | UUID16 | Decl | Value | Props |
            |---|---|---|---|
            | 0x2000 | 0x002a | 0x002b | 0x2a read+write+indicate |
            | 0x2001 | 0x002d | 0x002e | 0x0a read+write |
            | 0x2002 | 0x002f | 0x0030 | 0x08 write |
            | 0x2003 | 0x0031 | 0x0032 | 0x02 read |
            | 0x2004 | 0x0033 | 0x0034 | 0x0a read+write |
            | 0x2005 | 0x0035 | 0x0036 | 0x0a read+write |
            | 0x2006 | 0x0037 | 0x0038 | 0x0a read+write |
            | 0x2007 | 0x0039 | 0x003a | 0x08 write |
            | 0x2008 | 0x003b | 0x003c | 0x1a read+write+notify |
            | 0x2009 | 0x003e | 0x003f | 0x02 read |
            | 0x2a19 | 0x0040 | 0x0041 | 0x02 read |
            | 0x200b | 0x0042 | 0x0043 | 0x02 read |
            | 0x2080 | 0x0044 | 0x0045 | 0x02 read |
            | 0x2082 | 0x0046 | 0x0047 | 0x0a read+write |
            | 0x2083 | 0x0048 | 0x0049 | 0x08 write |
            | 0x2084 | 0x004a | 0x004b | 0x22 read+indicate |
            | 0x2086 | 0x004d | 0x004e | 0x02 read |
            | 0x2087 | 0x004f | 0x0050 | 0x2a read+write+indicate |

            Nicht vorhanden im Bereich: 0x200a, 0x2081, 0x2085.
            0x2a19 kollidiert numerisch mit dem SIG-Battery-Level, ist auf der
            Vendor-Base aber etwas anderes.

            **Grenze dieser Quelle:** Das Stack-Log protokolliert Struktur, keine
            Nutzdaten. `gatt_process_notification` erscheint 4× ohne Inhalt; eine
            Suche nach `(len|value|data)=` über alle GATT-Zeilen liefert null
            Treffer. Handle-Werte und Payloads sind aus dem Bugreport **nicht**
            rekonstruierbar. Der Bugreport enthält zudem kein `btsnoop_hci.log`
            — das Entwickleroption-Log war während des Pairings nicht aktiv.
Folge:      Neu `src/skyshutter/ble.py` (Tabelle als Datenstruktur) und
            `tests/test_ble.py` (18 Tests, nageln die Messung fest).
            Verschlüsselter Mitschnitt im Repo: `captures/bt-logs-2026-08-22.tar.gz.gpg`
            (AES256, symmetrisch; Passphrase außerhalb des Repos).
            Offene Frage „ML-L7-kompatibel?" bleibt offen — der Vendor-Service
            0xde00 ist nicht das ML-L7-Profil.

Abgeleitet, nicht gemessen: Vier Handles im Bereich sind unbelegt (0x002c,
0x003d, 0x004c, 0x0051), und genau vier Characteristics können notify oder
indicate. Jede Lücke liegt direkt hinter einem Value-Handle — dort gehört ein
CCCD (0x2902) hin. Plausibel, aber erst durch einen Mitschnitt mit Nutzdaten
belegt.

---

## Fremdmessungen

### 22.08.2026 — Bedeutung der BLE-Characteristics aus fremder Reverse-Engineering-Arbeit
Quelle:     Konstantenliste aus der Hersteller-App, gepostet im dslrdashboard-Forum
            (Thema 2384, zu einer D850) sowie ein Protokoll-Aufsatz zum Ersatz der
            App durch einen ESP32 (skyblond.info/archives/1115.html).
            **Rang: fremde RE-Arbeit, kein Urteil und keine Herstellerdoku.**
Ergebnis:   | UUID | Name laut Quelle | unsere Messung |
            |---|---|---|
            | 0x2000 | AUTHENTICATION | 17 B null, read+write+indicate |
            | 0x2001 | POWER_CONTROL | `03` |
            | 0x2002 | CLIENT_DEVICE_NAME | write-only |
            | 0x2003 | SERVER_DEVICE_NAME | **Gerätename — deckt sich** |
            | 0x2004 | CONNECTION_CONFIGURATION | 102 B |
            | 0x2005 | CONNECTION_ESTABLISHMENT | `03` |
            | 0x2006 | CURRENT_TIME | **Uhr — deckt sich** |
            | 0x2007 | LOCATION_INFORMATION | write-only |
            | 0x2008 | LSS_CONTROL_POINT | `1100`, notify |
            | 0x2009 | LSS_FEATURE | `fd010000` |
            | 0x200a | LSS_CABLE_ATTACHMENT | **fehlt an dieser Kamera** |
            | 0x200b | LSS_SERIAL_NUMBER_STRING | **Seriennummer — deckt sich** |
            | 0x2080 | LSS_CATEGORY_INFO | `03000000` |
            | 0x2081 | LSS_STATUS_FOR_CAPTURE | **fehlt an dieser Kamera** |
            | 0x2a19 | BATTERY_LEVEL | **`0x64` = 100 — deckt sich** |

            Format der Authentifizierung auf `0x2000`, laut Quelle 17 Byte:
            Stufenbyte (0x01–0x04), 8 Byte Zeitstempel, 4 Byte Geräte-ID,
            4 Byte Nonce, alles little-endian. **Die Länge deckt sich mit den
            17 Nullbytes, die wir an dieser Kamera gelesen haben.**
Folge:      Vier unabhängig gemessene Werte bestätigen die Liste — das ist der
            Grund, dem Rest zu trauen. Zwei Einträge der Liste existieren an
            dieser Kamera nicht (0x200a, 0x2081), fünf Characteristics dieser
            Kamera stehen in keiner veröffentlichten Liste (0x2082, 0x2083,
            0x2084, 0x2086, 0x2087) — vermutlich neuere Erweiterungen.
            Namen übernommen in `src/skyshutter/ble.py` (`NAMES`), gelesen zur
            Verifikation, nicht als Code kopiert.

            **Konsequenzen für den Plan:** `0x2005` CONNECTION_ESTABLISHMENT ist
            der Kandidat für den WLAN-Start; davor steht der Handshake auf
            `0x2000`. `0x2008` LSS_CONTROL_POINT ist der Fernauslöser — die
            Kamera trägt das Fernbedienungsprofil also tatsächlich.

Messungen **anderer Leute** an denselben Modellen. Sie zählen nicht als eigene
Messung und schließen kein Gate — sie verschieben nur Wahrscheinlichkeiten und
sagen, wo sich das eigene Messen lohnt. Streng getrennt vom Abschnitt oben.

### 11.01.2026 — P1100 über USB-PTP, libgphoto2 Issue #1201
Quelle:     https://github.com/gphoto/libgphoto2/issues/1201 (geschlossen)
Aufbau:     USB, nicht WLAN. libgphoto2 nach Ergänzung der USB-ID.
Ergebnis:   USB-ID `04b0:0234`, Capture-Flag ergänzt in Commit `f03f31dae`.
            Ordner-Browsing und Download funktionieren (mit selbst erstellter
            udev-hwdb). `--capture-image-and-download` löst aus und **hängt**.
            `--capture-preview` scheitert mit
            `Liveview cannot start: Lens is retracting`.
Folge:      Die Fehlermeldung ist eine Nikon-Vendor-Antwort — die Kamera hat den
            Live-View-Opcode verstanden und beantwortet, nur im falschen
            Objektivzustand. Starkes Indiz, dass `StartLiveView` (0x9201) in
            `operations_supported` steht. Eröffnet USB als zweiten Messpfad, der
            die WLAN- und WPA3-Frage umgeht. Siehe recherche.md, Abschnitt 1.

---

## Widerlegtes

Was wir ausgeschlossen haben — damit es niemand erneut versucht.

| Datum | Annahme | Womit widerlegt |
|---|---|---|
| 22.08.2026 | Der HCI-Snoop-Schalter in den Entwickleroptionen liefert auf diesem Handy einen brauchbaren Mitschnitt | Aufzeichnung war aktiv (`dumpsys bluetooth_manager` → `sSnoopLogSettingAtEnable = FULL`), der Bugreport enthält 310 btsnoop-Dateien unter `FS/data/misc/bluetooth/logs/bthci/CsLog_*/BT_HCI_*.cfa` — **alle exakt 16 Byte, also nur Header ohne ein einziges Paket.** Der Hersteller filtert über `INIT_gd_hal_snoop_logger_filtering=true`. Beide Wege, das abzuschalten, sind ohne Root gesperrt: `device_config put` scheitert mit `SecurityException: must add flag to the allowlist`, `setprop persist.bluetooth.btsnoopenable` mit `Failed to set property`. |
| 22.08.2026 | ~~`01` auf `0x2005` startet den Access Point~~ **Diese Widerlegung war selbst falsch — am 23.08. zurückgenommen.** | Beobachtung damals: nach der Authentifizierung geschrieben, Kamera meldet Erfolg, Wert bleibt `03`, kein AP. **Fehler war die Deutung von `03`:** Das ist kein Ruhewert, sondern derselbe Bitfeld-Wert beim *Lesen* — Bit0 und Bit1 gesetzt heißt „WLAN und Bluetooth aktiv". Wir haben eine Statusmeldung für einen unveränderten Befehlswert gehalten. Der Herstellercode zeigt: `0x01` **ist** der WLAN-Auslöser. Warum es damals wirkungslos blieb, ist offen; wahrscheinlichster Grund ist, dass zu diesem Zeitpunkt noch keine Kopplung bestand — zur selben Zeit lieferte `0x2004` leere Zugangsdaten. |
