# Stand der Recherche (August 2026)

Ziel des Projekts: eine eigene API für **Livebild + Steuerung** der Nikon Coolpix
P1100 über WLAN, mit Blick auf die verwandten Modelle P900 und P1000.

Dieses Dokument sammelt den **Wissensstand aus fremden Quellen**. Es ist kein
Messprotokoll — was an der eigenen Kamera gemessen wurde, steht ausschließlich in
[FINDINGS.md](FINDINGS.md). Jede Aussage hier trägt einen Rang:

| Rang | Bedeutung |
|---|---|
| **[PRIMÄR]** | Spezifikationstext, Quellcode oder eine fremde, dokumentierte Messung |
| **[SEKUNDÄR]** | Herstellerdokumentation, Handbuch, Kompatibilitätsliste |
| **[COMMUNITY]** | Forum, Blog, Issue-Kommentar |
| **[UNBELEGT]** | plausibel, aber ohne Beleg — als Vermutung behandeln |

---

## 1. Die Kernfrage und was sie inzwischen wahrscheinlich macht

> **Stand 23.08.2026 — die Hypothese dieses Abschnitts ist zur Hälfte
> bestätigt.** Dass die Kamera **PTP mit Nikon-Vendor-Opcodes** spricht, ist
> gemessen: 38 Operationen über USB ausgelesen, darunter Live View, Zoom und
> Auslöser. Offen ist nur noch, ob sie dasselbe **über TCP 15740** anbietet —
> der Port steht im Herstellercode, geöffnet hat sie ihn für uns noch nie.
> Alles Gemessene: [referenz.md](referenz.md).
>
> Der folgende Abschnitt ist der Rechercheweg dorthin und bleibt als solcher
> stehen.

Die Arbeitshypothese lautete: Die Coolpix spricht im Fernsteuerungsmodus PTP/IP auf
TCP 15740 mit Nikon-Vendor-Opcodes. Drei Befunde stützten sie damals.

