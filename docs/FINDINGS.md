# FINDINGS — Messprotokoll

Die einzige Quelle der Wahrheit über die echte Kamera. Alles hier steht, weil es
**gemessen** wurde, nicht weil es plausibel ist. Widerspricht ein Chatverlauf
diesem Dokument, gewinnt dieses Dokument.

Pflege: [playbook.md](playbook.md), Abschnitt 2, Schritt 3.

---

## Stand

Diesen Block liest eine neue Session zuerst. Er wird bei jeder Runde überschrieben.

| | |
|---|---|
| **Phase** | 1 — Ist es PTP/IP? |
| **Erreicht** | **Kopplung reproduzierbar** — skyshutter steht in der Geräteliste der Kamera, Ablauf in [pairing.md](pairing.md) |
| **Offenes Gate** | Nach dem Bonding bleibt die Kamera bei „Establishing connection" stehen |
| **Fehlende Messung** | Zu welchem Dienst die Kamera sich nach dem Bonding verbinden will — RFCOMM/Serial Port wird angeboten und nicht angenommen |
| **Nächster Schritt** | Herausfinden, was die Kamera nach dem Bond erwartet; danach `0x2005`/`0x2008` als gekoppelter Client |
| **Unsere Kennung** | wechselt bei jedem Pairing; die vom letzten Lauf steht im Protokoll |
| **Stand vom** | 2026-08-22 |

**Erste echte Messung liegt vor** (22.08.2026, BLE-GATT-Baum, unten). Der
PTP/IP-Pfad ist davon unberührt: der gesamte Code in `ptp.py`, `ptpip.py`,
`nikon.py` ist weiterhin ausschließlich gegen den Simulator getestet.

---

## Offene Fragen

Spiegelt die Liste in [protokoll.md](protokoll.md); abgehakt wird nur mit Messung.

- [ ] Antwortet die Kamera im Remote-Modus auf TCP 15740?
- [ ] Wird eine ungepaarte GUID akzeptiert, oder ist der BLE-Handshake Pflicht?
- [ ] Welche Vendor-Opcodes stehen in `operations_supported`?
- [ ] Live View vorhanden — Header-Länge, Auflösung, Bildrate?
- [ ] Vendor-Properties für den 125×-Zoom?
- [ ] Verträgt die Kamera parallele Sessions neben SnapBridge?
- [x] Welche IP hat die Kamera als AP tatsächlich? **`192.168.0.10`**
      (22.08.2026 vom Kameradisplay abgelesen, Kanal 6). `192.168.1.1` ist für
      dieses Modell hinfällig — und zugleich das Gateway des Heimnetzes hier,
      also doppelt ungeeignet als Vorgabe.
- [x] WPA3-SAE bestätigt? **Nein — der AP läuft mit WPA2-PSK** (22.08.2026 vom
      Kameradisplay abgelesen). Monitor-Mode und der Mango als Mitschneider
      sind damit brauchbar.
- [ ] Liefert die P1100 über **USB**-PTP eine `operations_supported`-Liste?
      (Fremdmessung #1201 legt nahe: ja — umgeht die WLAN-Frage komplett)
- [ ] Ist die P1100 tatsächlich ML-L7-kompatibel? (zuvor als belegt geführt,
      Nachrecherche fand keine offizielle Bestätigung — der furble-Quick-Win
      hängt daran)
- [ ] Welche Bytes fließen über die write-only-Characteristics 0x2002, 0x2007,
      0x2083? Eine davon dürfte den WLAN-Start auslösen. Braucht einen
      btsnoop-Mitschnitt mit Nutzdaten — der Bugreport gibt sie nicht her.
- [ ] Tragen 0x2000/0x2084/0x2087 (indicate) den Antwortkanal, und 0x2008
      (notify) die Ereignisse? Reine Vermutung aus den Property-Bits.
- [ ] Stimmt die CCCD-Ableitung (Value-Handle + 1) für die vier
      notify/indicate-Characteristics?

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
| 22.08.2026 | `01` auf `0x2005` startet den Access Point | Nach vollständiger Authentifizierung geschrieben, Kamera meldet Erfolg, Wert bleibt danach `03`, kein AP erscheint. Der Schreibzugriff wird angenommen, bewirkt aber nichts. |