**Erstens — die P1100 antwortet auf den Live-View-Opcode.** libgphoto2-Issue
[#1201](https://github.com/gphoto/libgphoto2/issues/1201) (geschlossen 11.01.2026)
enthält eine fremde Messung an genau diesem Modell über **USB**-PTP:

- USB-ID `04b0:0234`, Capture-Flag ergänzt in Commit `f03f31dae`
- Dateibrowsing und Download funktionieren
- `--capture-image-and-download` löst aus und hängt danach
- `--capture-preview` scheitert mit `Liveview cannot start: Lens is retracting`

Diese Fehlermeldung ist eine Nikon-Vendor-Antwort. Die Kamera hat den Opcode
**verstanden und beantwortet**, sie war nur im falschen Objektivzustand. Das ist
ein starkes Indiz, dass `StartLiveView` (0x9201) in `operations_supported` steht.
[PRIMÄR — fremde Messung, USB, nicht WLAN]

**Zweitens — der Transport ist bei Nikon historisch PTP/IP.** Die
Wireless-Mobile-Utility-Generation (P900-Ära) und die WU-1a/1b-Dongles
transportieren über PTP/IP auf 15740; darauf setzen airnef und qDslrDashboard auf.
[COMMUNITY, konvergent aus mehreren unabhängigen Quellen]

**Drittens — libgphoto2 kennt WLAN-Nikons, aber keine WLAN-Coolpix.** In
`camlibs/ptp2/library.c` stehen P900 (`04b0:019c`), P1000 (`04b0:0232`) und P1100
(`04b0:0234`) ausschließlich als USB-`PTP mode`. Die WLAN-Liste führt nur
generisch „Nikon DSLR (WLAN)" und „Nikon 1 (WLAN)". [PRIMÄR, negativer Befund]

Was daraus folgt: Die Frage ist nicht mehr *ob* die Kamera PTP-Vendor-Opcodes
kennt, sondern ob sie den PTP/IP-**Transport** über WLAN öffnet und unter welchen
Bedingungen. Genau das prüft `skyshutter probe`.

---

## 2. Spezifikationen

| Dokument | Verfügbarkeit | Rang |
|---|---|---|
| **CIPA DC-005:2005 — PTP-IP** | **frei**, 10 Seiten: https://www.cipa.jp/std/documents/e/DC-X005.pdf | [PRIMÄR] |
| CIPA DC-005 Whitepaper (Erläuterung) | frei: https://www.cipa.jp/ptp-ip/documents_e/CIPA_DC-005_Whitepaper_ENG.pdf | [SEKUNDÄR] |
| ISO 15740 / PIMA 15740 — PTP-Kern | **kostenpflichtig**, kein freier Volltext. Nur Vorschau bei iteh.ai | [PRIMÄR, nicht frei] |
| USB Still Image Class Spec (PTP über USB) | frei bei usb.org, `usb_still_img10.pdf` | [PRIMÄR] |
| **gPhoto-PTP/IP-Doku** | frei, enthält das vollständige Paketlayout: http://gphoto.github.io/doc/ptpip/ | [SEKUNDÄR, community-primär] |

Der Handshake ist damit vollständig aus freien Quellen rekonstruierbar. Das
Paketlayout laut gPhoto-Doku: 4 Byte Länge (LE) + 4 Byte Typ (LE) + Payload.

| Typ | Paket | Payload |
|---|---|---|
| 1 | Init_Command_Request (I→R) | 16 Byte GUID + WCHAR-Rechnername, `\0`-terminiert |
| 2 | Init_Command_Ack (R→I) | 4 Byte Session-ID + 16 Byte GUID + WCHAR-Kameraname |
| 3 | Init_Event_Request (I→R) | 4 Byte Session-ID aus dem Ack |
| 4 | Init_Event_Ack | leer |
| 6/7 | Cmd_Request / Cmd_Response | |
| 8 | Event | |
| 9/10/12 | Start_Data / Data / End_Data | |
| 13 | Ping / Pong | |

Bei der Referenzkamera der gPhoto-Autoren war die GUID im Ack die MAC-Adresse.
Die gPhoto-Doku listet als PTP/IP-Kameras unter anderem **Coolpix P1–P4 und S6**
(2005er-Generation) — also gab es WLAN-PTP/IP in der Coolpix-Linie schon einmal.
Auf die P900-Generation ist das nicht übertragbar. [UNBELEGT für P900+]

---

## 3. Codequellen

Das Repo kann bei Bedarf von MIT auf LGPL wechseln — die Lizenzspalte ist deshalb
Information, kein Ausschlusskriterium. Opcode-**Nummern** sind ohnehin Fakten und
nicht schutzfähig; nur der Code-Ausdruck ist es.

| Projekt | Inhalt | Lizenz |
|---|---|---|
| **libgphoto2 `camlibs/ptp2/`** | `ptp.h` mit allen `PTP_OC_NIKON_*` / `PTP_DPC_NIKON_*`; `ptpip.c` mit dem Transport; `library.c` mit der Kameratabelle | LGPL-2.1 |
| **Wireshark `packet-ptpip.c`** | Dissector für den Handshake; kennt Standard-Opcodes 0x1000–0x1025, **keine** Nikon-Vendor-Opcodes | GPL-2.0+ |
| **petabyt/libpict** (ex-camlib) | schlanke `PtpRuntime`-Abstraktion, Opcode-Layer generisch, Vendor-Extensions als eigene Module (`src/canon.c`) | Apache-2.0 |
| **petabyt/vcam** | PTP-Responder / Kamerasimulator für USB, PTP/IP, UPnP — Regressionstests ohne Hardware | — |
| **mmattes/ptpip** | Python-PTP/IP, gegen eine Nikon D5300 getestet, Default `192.168.1.1:15740` | ungeprüft |
| **tengelmeier/mtp-tools** | Lua-Dissector für Wireshark, explizit auf Vendor-Opcodes erweiterbar | — |
| **simeonpilgrim/nikon-firmware-tools** | Nikon-Firmware-Werkzeuge, enthält `wireshark_usb_ptp_20130305.patch` mit Nikon-Opcodes (USB, nicht PTP/IP) | — |
| libptp2 | historischer Fork, Basis von libgphoto2 | GPL |

### Nikon-Vendor-Opcodes (aus `ptp.h`, verifiziert)

Vendor-Bereich ist `0x9000–0x9FFF`.

| Opcode | Name |
|---|---|
| 0x90C3 | `DelImageSDRAM` |
| 0x90C8 | `DeviceReady` |
| 0x9200 | `GetPreviewImg` |
| **0x9201** | **`StartLiveView`** |
| 0x9202 | `EndLiveView` |
| **0x9203** | **`GetLiveViewImg`** |
| 0x9204 | `MfDrive` — manueller Fokus per Kommando |
| 0x9205 | `ChangeAfArea` |
| 0x9206 | `AfDriveCancel` |
| 0x9421 | `GetObjectSize` |

Ebenfalls vorhanden: `AfDrive`, `ChangeCameraMode`, `InitiateCaptureRecInMedia`,
`AfCaptureSDRAM`.

Bekannte Nikon-Eigenheit: Issue
[#1135](https://github.com/gphoto/libgphoto2/issues/1135) zeigt, dass eine Z8 über
PTP/IP bei Property-Abfragen `PTP_RC_OperationNotSupported` (0x2005) liefert,
obwohl die Grundverbindung steht. Die PTP/IP-Property-Menge ist bei Nikon also
**nicht** deckungsgleich mit der USB-Menge. [COMMUNITY]

---

## 4. Das Coolpix-WiFi-Protokoll: zwei Generationen

**Wireless Mobile Utility (WMU)** — die ältere App, P900-Generation. Transport ist
PTP/IP auf 15740; darauf setzen airnef und qDslrDashboard auf. Kein offizielles
Protokolldokument, keine veröffentlichte RE der App selbst. [COMMUNITY]

**WU-1a/WU-1b** — die externen WLAN-Dongles derselben Ära. Joe Fitz hat den WU-1a
2012 hardwareseitig aufgemacht: eine PTP-zu-PTP/IP-Bridge mit Nikon-Firmware auf
einem Broadcom BCM4336. Die Funkschicht wurde nicht vollständig reversed, nur die
Bridging-Logik. [COMMUNITY, hardwareseitig primär]

**SnapBridge** — die aktuelle App, Zwei-Schicht-Modell: BLE hält eine
Dauerverbindung für Auto-Transfer, GPS und Uhrzeit; für Live View und
Fernauslösung schaltet die App auf WLAN um, das die Kamera selbst aufbaut.
[SEKUNDÄR, Nikon-Onlinehilfe]

Bei Coolpix ist der Fernsteuerungsmodus gegenüber DSLR und Z-Serie **bewusst
beschnitten**: nur Auslöser, kein Zugriff auf Blende, ISO, Verschlusszeit oder
AF-Punkt; teils nur im P/Auto-Modus. Mehrfach in Foren bestätigt. [COMMUNITY]

**Das ist eine Aussage über die App, nicht über das Protokoll.** Ob die Kamera die
Vendor-Properties auf dem Draht verweigert oder ob nur die App sie nicht anbietet,
ist offen — und genau der Punkt, an dem eine eigene API mehr können könnte als
SnapBridge. Umgekehrt kann die Beschränkung auch in der Kamerafirmware sitzen.
Ohne Messung ist beides gleich plausibel. [UNBELEGT]

Ob die Coolpix im WLAN-Remote-Modus tatsächlich einen PTP/IP-Server auf 15740
öffnet, ist **durch keinen Mitschnitt belegt**. [UNBELEGT]

> **Nachtrag 23.08.2026:** Der Port `15740` steht als Konstante `0x3d7c` im
> Verbindungsaufbau der Hersteller-App, zusammen mit der Initiator-GUID
> `00112233-4455-6677-8899-AABBCCDDEEFF` und dem Namen `Android Device`. Das
> belegt, dass die App ihn erwartet — nicht, dass die Kamera ihn öffnet.
> Die Frage bleibt offen, ist aber nicht mehr ganz unbelegt.

### Kamera-IP

`mmattes/ptpip` nutzt `192.168.1.1` als Vorgabe; für WU-1a/1b-Setups ist das der
übliche Wert. Für Coolpix mit eingebautem WLAN empfehlen airnef-Nutzer
`192.168.0.10`, weil `192.168.1.1` mit der Router-IP kollidiert. [COMMUNITY, real
getestet] — beide Werte gehören in den Scan von `skyshutter probe`.

---

## 5. Modellvergleich

|  | P900 (2015) | P1000 (2018) | P1100 (2025) |
|---|---|---|---|
| App | WMU, später auch SnapBridge (Android) | SnapBridge | SnapBridge |
| WLAN | 802.11b/g/n | 802.11b/g, WPA2-PSK | 802.11b/g/n 2,4 GHz, **WPA3-SAE** [SEKUNDÄR] |
| Bluetooth | keins | BT 4.1 inkl. BLE | BT 5.1/5.2 |
| USB | Micro-USB | Micro-USB | USB-C |
| USB-PID | `04b0:019c` | `04b0:0232` | `04b0:0234` |
| RAW | nein, nur JPEG | ja, `.NRW` | ja, `.NRW` |
| längste Zeit in M | 15 s bei ISO 100 | 30 s, plus Bulb/Time bis 60 s | 30 s laut Onlinemanual; Bulb nur sekundär behauptet [UNBELEGT] |
| ML-L7-Fernbedienung | — | offiziell gelistet | **nicht bestätigt** — siehe unten |

**Offener Widerspruch:** Eine frühere Fassung dieses Dokuments nannte
ML-L7-Kompatibilität der P1100 als gegeben; die Nachrecherche fand dafür **keine
offizielle Bestätigung** — die Nikon-Kompatibilitätsliste der ML-L7 führt
P1000/P950/B600/A1000. Das ist relevant, weil der furble-Quick-Win daran hängt.
Vor dem ESP32-Abend prüfen. [UNBELEGT, war zuvor als belegt geführt]

**WPA3-SAE ist mehr als eine Fußnote.** Bei WPA2-PSK genügen Passphrase, SSID und
ein vollständiger 4-Way-Handshake, um in Wireshark zu entschlüsseln. Bei SAE hat
jede Sitzung einen eigenen PMK (Forward Secrecy) — dann geht Monitor-Mode nur noch
mit dem PMK zur Laufzeit aus `wpa_supplicant -d -K`. Der Umweg über den GL-X3000
ist davon unberührt, weil dort hinter der Entschlüsselung mitgeschnitten wird.
[PRIMÄR, Wireshark-Doku]

---

## 6. Reverse-Engineering-Werkzeuge

**Netzwerk.** Drei Wege: PCAPdroid auf dem Phone (kein Root, VpnService-basiert —
verändert aber L3/L4-Header, für Payload gut, für Timing unbrauchbar); Traffic über
den GL-X3000 routen und dort `tcpdump` (1:1-Sicht, entspricht dem vorhandenen Rig);
Monitor-Mode mit Entschlüsselung (nur bei WPA2 praktikabel, siehe oben). mitmproxy
scheidet aus — PTP/IP ist rohes TCP ohne HTTP-Layer.

**Bluetooth.** Entwickleroptionen → HCI-Snoop-Log aktivieren → Bluetooth neu
starten → `adb bugreport` → `FS/data/log/bt/btsnoop_hci.log` → Wireshark.
Live-Capture über `androiddump` ist auf neueren Android-Versionen oft defekt; der
Bugreport-Weg ist robuster. [SEKUNDÄR]

**App-Analyse.** APKMirror gilt als vertrauenswürdigster Bezug (prüft Signaturen
gegen den Play-Store-Build, re-signiert nicht). `jadx` für den Java/Kotlin-Layer,
`apktool` für Ressourcen und Manifest, Ghidra für native `.so`. Eine veröffentlichte
SnapBridge-Teardown mit Klassennamen existiert nicht — Foolography berichtet, selbst
daran zu arbeiten, und dass SnapBridge BT Classic, BLE und WLAN mischt. Erstsichtung
ein Abend; vollständige Extraktion bei R8-Verschleierung eher eine Woche.

**Firmware.** nikonhacker.com und `simeonpilgrim/nikon-firmware-tools` sind die
etablierte Community, inklusive Ghidra-Loader für Fujitsu FR (EXPEED 1–3). Für
ältere Coolpix-ARM-Blobs ist unverschlüsselte Firmware mit bloßer Header-Prüfsumme
dokumentiert; für die P1100 ist die Lage unbekannt. Als Einstieg ungeeignet
(Wochen), als Rückfallebene sinnvoll.

**Simulator.** `petabyt/vcam` emuliert PTP/IP als Responder. Wertvoll, weil er den
eigenen Client gegen eine **fremde** Implementierung testet statt gegen die eigene
Annahme — der vorhandene Simulator kann das konstruktionsbedingt nicht.

**Recht.** § 69e UrhG erlaubt Dekompilierung zur Herstellung von Interoperabilität,
beschränkt auf die dafür notwendigen Programmteile. Eine eigene API für die eigene
Kamera fällt darunter. [PRIMÄR, Gesetzestext]

---

## 7. Andockpunkte — wohin die API sprechen sollte

Damit die API kein Inselprojekt wird, gibt es zwei etablierte Ziele.

**ASCOM Alpaca** — REST/HTTP+JSON, plattformunabhängig. Offizielles
Python-Serverframework `AlpycaDevice` (ASCOM Initiative, Falcon-basiert),
Conformance-Prüfer `ConformU`, Referenzserver mit Swagger. Entscheidend: mit
`alex-pirozhenko/alpaca-libgphoto2` existiert bereits ein Präzedenzfall, der genau
diesen Weg geht (ICameraV4 auf AlpycaDevice-Template über libgphoto2). Clients:
N.I.N.A., SharpCap, APT.

**INDI** — XML über TCP 7624. Treiber erben offiziell von `INDI::CCD` in C++, aber
das Wire-Protokoll ist offen genug für reine Python-Treiber; `indi_pylibcamera` ist
die funktionierende Referenz dafür. `pyindi-client` ist dagegen nur eine
**Client**-Bindung, keine Treiber-API. Client: KStars/Ekos.

Empfehlung: **Alpaca zuerst.** REST/JSON passt zur stdlib-Python-Architektur ohne
SWIG oder C++-Bindings, es gibt ein offizielles Template, einen Conformance-Test
und einen direkten Präzedenzfall. INDI lohnt als Zweitschritt, falls Ekos gebraucht
wird — dann als dünner Treiber über dieselbe API, nicht als Parallelimplementierung.

---

## 8. Was die Hardware für Astro hergibt

Die Randbedingungen begrenzen, was eine API überhaupt nützlich machen kann.

- **P900** scheidet für ernsthafte Astronutzung weitgehend aus: kein RAW, 15 s
  maximale Belichtung, kein Bulb.
- **P1000/P1100** liefern RAW (`.NRW`) und 30 s in M; die P1000 zusätzlich Bulb/Time
  bis 60 s. Für die P1100 ist Bulb nur sekundär behauptet. [UNBELEGT]
- Die P1000 hat einen eingebauten Intervallometer und Zeitraffer-Presets
  („Night sky", „Star trails" bis 150 Min).
- Manueller Fokus mit Focus Peaking ist vorhanden; die Community nennt
  **Fokus-by-wire mit Hysterese** als Hauptproblem — Überschwingen beim manuellen
  Fokussieren am Ring.
- Zweites Hauptproblem: Verwacklung bei 3000 mm. Ohne Fernauslöser behilft man sich
  mit dem Selbstauslöser.
- `.NRW` öffnet nicht in Adobe; Umweg über Capture NX-D nach TIFF. Für
  Lucky Imaging läuft `.MOV` über PIPP nach AutoStakkert.

Daraus die drei API-Funktionen mit dem höchsten Astro-Nutzen:

1. **Fernauslösung mit Verzögerung** — löst das Verwacklungsproblem besser als
   Selbstauslöser oder Kabel.
2. ~~**Live View plus Fokus per Kommando** (`MfDrive`, 0x9204) — umgeht die
   Fokus-by-wire-Hysterese. Das ist die eigentliche Rechtfertigung des ganzen
   Projekts.~~
   **Widerlegt am 23.08.2026.** `0x9204` steht **nicht** in der gemessenen
   Operationsliste dieser Kamera, und die Hersteller-App kennt den Opcode für
   kein einziges Modell — Volltextsuche über die gesamte App, null Treffer.
   Manueller Fokus per Kommando ist über PTP nicht möglich.
   **Was bleibt:** Live View plus Autofokus (`0x90C1`) und Setzen des
   Messfeldes (`0x9205`). Für helle, kontrastreiche Ziele wie den Mond
   tragfähig; für schwache Objekte ein echter Verlust.
3. **Intervallserie mit Parametervariation und direktem Download** — Grundlage für
   Belichtungsreihen ohne Kartenwechsel. Der Bildabruf ist geklärt
   (`GetPartialObject` in 1-MiB-Blöcken, fortsetzbar); einen Intervallometer im
   PTP-Layer gibt es **nicht**, die Serie muss der Client selbst fahren.

Punkt 2 und 3 setzen voraus, dass die Kamera über WLAN mehr zulässt als SnapBridge
anbietet.

~~Trifft die Beschränkung auch auf dem Draht zu, bleibt Punkt 1 — und dafür
genügt der ML-L7-Weg über furble.~~ **Auch das ist widerlegt:** Die Kamera
meldet über ihre Feature-Bits (`0x2009`, Bit 11), dass sie Kamerasteuerung über
Bluetooth **nicht** anbietet, und die dafür nötigen Characteristics fehlen ihr.
Der Fernauslöser über BLE ist an diesem Modell keine Rückfallebene — es gibt
keine. Details in [referenz.md](referenz.md).

---

## 9. Vorbilder aus anderen Herstellerwelten

| Hersteller | Protokoll | Offenheit |
|---|---|---|
| Canon | **CCAPI**, offiziell REST/HTTP+JSON ab ~2019 | Doku hinter kostenloser Registrierung; Clients: `horshack-dpreview/Canomate` (Python, GPL-3.0) |
| Sony | altes **Camera Remote API** (HTTP/JSON-RPC, UPnP-Discovery) frei dokumentiert; neues SDK ist PTP/IP und closed | `petabite/libsonyapi`, `erik-smit/sony-camera-api`; PTP/IP-Reimplementierung in `alpha-fairy` |
| Panasonic | **`cam.cgi`** über HTTP-GET | community-dokumentiert: `cleverfox/lumixproto`, `gavinwilliams/open-gh4`, `njfdev/liblumix` |
| Olympus | OI.Share / OPC, CGI-Endpunkte | `ccrome/olympus-omd-remote-control`, offizielle AIR-SDK-Doku |
| Fujifilm | proprietär über WLAN | `petabyt/fudge` |

**Architektur zum Abschauen** ist libgphoto2 selbst: vier saubere Schichten — CLI →
libgphoto2-API → camlib (Kameratreiber) → libgphoto2_port (Transport). Innerhalb
`ptp2` nochmals getrennt in generischen PTP-Kern (`ptp.c/h`, auch von libmtp
genutzt) und gphoto-Glue (`library.c`, `ptpip.c`, `usb.c`). Genau die Trennung
Transport / Opcode / High-Level, die dieses Projekt braucht.

Kleiner und direkter nachvollziehbar: `petabyt/libpict` mit `PtpRuntime` als
Transportabstraktion und Vendor-Extensions als separate Module — plus `vcam` als
Simulator daneben. Dieselbe Aufteilung, die hier schon angelegt ist.

Kein Projekt vereint CCAPI, Sony-JSON-RPC und PTP/IP hinter einer Schnittstelle.
Die HTTP-Welt und die PTP-Welt bleiben in der Praxis getrennt.

---

## 10. Was nachweislich nicht existiert

Vier Agenten haben unabhängig voneinander gesucht. Negativbefunde, jeweils mit
benannter Suchbreite:

- **Kein PTP/IP-Codepfad für P900/P1000/P1100** in libgphoto2 — nur generische
  WLAN-Nikon-Einträge. [PRIMÄR]
- **Kein öffentlicher pcap-Mitschnitt** einer Nikon-WLAN-Kamera. Weder WMU noch
  SnapBridge noch WU-1a/1b. Alle bekannten RE-Arbeiten stützen sich auf Code und
  Verhalten, nicht auf veröffentlichte Mitschnitte.
- **Keine veröffentlichte SnapBridge-Teardown** mit Klassennamen oder PTP-Layer.
- **Kein Coolpix-SDK.** Das offizielle Nikon SDK deckt Z- und D-Serie ab.
- **Kein Repo, kein Gist, kein Forenthread** zu WLAN-RE der P1000/P1100. Gesucht
  wurde auf GitHub (Code, Issues, Discussions, Gists), Reddit, DPReview, Nikonians,
  CloudyNights, Stack Overflow, Hackaday.
- **Keine kommerzielle App mit Coolpix-WLAN-Fernsteuerung.** qDslrDashboard: kein
  Coolpix-Support. CamRanger: nicht gelistet. Cascable: nicht bestätigt. Einzige
  Ausnahme: Foolography Unleashed führt die P1000 mit „reduced features" —
  vermutlich reiner Bluetooth-Trigger. [SEKUNDÄR]
- **libgphoto2 #477** (P1000-Support, eröffnet 25.02.2020) ist weiterhin **offen**;
  Maintainer haben geantwortet, vollständiger Support ist nie gelandet.
- Als benannte Pakete nicht auffindbar: `pyptp`, `ptpy`, `node-ptp`.

Die Lücke im Ökosystem ist damit belegt, nicht nur vermutet.

---

## 10b. Wie das Bild zu einem Stream wird — drei Wege

Recherchestand 22.08.2026. Die Frage lautet nicht „geht Streaming", sondern
über welchen Kanal das Bild die Kamera verlässt.

### HDMI — belegt, sofort, und schließt dieses Projekt aus

Clean HDMI ist ein **offiziell beworbenes Merkmal** dieses Modells
[PRIMÄR, Herstellerdoku]: Micro-HDMI Typ D, Informationsanzeige abschaltbar,
Ausgabeauflösung wählbar. Ein UVC-Capture-Stick (20–40 €) macht daraus ohne
jedes Protokollwissen einen Stream.

Der Preis steht im selben Handbuchabschnitt:

> „Wireless communication is not available when the camera and an
> HDMI-compatible device are connected."

Dazu bei eingeschaltetem Clean HDMI: **kein 4K**, **keine Standbildaufnahme**,
kein Peaking, Kameradisplay aus. Über USB steht dort nichts — es scheint als
einziger Kanal offen zu bleiben.

**Konsequenz: HDMI und skyshutter schließen sich aus.** Steckt das Kabel, ist
die gesamte BLE- und WLAN-Strecke tot. Als Rückfallebene brauchbar, als
Erstwahl beendet es das Projekt in seiner jetzigen Form.

### USB-PTP — durchgeführt, mit eindeutigem Ergebnis

> **Nachtrag 23.08.2026:** Der hier beschriebene Test wurde gemacht. Ergebnis:
> **PTP über USB funktioniert vollständig** — die gesamte Operationsliste in
> [referenz.md](referenz.md) stammt daher. **Live View über USB funktioniert
> nicht**, und zwar prinzipiell: Die Kamera zieht beim Anstecken das Objektiv
> ein und meldet über Property `0xD1A4` Bit 24, dass Live View gesperrt ist.
> `ChangeCameraMode` lässt sich nicht dagegen setzen.
>
> Damit ist auch die Frage der beiden Fremdberichte beantwortet, die genau hier
> hängengeblieben sind. Der ursprüngliche Text bleibt als Herleitung stehen.

Die Ausgangslage war:

Issue #1201 zu diesem Modell und Issue #780 zum P950 zeigen dasselbe Bild:
Browsing und Download funktionieren, `--capture-preview` scheitert mit
`Liveview cannot start: Lens is retracting`. Beide Fälle ungelöst, der P950-Fall
ebenfalls für Astrofotografie. **Kein bestätigter Erfolg bei irgendeiner
Coolpix.** [PRIMÄR, fremde Messung]

Die Meldung ist aber eine **Antwort der Kamera**, kein Absturz — sie hat den
Opcode verstanden und verweigert ihn wegen eines Zustands. In keinem der beiden
Berichte steht, dass jemand es mit ausgefahrenem Objektiv im Aufnahmemodus
versucht hat.

**Der Hebel liegt darin, dass die Live-View-Opcodes transportunabhängig sind.**
Klärt sich „Lens is retracting" über Kabel, wissen wir auch, ob der WLAN-Weg
jemals ein Bild liefern kann — bevor der AP-Trigger geknackt ist.

Weg unter WSL: `usbipd-win` reicht das Gerät an Linux durch, dann gphoto2.

### PTP/IP über WLAN — das Ziel, blockiert am AP-Trigger

Danach fehlt keine Zeile Code: `ptpip.py` spricht den Transport, `nikon.py` hat
`start_live_view`, `get_live_view_frame` und `stream_live_view`, `mjpeg.py` ist
ein fertiger HTTP-MJPEG-Server.

### Aufwand für einen USB-Transport

`nikon.py` benutzt von seiner Verbindung **nur `transaction()`**. Ein
USB-Transportmodul mit derselben Methode — PTP-über-USB ist Bulk-In/Bulk-Out
mit einem 12-Byte-Container statt TCP-Rahmen — genügt; `nikon.py`, `mjpeg.py`
und die CLI bleiben unangetastet.

### Nicht verfügbar

Nikons **Webcam Utility unterstützt die Coolpix-Linie nicht** — die Liste ist
Z-Serie und DSLR. Die auf Produktseiten kursierende Kameraliste mit P1000 ist
die SnapBridge-Liste, nicht die des Webcam-Werkzeugs. [PRIMÄR, negativer Befund]

---

## 11. Was sich für den Plan ändert

1. **USB ist ein zweiter, unabhängiger Messpfad.** Issue #1201 zeigt, dass die
   P1100 über USB-PTP antwortet und Vendor-Fehler zurückgibt. `operations_supported`
   lässt sich damit auslesen, **ohne** dass die WLAN-Frage geklärt ist — und ohne
   das WPA3-Problem. Das umgeht die aktuelle Blockade in Phase 1 teilweise.
2. **Die Live-View-Frage ist halb beantwortet.** Der Opcode existiert und wird
   beantwortet. Offen ist nur noch der Objektivzustand und der Transport.
   Nachtrag 22.08.: Beim P950 scheitert derselbe Aufruf mit derselben Meldung,
   ebenfalls ungelöst — es gibt **keine Coolpix mit belegtem Live View über
   PTP**. Der Test mit ausgefahrenem Objektiv im Aufnahmemodus steht aus und
   ist der billigste offene Messpunkt des Projekts. Siehe Abschnitt 10b.
3. **`vcam` als Gegenprobe** neben dem eigenen Simulator einplanen.
4. **ML-L7-Kompatibilität der P1100 vor dem furble-Abend prüfen** — sie ist
   unbelegt.
5. **Alpaca als Zielschnittstelle** vormerken, sobald der Client steht.
