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
| **Phase** | **Tracking-Kette end-to-end bewiesen (Stream→star_tracker→ZMQ→Mount-Loop, mock)** — Produktion fehlt nur Nacht-Parameter + FTDI/indi/Unpark |
| **Erreicht** | 38 Operationen, 22 Properties gemessen · **LsSec geknackt** · **Classic-Bond am Raspberry** · **AP-Start + Join** · **Live-View 1552×1162 FULL, systemd selbstheilend (26 s + bluetoothd-Race + LV-Prohibit-Retry)** · **Capture+Download an HW validiert** · **ISO/EV/Drive schreibbar** · **Zoom kalibriert** · **CV-Rauschfloor 0,06 px** · **ZMQ-Brücke zum AZ-GTi-Mount-Loop im Mock bewiesen (30/30 Frames)** (173 Tests) |
| **Erreicht (alt)** | **AP-Start geknackt.** `remote-start.py` fährt den korrigierten Flow (CCCs + VALID_WAKE + Bond + `0x2005`=01) und die Kamera öffnet ihren WLAN-AP |
| **Erreicht (neu)** | **Feld-Rig steht.** Raspberry (reComputer R2140, Debian 12, 4×A76/16 GB, Hailo) = Funk-Zentrale: WLAN+BLE an Bord (`wlan0`/`hci0`, beide aktiv, bleak-Scan ok). `remote-start.py` auf Linux portiert und auf dem Raspberry deployt (`~/projekte_hardware/skyshutter`, venv + bleak 3.0.2 + pycryptodome). Mango = reiner AP/Router/Zugang (192.168.1.143 WAN, LAN 192.168.3.178, DNAT 2222→22 + 8080→8080). |
| **Offenes Gate** | Alle Kern-Features bewiesen oder entschieden. Verworfen/negativ: 0x941E (wirkungslos oder Session-Kill), Event-Socket (schweigt — Polling via 0x941C ist der Weg). Rest: `0x9520/21` uninteressant bis auf Weiteres. **Nächster Block: CV-Pipeline auf den Stream.** |
| **Nächster Schritt** | (a) **Nachtvalidierung CV** (jetzt ~22:30 ab Dunkelheit): `python3 tools/cv/star_tracker.py --duration 120 --out /tmp/stars.csv --zmq` an echten Sternen → min/max-area kalibrieren. WLAN-Tode (−71 dBm) überbrückt der Wrapper in ~60–90 s — Lücken tolerierbar. (b) Physisch: Pi-Antenne/Position relativ Kamera prüfen (Metall weg), Kamera-Akku am Display. (c) FTDI-Kabel anschließen + `ASTRO_BACKEND=indi` + Unpark (erst dann echte Bewegung). |
| **Danach** | CV-Pipeline (astro-cv-tracker-Know-how + Hailo) auf den Stream setzen. |
| **Nicht erreichbar** | manueller Fokus (`0x9204` fehlt), Bulb-Auslöser (`0x920C` fehlt), Auslösen über Bluetooth (Feature-Bit 11 = 0) |
| **Unsere Kennung** | wechselt bei jedem Pairing; die vom letzten Lauf steht im Protokoll |
| **Stand vom** | 2026-08-26 (Belichtungs-Properties vollständig kartiert; Astro-Stream+Auslöser stabil) |

**Erste echte Messung liegt vor** (22.08.2026, BLE-GATT-Baum, unten). Der
PTP/IP-Pfad ist davon unberührt: der gesamte Code in `ptp.py`, `ptpip.py`,
`nikon.py` ist weiterhin ausschließlich gegen den Simulator getestet. Das
neu implementierte Phase-A-Inventar (Properties & Storage) wartet auf die
erste physische Hardware-Verifikation, um das Annahmeformat für `0x90CA` zu
bestätigen.

---

## Offene Fragen

Abgehakt wird nur mit Messung. Beantwortetes bleibt stehen — die Antwort ist
oft mehr wert als die Frage.

### Offen

- [ ] **Welches exakte Datenformat liefert `0x90CA` (GET_VENDOR_PROP_CODES)?**
      ~~Verifikation ausstehend.~~ **ERLEDIGT 26.08.: Die Operation wird nicht
      unterstützt (0x2005, doppelt gemessen). Es gibt kein Format — die Frage
      entfällt.**
- [x] **Startet `0x01` auf `0x2005` den Access Point?** **JA** — mit
      vorhandenem Classic-Bond akzeptiert (24.08. 21:29, „accepted“), AP
      broadcastet nach ~80 s. Beantwortet 24.08.
- [x] Antwortet die Kamera im WLAN-Modus auf TCP 15740? **JA** — PTP/IP-
      Verbindung + Live-View-Frames (24.08. 21:46, `docs/proof/`).
- [ ] Wird eine beliebige GUID akzeptiert? Die App benutzt für alle
      Installationen dieselbe, was dagegen spricht, dass die Kamera darüber
      unterscheidet.
- [ ] Verträgt die Kamera eine zweite Sitzung neben der Hersteller-App?
- [x] **Wie groß sind die Live-View-Bilder wirklich, und welche Bildrate hält
      die Kamera durch?** Remote-Modus (ControlMode 1): ~25–36 kB Frames,
      Stream-Dienst hält 15 fps über Stunden (26.08., systemd-Dauerbetrieb).
      Abgehakt 26.08.
- [x] **Lässt sich der Zoom über `0x9016` tatsächlich fahren, und in welchen
      Schritten?** **JA** — EXIF-bewiesen: 6× (0,1) = 4,3→10,7 mm (26.08.).
      Ein Befehl = ein Schritt; größere Schrittwerte ungemessen. Abgehakt
      26.08.
- [ ] Was tun `0x2082`–`0x2087`? Sechs Characteristics, die die Hersteller-App
      **nicht kennt** — nur an der Kamera selbst zu erschließen.
- [ ] Was sind die Properties `D303`, `D406`, `D407`? Ebenfalls in der App
      nicht auffindbar. **Rohwerte 26.08. gemessen:** D303=`01` (u8),
      D406=`010000`, D407=`01000000` (u32=1) — Deutung weiterhin offen.
- [x] Stimmt die CCCD-Ableitung (Value-Handle + 1)? **JA** — am 22.08. direkt
      am GATT-Baum der Kamera bestätigt: die vier Deskriptoren sitzen bei
      0x002c/0x003d/0x004c/0x0051, je +1 über dem Value-Handle (belegt in
      `src/skyshutter/ble.py` Docstring `cccd_handle`, referenz.md Abschnitt 1).
      Abgehakt 24.08. (Deep-Dive).
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
- [x] **Wie sind die WLAN-Zugangsdaten geschützt, und lassen sie sich lesen?**
      Blowfish-CBC, **vollständig geknackt am 23.08.** Der Sitzungsschlüssel
      leitet sich aus den Handshake-**Zeitstempeln** ab (nicht device/nonce, das
      war der frühere Irrtum), der Nutzdaten-IV ist null. In reinem Python
      nachgebaut und gegen zwei Klartext-Chiffrat-Paare verifiziert. Details in
      der Messung unten.
- [ ] **Rotiert das WLAN-Passwort zwischen zwei Verbindungen?** Entscheidet, ob
      die Entschlüsselung überhaupt gebraucht wird. Ungeprüft.

---

## Messungen

Neueste zuerst.

### 27.08.2026 (13:30–14:10: AZ-GTi Protokoll entschlüsselt) — UDP 11880, Synscan-Serial-Framing, `!3`=InvalidCharacter
Aufbau:     Pi per wlan0 mit Mount-AP „SynScan" (offen, Kanal 2, 55/100)
            verbunden; UDP-Fragen an 192.168.4.1:11880. Kamera-Stream für
            die Messfenster jeweils geparkt (Service stop), danach zurück.
Belegt:     - Mount-AP: SSID „SynScan", OFFEN (kein PSK), DHCP vergibt
              192.168.4.x (Pi wurde .2), Mount = 192.168.4.1, pingbar
              (RTT 4–210 ms, stark schwankend — WLAN-Chip schläft ein?).
            - **TCP komplett tot** (Portscan 1–11000: nichts offen; 11880
              activ refused). Alles läuft über **UDP 11880**.
            - **Framing: `:CMD<axis><HEX>\r` — nur CR, kein `#`, kein LF.**
              Nackte Befehle ohne `\r` oder mit `#` enden als `!3` =
              InvalidCharacter (Fehlerdic. aus pysynscan/synscan/comm.py).
            - Antworten: `=<HEX>\r` (ok) bzw. `!<n>\r` (Fehler 0=Unknown,
              1=Length, 2=MotorNotStopped, 3=InvalidChar, 4=NotInit …).
            - 24-Bit-Werte werden in 2-Zeichen-Gruppen gedreht übertragen
              („563412" statt „123456").
            - Gemessen (beide Achsen identisch): Version e=0336C5,
              Steps/Rev a=0x1FA400 (2.073.088), TimerFreq s=14.400 Hz,
              Highspeed-Schwelle j-Offset 0x800000, Status f1/f2=0x100/0x101
              (Achsen stehend), :F3 → `=` (initialisiert).
            - Befehlskarte (Referenz pysynscan motors.py, Verifikation —
              skyshutter implementiert eigenständig, stdlib-only):
              Lesend F3/e/a/s/j(Position−0x800000)/f(Status);
              Schreibend E(SetPos)/G(MotionMode+2)/I(Speed)/S/H(Target)/
              M(Break)/J(Start)/K(Stopp sanft)/L(HardStopp)/O(Switch).
Offen:      - **wlan0-Konflikt:** Ein Interface kann nur EIN Netz — Kamera-AP
              (192.168.0.x) ODER Mount-AP (192.168.4.x), nie beide. Für
              Streamen+Guiding gleichzeitig: Mount in Station Mode ins
              Heimnetz (App → Wi-Fi Setting → Station Mode) ODER zweiter
              USB-WLAN-Stick am Pi.
            - Bewegungsbefehle ungetestet (Schreibregel: nur nach OK).
            - :j1-Position im Detail noch nicht geloggt (erster Test lief,
              0x800000 = Nullposition).

### 27.08.2026 (12:35–12:39: Bilanz nach 3,5 h Dauerbetrieb) — Selbstheilung greift autonom; Magenta nicht wiedergekehrt; Watchdog v2 aktiv
Aufbau:     Watchdog-Log (/tmp/lv_watchdog.log, 30-s-Takt) + Service-Journal
            seit 09:26, /status-Sequenzvergleich t0/t8s.
Belegt:     - **3,5 h Magenta-frei** seit Wake 10:04 (340+ Messungen).
              Reine Zeitabhängigkeit damit geschwächt — Kollaps koppelte
              vermutlich an die Session-Churn-Situation des Morgens.
            - **WLAN-Flapping im 5–15-min-Takt** (Journal: 12:12, 12:25,
              12:30 … je 5× Fail) — und der Härtungs-Loop arbeitete jedes
              Mal autonom: 5 Fails → Wrapper → BLE-Re-Wake → Erholung.
              Kein manueller Eingriff nötig. Das ist der Beleg, dass das
              „stabile Tool"-Ziel auf Softwareseite jetzt getragen wird.
            - Sequenz zählt (1384→1450/8 s ≈ 8 fps), closed=false —
              std=63.17 konstant ist eine echt statische Szene, KEIN
              Stale-Frame (Verwechslungsgefahr dokumentiert).
            - Watchdog v2: prüft jetzt MAGENTA (std<1,0) UND STALE
              (Sequenz 2 Messungen eingefroren bei closed=false) — beide
              dokumentierten Versagensmodi abgedeckt. /status ist der
              zuverlässige Vitalindikator, nicht die Bildvarianz allein.
Offen:      Flapping-Ursache bleibt die physische −71-dBm-Funkstrecke —
              Software kann nur aufräumen, nicht verhindern.

### 27.08.2026 (09:20–09:30: Magenta-Kollaps eingekreist + Auto-Heal) — Kamera-Wake heilt, LV-Restart nicht; Schutz aktiv
Aufbau:     LV-Testskript (/tmp/lv_test.py) in frischer Session nach BLE-Wake:
            Frames via 0x9203 gezogen, vor/nach EndLiveView→StartLiveView.
            Danach Watchdog-Prozess (/tmp/lv_watchdog.py, System-python+cv2):
            pollt alle 30 s den Stream, restartet Service bei std<1.0.
Belegt:     - **Kamera-Display zeigt laut Thomas ein perfektes Bild** während
              der PTP-Stream magenta-kollabiert → zwei getrennte Pfade; der
              PTP-LV-Encoder/Buffer der Kamera ist der defekte Teil.
            - **Nach frischem BLE-Wake: gesund.** std=63.17 (reale Struktur),
              Kante bei Zeile 197 bleibt — das ist eine REALE Bildkante der
              Szene (kein Artefakt; Region [300:1100] hat jetzt Struktur).
            - **EndLiveView→3s→StartLiveView heilt NICHT** (B-Serie zeigte
              unverändert gesunde Werte — aber der Zustand war nach dem
              Wake schon gesund; der Zyklus bleibt damit ungetestet gegen
              einen AKUTEN Kollaps. Eindeutig: PTP-Reconnect heilt nicht,
              Kamera-Wake heilt).
            - Auto-Heal aktiv: star_tracker.py beendet sich mit Exit 2 +
              Service-Restart bei std<1.0 (alle 5. Frame geprüft); Watchdog
              auf dem Pi deckt auch Browser-Konsumenten ab.
Offen:      Wann genau kollabiert der LV-Buffer? (08:51 Service-Start war
              gesund laut journal — battery-Log —, 09:07 erste Magenta-
              Messung; Fenster also <16 min, Auslöser unbekannt: Zeit?
              Gegenlicht? WLAN-Flattern?) Watchdog-Log liefert das Muster.

### 27.08.2026 (09:05–09:15: „80 % roter Block") — Kamera liefert Frames mit synthetischem Magenta-Füllbereich; Transport/Server vollständig entlastet
Aufbau:     Pixel-Karten (48×24/12 Text-Downscale) + Varianz-Analyse gegen
            den laufenden MJPEG-Stream nach Nutzerbericht „roter Block".
Belegt:     - JPEG-Transport sauber: SOI+EOI intakt, ~57 kB, cv2 dekodiert
              vollständig; Kante liegt NICHT am JPEG-MCU-Raster.
            - Frames aktualisieren sich live (Sequence zählt, heller Keil
              wandert zwischen Proben) — kein eingefrorener Buffer.
            - **Das Bild selbst:** obere ~17 % (bis Zeile 197/1168) echte
              Szene (dunkler Bereich links, ausgebrannter heller Keil
              rechts = vermutlich Sonne), darunter 83 % **bitperfekt
              uniformes Magenta**: B=255/G=121/R=255, std=0.0 über die
              gesamte Region. Keine echte Fläche/Optik erzeugt std=0 —
              das ist synthetischer Füllbereich, den die Kamera selbst
              encodiert.
            - Nebelbefund: Bei toter Session serviert der MJPEG-Server der
              alten Clients das letzte Frame endlos weiter (zwei Proben
              byteidentisch, obwohl Sequence eingefroren). Für Tracker
              wichtig: /status abfragen statt blind zu vertrauen.
Offen:      Kamera-LCD-Check durch Thomas nötig: Zeigt das Display dieselbe
              Magenta-Fläche? Dann LV-Pipeline/WB-Kollaps der Kamera
              (Sonne im Bild?), sonst PTP-LV-Pfad. Gegenprobe möglich:
              Standfoto (shoot) durch Foto-Pipeline ziehen und vergleichen.

### 27.08.2026 (08:45–09:00: API Reste, Zoom Verhalten & BLE Stresstest)
Aufbau:     Test-Skript in `skyshutter-stream`-Lücke. Zoom (0x9016) mit Parametern getestet. Lese-Ops (0x90CC, 0x9006) getestet. BLE Stresstest (direkt nach Abbruch).
Belegt:     - **Lese-Ops (0x90CC Picture Control, 0x9006 Profiles):** Werfen BEIDE
              `OPERATION_NOT_SUPPORTED 0x2005`. Wie bei PTPIP-Info (0x90E0) geht
              die Kamera danach in den Straf-Zustand und schließt den Port
              (`Connection refused` für den Rest der Session). Die P1100
              unterstützt all diese Comfort-Features via PTP/IP nicht.
            - **Zoom (0x9016) Verhalten:** Der Parameter `steps` ist **kein
              linearer, relativer Abstand**, sondern erzeugt absolute
              Positions-Sprünge in einer internen Liste/Kurve.
              - `zoom(10)` ließ Brennweite von 3500 auf 5300 springen. Noch
                einmal `zoom(10)` ließ sie ZURÜCK auf 3500 springen!
              - `zoom(-1)` sprang von 3500 auf 10500.
              - `zoom(-2, -3, -4, -5)` fuhr iterativ auf 8600, 7300, 5300, 3500.
              - `zoom(-6)`: `INVALID_PARAMETER 0x201D` (ab hier greift die Grenze).
            - **BLE-Wakeup-Stress:** Wird der `remote-start.py` (LSS-Client)
              hart gekillt (SIGTERM) oder bricht bei schwachem WLAN ab,
              bleibt der GATT-State in BlueZ/Kamera unsauber. Ein sofort
              folgender Wakeup-Versuch wirft sofort den "Kamera sendet nicht /
              Unlikely Error". Ein sauberes `systemctl restart bluetooth`
              heilt das Pi-seitig sofort.
Folge:      - Das Kamera-Zoom-Verhalten via PTP/IP (0x9016) ist für feinfühlige
              Steuerung unbrauchbar (große, nicht-lineare Sprünge, 0x941E fehlt).
              Wir konzentrieren uns für das Tracking auf die Montierung (Mount).
              - **Nacht-Kollaps-Kette geklärt:** Schwaches WLAN -> Stream reißt
              -> Systemd killt/restartet Wrapper -> unsauberer BLE Abbruch ->
              BlueZ verschluckt sich -> Wakeup geht nicht mehr durch -> Pi-
              Stromversorgung (Brownout) gibt dem System den Rest.
              Lösung: Stärkere Stromversorgung + `Restart=always` in den
              Stream-Service einbauen, der VOR dem `remote-start.py` präventiv
              einmal `systemctl restart bluetooth` macht.
Aufbau:     Pi stürzte um 08:06 hart ab. Ursachenforschung per ssh nach Reboot.
Belegt:     - **Ursache Pi-Crash:** Chronische Unterspannung. `vcgencmd get_throttled`
              liefert `0x50000` (Unterspannung + Throttling in der Vergangenheit).
              Kernel-Log war voll mit `Undervoltage detected!` im Minutentakt.
              Die Kombination Pi + Mango + Akku-Ladung ist zu viel für das Netzteil/Kabel.
            - **BLE-Wakeup Recovery:** Kamera reagierte nach dem Neustart nicht auf
              Bluetooth-Handshake (Fehler: `UNLIKELY_ERROR 14` / `Not connected`).
              Ein `sudo systemctl restart bluetooth` auf dem Pi heilte den Pi-Stack,
              die Kamera antwortete danach sofort sauber auf BLE.
            - **PTPIP-Info 0x90E0:** Antwortet mit `OPERATION_NOT_SUPPORTED 0x2005`
              und **bricht die PTP-Session hart ab** (Folgebefehle erhalten
              `Connection refused`).
            - **LiveView Tages-Test:** Unmittelbar danach startete der Stream-Test
              bei Tageslicht erfolgreich. Saubere Frames (~57 kB) kamen sofort.
              Das beweist: Das nächtliche "0 Frames" Problem lag nicht am Netzwerk
              oder Code, sondern am Kamera-Zustand (vermutlich Objektiv eingefahren,
              Standby, oder Playback-Modus aktiv, was StartLiveView zwar mit OK
              quittiert, aber keine Frames liefert).

### 27.08.2026 (00:36–01:10: Nach dem Kamera-Neustat) — Session lebt, aber ZERO Frames zum Konsumenten; BLE-Wake kollabiert bei Schnellfolge
Aufbau:     Nach Thomass Kamera-Neustart: Ein Weckzyklus erfolgreich
            (00:37 join Versuch 13, battery 100 %), Stream „live view on".
            Danach 8+ unabhängige Konsumenten-Versuche gegen :8080
            (star_tracker synchron + gestückelt 6×18 s, Byte-Pulls,
            Debug-Doppel-Anlauf) über 35 min.
Belegt:     - **Session lebt, Frames nicht:** Keepalive-Polls kommen im
              25-s-Takt durch (Journal bis 01:00), Port hört — aber JEDE
              Konsumenten-Verbindung erhielt 0 Bytes/0 Frames. Zweimal
              endete die PTP-Frame-Versorgung mit „network error: timed
              out" (00:42:31). Verdacht: StartLiveView antwortet OK nach
              dem Neustart, der LV-Bildstrom läuft aber NICHT an (Kamera
              evtl. in Playback-/Unruhe-Zustand). Frame-Pull bleibt stumm,
              ohne Fehler zu werfen.
            - **BLE-Wake-Kollaps bei Schnellfolge:** nach ~6 Zyklen in
              25 min lieferte die Kamera keine Creds mehr (zweimal
              hintereinander ABBRUCH im Debug-Skript, wiederholt
              „Keine frischen Zugangsdaten" im Wrapper-Journal). Tagsüber
              waren Einzelschnellfolgen unkritisch; nächtliche Dauerfolge
              scheint ein anderes Regime. (Frage für tags: gibt es eine
              Pause-Untergrenze zwischen Weckzyklen?)
Folge:      E1-Nachtvalidierung heute NICHT geschafft — blockiert durch
              Kamera-Zustand, nicht durch Code (bei Tage liefen 59 kB-
              Frames stundenlang). Nächste Runde tagsüber: (1) Kamera am
              Gerät prüfen/LV manuell anstoßen, (2) Debug-Stream-Lauf
              (/tmp/dbgstream.sh auf dem Pi) mit Creds-Erfolg wiederholen
              — die -vv-Ausgabe zeigt genau, wo der Bildstrom hängt.

### 26.08.2026 (23:32–23:41: BLE-Wake tot) — Kamera sendet nicht mehr; E1 wartet auf physischen Check
Aufbau:     Wrapper-Loop im Minutentakt-Retry (Journal), remote-start-
            Log gelesen, bluetoothctl verifiziert.
Belegt:     - Seit 23:32 Dauerausfall: alle ~90 s Weckversuch, jeder
              scheitert mit „Keine frischen Zugangsdaten"; Stage-2-Fehler
              im Log: **„Kamera sendet nicht (Verbindungsmenü offen?
              Funk-Reset nötig?)"** — Kamera adver tisiert BLE nicht.
            - Pi-Seite sauber: Controller sichtbar, classic bond 7C:B8:
              DA:A6:4F:FE vorhanden.
            - Akku war 20:10/20:32 bei 100 % (Journal) — kein dokumentierter
              Tiefstand; Verdacht: Auto-Power-Off der Kamera selbst nach dem
              abendlichen Session-Hopping (Stream starb alle 1–2 min) oder
              Verbindungsmenü hängt.
Folge:      PHYSISCH bei Thomas: Kamera prüfen (ein/an, Akku, WLan-Menü),
            dann reicht der Wrapper — er retryt bis dahin automatisch.

### 26.08.2026 (21:50–22:15: Farb-/Dämmerungs-Serie am Live-Stream) — „rosa" ist Weißabgleich-Drift, kein Transportfehler; Sättigung löst sich langsam auf
Aufbau:     Pixelstatistik-Sonden gegen den laufenden MJPEG-Stream
            (HSV-Hue/Sat/Val getrennt je Bildhälfte, Grau-Histogramm),
            parallel 30-s-Kalibrier-Subläufe des star_tracker.
Belegt:     - **Nutzerbeobachtung „halb rosa" eingegrenzt:** Gemessen um
              22:05 ist der GESAMTE Frame gleichmäßig magenta (83 % aller
              Pixel im Hue-Band 240–360°, links=rechtsexakt gleiche Stats:
              sat=113, val=212 beidseits) — das ist AE/WB-Drift bei
              Dämmerlicht, KEIN Bildfehler und keine Seitenasymmetrie.
              Falls im Browser tatsächlich nur EINE Hälfte rosa wirkt:
              angebrochener Multipart-Puffer beim Client → hartes Neuladen;
              Server liefert vollständige Frames (JPEG-Carve prüft SOI+EOI).
            - Fürs Tracking irrelevant: Tracker arbeitet in IMREAD_GRAYSCALE,
              Farbcast fällt raus.
            - **Dämmerungsverlauf:** 20:40 median=255/max=255 (Vollsättigung)
              → 21:02 unverändert → ~22:05 median=176/max=226. Aber:
              Kalibrier-Subläufe um 22:07–22:10 fanden NULL Blobs — der
              Himmel hatte noch keinerlei Struktur über dem Threshold.
            - Stream-Flapping hält an (Tod alle 1–2 min, Heilung ~90 s);
              Watcher-Probes trafen mehrfach exactly die Lücken.
Folge:      E1 braucht echtes Dunkel (~22:30+) UND Bestätigung, dass die
              Kamera aufs Sternfeld zeigt (nur Thomas physisch prüfbar —
              Kamera-LCD!). WLAN-Flapping läuft als Dauerstörung weiter.

### 26.08.2026 (21:23–21:50: E5-Messblock Zoom/Props) — Multi-/Negativschritte bewiesen, 0x90CA existiert nicht, Brennweiten-Grenzen dekodiert
Aufbau:     Drei Session-Käufe über stop-stream→BLE-weck→join→Measure→
            restart (Skripte /tmp/e5_v*.sh auf dem Pi). Mehrere Neuanläufe:
            erstes Skript startete ohne Weckzyklus (AP tot, Lehre bestätigt),
            zweiter Weck scheiterte bei 2-s-Settle, Erfolge ab 12 s.
Belegt:     - **0x90CA (GET_VENDOR_PROP_CODES): OPERATION_NOT_SUPPORTED**
              (0x2005, doppelt bestätigt) — Kamera hat die Operation nicht.
              Offene Frage „Datenformat" damit erledigt: es gibt keins.
            - **Zoom-Multi-Schritt bewiesen:** `zoom(+10)` bewegte +3800
              Einheiten in 1,5 s (ein Befehl ≠ ein Schritt); `zoom(-13)`
              brachte exakt auf Baseline zurück → Negativrichtung bewiesen.
            - **Schrittparameter OBERGRENZE:** `zoom(-300)` →
              INVALID_PARAMETER 0x201D (abgelehnt, keine Bewegung). Grenze
              irgendwo zwischen 14 und 299 pro Befehl, ungemessen.
            - **Anschlag-Indiz:** Bei focal=3500 tat `zoom(+3)` NICHTS,
              während `zoom(+10)` danach sofort bewegte — Regime-Grenze
              (Verdacht Optical/Digital-Übergang), unbestätigt.
            - **Brennweiten-Grenzen dekodiert:** D0E3 (min)=0x00000960=
              2400, D0E4 (max)=0x000493E0=300000 — Zenti-mm, also exakt
              Spezifikation 24–3000 mm äq. Positionswerte von 0x5008
              (3500/7300) passen NICHT direkt auf diese Skala — Einheiten-
              frage offen (Digitalbereich? andere Einheit?). Vorherige
              Kalibrierungskurve unberührt (die nutzt EXIF-Echt-mm).
            - **Rohwerte unbekannter Properties:** D303=`01` (u8),
              D406=`01 0000`, D407=`01 000000` (u32=1). Deutung offen.
            - Betriebs-Lehren: BLE-Weck braucht ≥12 s Settle nach sauberem
              Session-Stopp (2 s scheiterte mit „device disconnected");
              Schnellfolge von Weckzyklen (--hold-300-Kette) kann Creds-
              Lieferung aussetzen lassen (ein ABBRUCH nach zwei Erfolgen).
Folge:      Kamera verbleibt auf focal=3500 (bewusst — Langbrennweite
              ist fürs Stern-Tracking kein Hindernis, Blobs werden größer).
              Zoom-Anschlag/Digitalgrenze bleibt nachzu messen, wenn Zeit;
              Einheitendiagnose von 0x5008 ebenfalls offen (Notiz A9 des
              Plans ergänzt).

### 26.08.2026 (20:40: Abendsonde — Dämmerung sättigt den LiveView komplett) — Autopilot für die Nachtvalidierung läuft
Aufbau:     Frame-Sonde gegen den laufenden Stream (System-python3, cv2),
            plus darkness-wait.sh auf dem Pi (nohup): alle 5 min Sonde,
            ab median<100 ohne 255er-Riesenblob automatisch ein 120-s-
            Kalibriellauf des star_tracker mit CSV nach /tmp/stars.csv.
Belegt:     - **Dämmerungs-LiveView clippt:** median=255, max=255, größter
              Blob 1.432.073 px (Vollframe) um 20:40. Gleiche Sättigungs-
              lehre wie die Tagszene — AE-Gain zieht auf, bis alles 255 ist.
              Stern-Tracking geht erst bei gefallenem Median (Dunkelheit).
            - MJPEG-Sonden-Lehre: Stream beginnt mit Multipart-Boundary;
              Sonden müssen zum JPEG-Start (\xff\xd8) schneiden, sonst
              liefert cv2.imdecode None.
            - Nacht-Autopilot: darkness-wait.sh (PID 68245) triggert den
              Kalibriellauf selbst; Report /tmp/darkness_report.txt.
            - Stream-FAILs im Watcher-Rhythmus sind WLAN-Tod-Fenster
              (normal, Wrapper heilt in 60–90 s) — kein Skriptfehler.
Folge:      Auswertung, wenn Report Kalibriellauf zeigt. Danach min/max-area
            aus /tmp/stars.csv kalibrieren (E1-Gate V1).

### 26.08.2026 (20:10: Akku + AP-Sofort-Tod) — BatteryLevel-Logging im Stream; Akku 100 %
Aufbau:     Einmal-Read von 0x5001 nach Session-Ende des Streams versucht →
            „No route to host" nach 3 s. Darauf `battery_level()` in
            NikonCamera + INFO-Log beim Session-Aufbau in `cmd_stream`
            (jede Wrapper-Session loggt jetzt gratis den Akkustand).
Belegt:     - **Kamera schaltet ihren AP SEKUNDEN nach Session-Ende ab**
              (nicht erst nach Auto-Off-Frist) — deshalb braucht jeder
              Wrapper-Neustart den vollen Weckzyklus; Read außerhalb des
              Client-Slots ist praktisch unmöglich.
            - **BatteryLevel 0x5001: 100 %** (Journal „INFO skyshutter:
              battery: 100 %") — Nachtlauf akkuseitig gesichert.
            - 176 Tests (neu: battery_level-Integrationstest).
Folge:      Akkustand ab jetzt über `journalctl -u skyshutter-stream |
            grep battery` — Anzeige am Kamera-Display entfällt.

### 26.08.2026 (Abend II: Keepalive-Messung, 19:27–19:41) — GetEvent-Poll verlängert Sessions, echte Todesursache ist schwaches WLAN (−71 dBm)
Aufbau:     `stream --keepalive-secs 25` (GetEvent 0x941C im Frame-Loop,
            gleicher Thread → kein Socket-Interleaving) + `-v` im Wrapper;
            12-min-Monitor auf dem Pi (journal tail + minütlicher Frame-Pull).
Belegt:     - Keepalive-Mechanismus sauber: Poll dt=25,0–26,2 s, Kamera
              antwortet jedes Mal OK (0 events).
            - Session-Längen MIT Poll: 181 s / ~45 s / 165 s / ~110 s
              (Baseline ohne Poll: 55 s). Verlängernd, aber keine Stabilität;
              HTTP-Verfügbarkeit 8/12 minütlicher Probes.
            - Zwei Todesarten: „Broken pipe" (RST) UND „timed out" — keine
              deterministische Timer-Konstanz.
            - **`iw station dump`: Signal −71 dBm, RX 18 MBit/s** (Direkt-
              verbund Pi↔Kamera-AP). Schwach — erklärt Streuung und Timeouts.
            - Korrektur zu Abend I: der „55 s Auto-Power-Off-Verdacht" war
              vermutlich schon WLAN-Tod, kein Timer.
Folge:      (1) Keepalive-Flag bleibt produktiv (harmlos, im Mittel
              verlängernd; 2 Unit-Tests, 175 grün). (2) Vor Nachtläufen
              PHYSISCH prüfen: Pi-Position/Antennenausrichtung relativ zur
              Kamera, Metall des Rigs weg vom Funkweg; notfalls besserer
              WLAN-Stick am Pi. (3) Kamera-Akkustand am Display checken
              (nach Tagessession; PTP-BatteryLevel nur ohne Stream lesbar,
              Client-Slot konfligiert — offene Kleinigkeit). (4) Der Wrapper
              heilt jeden Tod in ~60–90 s — für die Nachtvalidierung der
              Blob-Parameter reicht das; star_tracker überbrückt Lücken.

### 26.08.2026 (Nacht: ZMQ-Brücke bewiesen + PTP-Kapputt-Fund) — End-to-End Tracker→Loop läuft; Kamera kappt passive Sessions nach ~55 s
Aufbau:     star_tracker um `--zmq` (Publisher bind :5555, DetectionFrame-
            JSON exakt im Vorgängerformat) und `--selftest-publish`
            (synthetische Drift-Detektion, szenenunabhängig) erweitert.
            Telemetrie-Mitschnitt auf :5556 während des Publishens.
Belegt:     - **E2E-Schnittstellenbeweis:** 30 synthetische Frames auf
              :5555 → astro-loop empfängt und verarbeitet: 30/124
              Telemetrieframes mit target.valid=true, err_x_norm=0,8 und
              vel_x_norm=0,08/s korrekt aus der Drift berechnet; Mount
              bleibt connected+parked (keine Bewegung ohne Unpark —
              sicheres Design bestätigt). **Kette fertig:** Stream →
              star_tracker → ZMQ → Mount-Loop. Für Produktion fehlen nur
              Nacht-Blob-Parameter, FTDI-Kabel + Backend indi + Unpark.
            - **NEUER Betriebs-Befund:** Kamera kappt die PTP-Session
              nach ~55 s PASSIVEN Streamings (Journal: „Broken pipe",
              19:12:38 Start → 19:13:33 Tod). Heute Vormittag hielten
              aktive Zugriffe (Zoom/Download/Capture) die Session stunden-
              lang. Verdacht: Auto-Power-Off-Timer zählt Bedienung, nicht
              LV-Konsum. **Offen:** Keepalive-Messen — hält ein 30-s-
              GetEvent-Poll (0x941C) oder Property-Poll die Session wach?
              Evtl. auch Kamera-Menü „Auto-Abschaltung" verlängern.
            - Shell-Lehre: `cmd1 && cd X && nohup Y & Z` legt die GANZE
              Kette in den Hintergrund (Z läuft ohne cd) — absolute Pfade
              oder `;`-Trennung.
Folge:      Für Nachtläufe: Wrapper heilt den 55-s-Tod zwar, aber jeder
              Zyklus kostet einen Weckzyklus (~90 s). Keepalive-Messung
              VOR der Nachtvalidierung spart Frust.

### 26.08.2026 (Abend: Vorgängerprojekt gesichtet + Stern-Tracker gebaut) — astro-cv-tracker ist recycelbar; Track-Kette synthetisch bewiesen
Aufbau:     Sichtung `~/projekte_hardware/astro-cv-tracker` (lief auf DIESEM
            Pi), Bau `tools/cv/star_tracker.py` (System-python3), Smoke-
            Tests am Tag-Stream + Synthetik-Validierung der Track-Logik.
Belegt:     - **Vorgänger-Kontext:** Der R2140 war der Astro-CV-Tracker-Pi:
              Nikon P1100 per HDMI-Grabber, AZ-GTi per Lynx-Astro-FTDI-
              EQDIR (indi), Modus-A-Centroid (numpy-only), Mount-Loop mit
              ACK+Retry-Commands, boot-sicher paused, ZMQ-Detektionen auf
              tcp://127.0.0.1:5555 (Publisher bindet, JSON `DetectionFrame`).
              docs/MOUNT_CONTROL_SPEC.md dokumentiert alle Fallen (Port-
              konflikt, Auto-Chase, Slow-Joiner-Drops). **Integrationspfad:
              unser WiFi-Tap ersetzt den HDMI-Capture-Prozess; Mount-Loop
              bleibt unverändert.**
            - **Alte Units liefen noch:** astro-loop + astro-dash aktiv
              (Backend=mock — sicher, keine Bewegung); astro-capture
              crash-loopte (Grabber fehlt) → gestoppt (reversibel).
              Kein /dev/ttyUSB*: FTDI-Kabel des Mounts NICHT angeschlossen.
            - **star_tracker.py:** bg-relativer Threshold (bg+rel·(peak−bg),
              Kontrast-Gate gegen Schwarzbild — Rezept des Vorgängers),
              ≤254-Kappe (Sättigungslehre von heute), Flächenfilter
              [min,max], Top-N nach Intensitätsmasse, intensitätsgewichtete
              Subpixel-Centroide, Nearest-Neighbor-Assoziation mit px-Gate,
              CSV-Log + Per-Track-Statistik. Smoke am Tag-Stream: 0 Tracks
              ist KORREKT (Median=255 bei 85 % Sättigung → Kontrast-Gate
              greift; nachts bg≈0 → kein Gate). Decode avg 4,6 ms/Frame.
            - **Synthetik-Beweis der Kette:** 3 Punkte → 3 Blobs exakt an
              Soll-Position → 3 stabile Tracks über 4 Frames (kein Split,
              kein Riss); Subpixel-Statistik stimmt auf den Erwartungswert.
Folge:      Nachtvalidierung ist jetzt ein Einzeiler pro Lauf:
              `python3 tools/cv/star_tracker.py --duration 120 --out …`.
              Danach Kalibrierung von min/max-area an echten Sternen und
              die AZ-GTi-Integration (FTDI anstecken + Backend indi).

### 26.08.2026 (CV-Probe am laufenden Stream) — Pipeline-Rauschfloor 0,06 px; CPU-only reicht locker
Aufbau:     Zwei Probes gegen den laufenden Vollauflösungs-Stream
            (localhost:8080, System-python3 + cv2/numpy, KEIN Extra-
            Weckzyklus — HTTP-Tap only).
Belegt:     - **Durchsatz: 6,1 fps** (40 Frames in 6,6 s) über localhost
              HTTP — Leitung ist kein Flaschenhals.
            - **Kosten pro Frame:** JPEG-Decode ~5 ms im Dauerlauf
              (erste Frame 1.083 ms = cv2-Init), Threshold+CC+Momente
              wenige ms; gesamt 3–26 ms/Frame — weit unter dem 167-ms-
              Budget bei 6 fps. **Für Centroid-Tracking ist die CPU
              genug, die Hailo-NPU bleibt für spätere DNN-Aufgaben frei.**
            - **Erste Probe: null Blobs.** Ursache: Tagszene zu 85,5 %
              gesättigt (max_brightness 255 überall) → 99,5-Perzentil-
              Schwelle klemmt auf 255, `img > 255` findet nichts.
              Lehre: **adaptiver Threshold muss auf ≤254 gekappt werden**
              (in Probe 2 fixiert).
            - **Zweite Probe (Threshold ≤254): größtes Blob 1,43 Mpx**
              (= der gesättigte Himmel), Centroid über 40 Frames:
              **σ = 0,01/0,014 px, max. Drift 0,06 px.** Das ist der
              Rauschfloor der GESAMTEN Kette (Sensor-JPEG → PTP →
              HTTP → decode → Threshold → Momente) — zwei Größenordnungen
              unter jeder Guiding-Toleranz. Für kleine Stern-Blobs wird
              das Rauschen größer (kleinere Mittelungsbasis), aber der
              Pipeline-Anteil ist damit gemessen: vernachlässigbar.
Design-     **FINAL:** CV-Prozess = System-python3, localhost-MJPEG-Tap,
entscheid:  Perzentil-Threshold (≤254 kappen) + Flächenfilter für
              punktförmige Quellen, Momente für Subpixel-Centroid;
              Auslöser/Zoom später als Endpunkte am Stream-Dienst
              (Ein-Client-Limit). Aktor: AZ-GTi via FTDI. Offen bleibt
              NUR die Nachtvalidierung an echten Sternen (Execution,
              keine Design-Unbekannte) — inkl. Stern-Blob-Flächenbereich,
              der den Flächenfilter parametrisiert.

### 26.08.2026 (Nach dem Rig-Stromausfall) — bluetoothd-Race behoben; StartLiveView-Verbot ist jetzt retrybar
Aufbau:     Rückkehr des Rigs (ursprüngliche Ausfallursache war schlicht das
            nicht gesteckte WAN-Kabel; Adresse .143 blieb, DNAT ok). Der
            stream-Dienst kam allein hoch, scheiterte aber in drei Klassen,
            die hier auseinandergelegt sind.
Belegt:     - **Root cause A (Pi, kalter Boot):** `bluetoothctl list` LEER,
              obwohl `hciconfig -a` hci0 UP RUNNING zeigte (BCM43455).
              bluetoothd kam vor hci0 hoch und sieht danach dauerhaft
              nichts. Einmal `systemctl restart bluetooth` → Controller
              da, bleak-Scan findet die Kamera sofort. Der alte Zustand
              ließ JEDEN Weckversuch 90 s ins Leere laufen ("Keine frischen
              Zugangsdaten").
            - **Wrapper-Fix (Step 1a):** vor jedem Weckversuch prüft der
              Wrapper `bluetoothctl list`; leer → Neustart von bluetoothd
              + 3 s. Damit heilt sich das Rig das Race künftig selbst.
            - **Root cause B (Code):** WLAN-Join ok, aber `StartLiveView`
              antwortete DEVICE_BUSY [0x2019] (0x9201) und der CLI STARB
              SOFORT. Ursache: in `start_live_view()` wurde ein gesetztes
              Prohibit-Bit (0xD1A4) als Sofort-Fehler behandelt statt in
              den vorhandenen Retry-Loop zu laufen. Plausibel nach Hard-
              Kill mitten im FULL-Stream (kein StopLiveView gesehen):
              transient Bits wie IMAGE_IN_SDRAM / DURING_SHOOTING_COMMAND /
              TEMPERATURE_RISE. Fix: Verbot wird im Loop retryt (Grund je
              Versuch geloggt, Bit 31 maskiert wie die Vendor-App),
              Frames-fließen-Fallback bleibt; Tests: Lens-Retracted-Test
              auf attempts=1 verschnellert, neuer Unit-Test für transientes
              Verbot (173 grün).
            - **Aber:** danach advertisierte die Kamera NICHT mehr (bleak:
              kein P1100 in 10 s; remote-start: "Kamera sendet nicht,
              Verbindungsmenü offen? Funk-Reset nötig?"). Physischer
              Kamera-Neustat bzw. Funk-Reset ausständig -- Verdacht
              Akku nach einem Tag Dauer-FULL-Streaming oder Auto-Power-off
              nach den fehlgeschlagenen Sessions.
Folge:      Rig-Infrastruktur ist stromausfallresistent (A+B gefixt);
              CV-Probe (tools/hw/hw_cvprobe.py) wartet auf den laufenden
              Stream.

### 26.08.2026 (CV-Block Start: Pi-Inventar; Rig-Ausfall) — Hailo-8 & CV-Stack bestätigt; Probe durch Netz-Ausfall blockiert
Aufbau:     Read-only-Inventar auf dem R2140 (`lspci`, `dpkg`, venv/import-
            Proben, Last). Danach Vorbereitung der Centroid-Probe gegen
            127.0.0.1:8080 — **Rig wurde vorher unerreichbar** (s. u.).
Belegt:     - **Pi 5 (CM5-Basis) mit echtem Hailo-8** (lspci: Co-processor
              Hailo-8, rev 01; `/dev/hailo0`). HailoRT 4.20 + TAPPAS 3.31 +
              `python3-hailort` + rpicam-Postprocessing installiert;
              Last ~0,4 — NPU ungenutzt.
            - **CV-Interpreter = System-python3** (numpy, cv2, PIL, hailo
              importierbar); das skyshutter-venv hat KEINES davon (bleibt
              bewusst stdlib-only). CV läuft also als eigener Prozess
              unter System-python3.
            - Mitgelieferte HEF-Modelle (yolov5/6, SCRFD, ResNet) sind für
              Stern-Centroiden irrelevant — klassische CV (Threshold +
              Connected Components + Momente) ist Stufe 1; Hailo reserviert
              für spätere DNN-Aufgaben.
            - Vorgängerprojekt astro-cv-tracker lief auf diesem Pi
              (FINDINGS 23.08., Login-Trail) — Reste auf Platte nicht
              geprüft (Ausfall kam davor).
            - **Rig-Ausfall ab ~13:0x Uhr:** Mango 192.168.1.143 nicht
              mehr erreichbar (Gateway antwortet, ARP tot → „No route to
              host", Ports 2222/8080 zu). Physisch zu prüfen (Strom/
              Reboot). Stream-Dienst-Zustand danach unbekannt.
Design-     (1) **Eingang:** MJPEG-Tap am Stream-Dienst (HTTP localhost,
skizze:        bewiesen per Client-Probe) — CV als eigener Prozess, der
              stabile Dienst wird nicht angefasst. (2) **Steuerkanal:**
              Kamera erlaubt genau EINEN PTP-Client, den hält der Stream-
              Dienst → Steuerbefehle (Zoom/ISO/Auslöser) müssen als
              HTTP-Endpunkte AM Stream-Dienst entstehen, nicht als zweite
              PTP-Session. (3) **Detektion Stufe 1:** Perzentil-Threshold +
              größte Komponente + Momente → Centroid; Kennzahlen: Decode-ms,
              CPU-ms/Frame, Centroid-Std (Jitter-Bindung). (4) **Aktor
              später:** AZ-GTi-Mount via FTDI (bevorzugt; WLAN-PSK fehlt,
              bei Thomas) — Centroid-Drift → Slew. Nachtvalidierung
              ausständig (Tag-Szene misst nur Decode + Jitter).
Folge:      Probe-Skript steht lokal (`tools/hw/hw_cvprobe.py`, auch als
              Prüfartefakt) und muss nach Rig-Rückkehr auf den Pi
              (System-python3!) und einmal gegen den laufenden Stream.

### 26.08.2026 (LV-Auflösung + Stream-Umstellung) — Vollauflösung 1552×1162 verfügbar und live
Aufbau:     EINE Verbindung, ohne ControlMode: StartLiveView + 10×
            GET_LIVE_VIEW_IMG mit Timing; danach enter_remote_mode + 10×.
            Danach Wrapper-Umstellung und Client-Probe am MJPEG-Port.
Belegt:     - **FULL-Modus (ohne ControlMode 1): 1552×1162, ~60 kB/Frame,
              Abruf 0,10 s** (nach Warm-up; erste 0,2–0,4 s) ≈ 6–10 fps.
              REMOTE-Modus: 640×480, ~17,5 kB, 0,03 s, ~28 fps. Voll-
              auflösung = **5,8× die Pixel** des Remote-Modus.
            - **StartLiveView antwortet im FULL-Modus SOFORT OK** (0x2001,
              erster Versuch). Die DEVICE_BUSY/2019-Geschichte ist remote-
              modus-spezifisch — die „LV-Statuslüge" gilt nur nach
              ControlMode 1.
            - **Stream-Dienst umgestellt** (Wrapper: `--remote --fps 25` →
              `--fps 6` ohne --remote): Client-Probe liefert 12 Frames à
              ~59 kB (avg 59.177 B) = Vollauflösung live auf 8080.
              Fürs Astro-Framing/CV: Pixel > Framerate (6 fps reichen zum
              Nachführen); Remote-Modus bleibt per `--remote` verfügbar.
Folge:      CV-Pipeline bekommt 1552×1162 als Eingang. Bandbreite: 60 kB ×
              6 fps ≈ 360 kB/s — läuft auf dem Kamera-AP (gemessen inkl.
              Transfer in der 0,1-s-Abrufdauer).

### 26.08.2026 (Event-Kanal + 0x941E) — Event-Socket schweigt beim Capture; 941E verworfen
Aufbau:     Zwei Weckzyklen, je EINE Verbindung. Event-Test: poll_event vor
            und 5 s nach capture(). 941E: Parameterproben mit Foto+EXIF als
            Wirkungsnachweis (Anker = wide-Anschlag, EXIF 4,3 mm).
Belegt:     - **Event-Socket bleibt beim Capture stumm:** Handles 42→43
              (Bild geschrieben), aber NULL Pakete auf dem Event-Kanal
              (auch idle davor keins). Die Kamera nutzt den Event-Socket
              nur für Ping-Antworten — Ereignisse kommen über 0x941C-
              Polling (macht die App so, referenz.md). Unser Polling-Ansatz
              ist damit der richtige, kein Handlungsbedarf.
            - **0x941E (PowerZoomByFocalLength) verworfen:**
              `(10,)`→0x201D · `(10,0)`→0x201D · `(10,1)`→0x2006
              (ParameterNotSupported — 2. Parameter wird geprüft) ·
              `(1000,)`→OK, keine Bewegung · `(2400,)`→OK, keine Bewegung ·
              **`(60000,)`→OK, danach Connection reset by peer** — die
              Kamera kappt selbst die Session. Parametersemantik nicht
              erschließbar (mm/100-mm-äquiv-Hypothesen widerlegt oder
              wirkungslos), Befehl kann die Session töten. **Produktion:
              0x9016-Schritte + Kalibrierkurve.**
Folge:      Zwei Restpunkte der Validierungsliste geschlossen (negativ,
              aber entschieden). Offen bleiben nur 0x9520/21 (Auto-
              Übertragung) und die CV-Pipeline als nächster Block.

### 26.08.2026 (Auto-Recovery + Zoom-Kalibrierung) — Dienst heilt sich selbst; Schritte→mm-Kurve gemessen
Aufbau:     Recovery: WLAN-Radio am Pi aus (12:19:11) → Stream stirbt an
            TCP-Timeout; Radio an → Beobachtung über journalctl. Kalibrierung:
            EINE Verbindung; wide bis Anschlag (INVALID_PARAMETER zählt als
            solcher), dann Treppen à 8 Schritte tele mit Foto + EXIF je Stufe.
Belegt:     - **Auto-Recovery funktioniert:** Stream-Tod 12:19:31 („network
              error: timed out", sauberes Sterben nach 20 s — kein Hängen),
              Wrapper räumt auf (BLE-Hold killen, RPA-Zombies lösen), neuer
              Weckzyklus; nach Radio-an: Creds 12:19:44, Join 12:19:56,
              Stream 12:19:57. **26 s Recovery, beide 15740er-Sockets +
              8080 wieder da, ohne manuelles Zutun.** Wrapper-while-Schleife
              + systemd Restart=always greifen genau wie gebaut. Simuliert
              das „Kamera war aus"-Szenario von der Vornacht.
            - **Zoom-Kurve (focal via EXIF, M-Modus, remote mode):**
              0 Schritte = 4,3 mm (wide-Anschlag; INVALID_PARAMETER beim
              ersten wide = Anschlags-Signal) · 8 = 14,4 mm · 16 = 49,5 mm ·
              24 = 155,0 mm · 31 = Tele-Anschlag (0x201D, EXIF-Punkt fehlt —
              Kamera spec 3000 mm äquiv.).
            - **Schritte sind logarithmisch, nicht linear:** Brennweite ≈
              ×3,3 je 8 Schritte (~16 % Zuwachs/Schritt). Der frühere
              „~1,1 mm/Schritt" galt nur für den untersten Kurvenbereich.
              Fein-Framing unten, grob oben — für Astro-Framing vom
              wide-Anschlag aus zählen.
            - Ein 0x201D auf 0x9016 heißt „Anschlag erreicht" (wieder
              bestätigt: wide sofort, tele nach 31).
Folge:      Recovery-Offenpunkt ist geschlossen; Zoom fürs Framing
              kalibrierbar (0–31 Schritte, Anker = wide-Anschlag).
              Feinheiten offen: Kurve oberhalb 155 mm ohne EXIF-Stütze,
              Schrittwerte >1 ungetestet, 0x941E (Zielbrennweite) als
              elegantere Alternative ungetestet.

### 26.08.2026 (Zoom + LV-Diag) — 0x9016 bewegt das Objektiv: EXIF-Beweis
Aufbau:     Vier Weckzyklen, je EINE Verbindung. Zoom-Wirkung über EXIF
            FocalLength (TIFF 0x920A) frisch geschossener Fotos: 64 kB
            Kopf via GetPartialObject, TIFF-Walk ohne Pillow.
Belegt:     - **Zoom fährt real:** Baseline 4,3 mm (= wide-Anschlag) →
              6× ZOOM_CONTROL (0,1) → **10,7 mm** EXIF (DSCN0033→0035).
              ~1,1 mm Real-Brennweite pro tele-Schritt (erster Datenpunkt,
              Linearität ungemessen). Die App kann es, wir können es.
            - **Anschlag-Verhalten:** 2× wide am wide-Ende antwortet OK
              OHNE Bewegung (Kamera war schon bei 4,3 mm); ab dem 3. wide
              in Folge → INVALID_PARAMETER 0x201D. OK heißt also nicht
              "bewegt", nur "angenommen".
            - **focal-Property (0x5005) ist für Zoom-Feedback unbrauchbar:**
              konstant 3500 vor/während/nach der Fahrt (Sentinel oder
              gecacht). Zoom-Position steht nur im EXIF des Bildes — oder
              künftig evtl. über 0x941E abfragbar.
            - **LV-Status lügt im Remote-Modus:** StartLiveView antwortet
              dauerhaft DEVICE_BUSY 0x2019 und 0xD1A2 (lv_status) bleibt
              false — TROTZDEM liefert GetLiveViewImg (0x9203) fortlaufend
              0x2001-Frames (~25,7 kB, Remote-Größe). Genau so läuft der
              Stream-Dienst. Nie auf lv_status/StartLiveView-Erfolg gate'n.
            - **AF-Fläche (0x9205), AF-Drive (0x90C1) und GetEvent (0x941C,
              4 Byte 00000000 = kein Event) funktionieren im M-Modus.**
              AF-Drive beendet dabei den LV (danach A00B bei Frame-Holung).
            - 0x9203 nach AF-Drive → **0xA00B NotLiveView** (LV muss neu).
Folge:      `zoom()` funktioniert; für das Astro-Rig ist der optische Zoom
              fernsteuerbar. Nächste Verfeinerung: Schrittzahl→mm-Kurve
              vermessen (linear?), 0x941E als Positions-Alternative testen.
Fallen:     - Ein Messskript, das alles am Ende in EIN json sammelt, verliert
              ALLES bei einem Crash — Zeilen sofort ausgeben (flush=True).
            - capture() mitten in der Messung: neuestes JPG über max(handle)
              finden (DSCN-Nummern steigen mit Handle).

### 26.08.2026 (Write-Kampagne) — Property-Writes an der HW: ISO/Drive/EV gehen, Rest ist read-only (steht so im Desc)
Aufbau:     Drei Weckzyklen, je EIN Python-Prozess/EINE Verbindung
            (`/tmp/hw_writes.py`, `hw_writes2.py`, `hw_ev.py` auf dem Pi).
            OK von Thomas für die stille Sequenz mit Restore lag vor.
Belegt:     - **ISO (0x500F) schreiben funktioniert** — 2× gemessen
              (800 → Readback 800, Wire `2003` = 0x0320 LE; Restore auf 0
              = Auto klappt). ISO bleibt über Verbindungen hinweg stehen.
            - **Drive (0x5013) schreiben funktioniert** — burst(2) und
              zurück single(1); genau das macht die Hersteller-App in ihrer
              Startsequenz (referenz.md).
            - **EV (0x5010) schreiben funktioniert nur mit Leiterwert:**
              +0.666 → OK (Readback 0.666), +1.0 → OK, **+0.7 (700) →
              INCOMPLETE_TRANSFER 0x2007, reproduzierbar.** Die Kamera
              quittiert Nicht-Leiterwerte also NICHT mit INVALID_PARAMETER,
              sondern 0x2007. Leiter = ⅓-Stop-Raster (steps·1000/3:
              333, 666, 1000, …). `set_exposure_bias()` snapped jetzt
              darauf (mit symmetrischem Floor: −2 Steps → −666).
            - **Programm (0x500E), Verschluss (0xD100), Blende (0x5007)
              → ACCESS_DENIED 0x200F.** Kein Rätsel: **die PropertyDescs
              derselben Kamera deklarieren genau diese als read-only**
              (bundle props.json: access-Feld) — ISO/EV/Drive als
              read/write. Das Deny-Muster war in der eigenen Messung vom
              Vortag ablesbar.
            - **M-Modus hilft nicht:** Ein separater Messlauf bei physisch
              auf "M" gestelltem Einstellrad (Readback "MANUAL") zeigte:
              Die Descs für Verschluss/Blende/Programm bleiben stur auf
              read-only, und der Schreibversuch endet weiterhin mit 0x200F.
              Die Firmware blockiert die Belichtungssteuerung kategorisch.
            - FocusMode (0x500A) nicht beschrieben (Desc: read-only).
Folge:      **Write-Gate geschlossen:** Alle beschreibbaren Props sind
              gemessen und funktionieren; die read-only-Antwort der Kamera
              ist absolut. Manuelle Belichtungs-Steuerung ist für diese
              Kamera-Familie (P1100/P900) über WLAN nicht vorgesehen.
Fallen:     - ISO-Write überlebte einen Skript-Crash (falscher Methodenname
              `set_ev` → AttributeError NACH dem ersten Write) — Restore-
              Schritte IMMER am Ende laufen lassen, auch nach Fehlern;
              der zweite Lauf fand `before.iso = 800` vor.

### 26.08.2026 (Reader-Validierung + 0x9522) — Belichtungs-Getter an der HW: alle Formate bestätigt, 0x9522 vermessen
Aufbau:     Drei Weckzyklen (AP schloss nach jedem Disconnect); pro Zyklus
            EIN Python-Prozess, EINE PTP/IP-Verbindung ( `/tmp/hw_probe9522.py`
            auf dem Pi). Skripte per SSH-Heredoc, Auswertung mit SOF-Parser
            (strukturell, kein Pillow).
Belegt:     - **Alle typisierten Getter laufen an der HW:** Verschluss 1/100 s,
              ISO 0 (= Auto!), f/7.1, Programm 0x8010, Einzelbild, EV 0.0,
              Brennweite 3500 (mm equiv.). 34 Objekte auf Karte.
            - **0x9522-Größenmatrix (Parameterprobe 0–7, lesender GET):**
              Code 1 → 343.341 B OK; Code 3 → identische 343.341 B;
              Code 2 → NO_THUMBNAIL_PRESENT (0x2010); 0, 4–7 →
              INVALID_PARAMETER (0x201D).
            - **Beide liefernden Codes = 1440×1080 (SOF)** — die „8 MP"-
              These der App-Analyse ist an dieser Kamera **widerlegt**.
              CLI-Suffix ehrlich zu `_preview.jpg` geändert, Default
              size_code=1.
            - **Verschlussformat geklärt:** Value-Dataset 4 Bytes als
              **u32-Paar** — Zähler im hohen, Nenner im tiefen Halbwort.
              cur 0x000A03E8 → (10, 1000) = 1/100 s ✓; desc-default
              0x0001003C → (1, 60) = 1/60 s ✓ (zwei unabhängige Werte
              bestätigen die Halbwort-Zuordnung). Desc deklariert INT64,
              der Wert passt in 4. Setter schreibt jetzt `<I`-Paar; Bulb
              = 0xFFFFFFFF wie vorher.
            - **Programm-Enum erweitert:** Kamera stand in 0x8010 (erster
              Lauf: ValueError des alten Enums). 0x8010 ist Werkszustand
              → als NIKON_AUTO benannt (Name inferiert); 0x8016/0x8018/
              0x80D0/0x80D1 bleiben numerisch dokumentiert. CLI versteht
              `set program auto`.
Folge:      Getter-Formate sind **messbasiert** (u16/i16/u32-Paar); Simulator
              und Tests spiegeln alle gemessenen Breiten und die 0x9522-
              Matrix. Für die Write-Sequenz fehlt nur noch das OK.
Fallen:     - `pkill -f "remote-star[t].py"` im SELBEN SSH-Kommando wie der
              Neustart tötet die Shell wieder (auch ohne sichtbares
              `remote-start`-Literal: `nohup … tools/remote-start.py` matcht).
              Kill und Start strikt in getrennten SSH-Calls.
            - Erster Preview-Versuch mit size_code=4 → INVALID_PARAMETER:
              der Code stammte aus der App-Analyse, nicht aus einer Messung.

### 26.08.2026 (00:12) — Download-Pfad an der HW: 16-MP-Foto bytegenau auf dem Pi
Aufbau:     `skyshutter download --list` / `--last 1` (neue CLI, committet).
            `GetObjectHandles` (alle Stores) → `GetObjectInfo` (Name, Größe)
            → `GetPartialObject` in 1-MiB-Blöcken (so holt es auch die App;
            `GetObject` 0x1009 benutzt sie nie, referenz.md).
Belegt:     - **Listing:** echte Karteninventur — DSCN0027–0032.JPG +
              DSCN0031.MP4, Handles + Größen korrekt.
            - **Download DSCN0032.JPG: 3.593.725 B = exakt die ObjectInfo-
              Größe; JPEG-Marker ffd8…ffd9 intakt; Auflösung 4608×3456.**
            - Simulatortest: Capture erzeugt Objekte, Listing/Info/Download
              prüfen den ganzen Pfad ohne Hardware (166 Tests).
Folge:      **Der 4K-Workflow ist komplett und gemessen:** Stream (Framing)
              + `shoot` (16 MP auf SD) + `download` (bytegenau auf den Pi).
Fallen dieser Nacht (Ops-Bericht):
            - `pkill -f remote-start` in einem SSH-Kommando, das auch den
              Start enthält, tötet die eigene Shell (Muster matcht die
              cmdline des äußeren bash). Kill und Start trennen.
            - AP bleibt nach PTP-Disconnect für neue Joins zu, auch bei
              laufendem BLE-Hold (bekannt, wiedergesehen); nur der volle
              Zyklus (Hold killen → RPA-Cleanup → neu wecken) öffnet ihn
              wieder.

### 25.08.2026 (23:49) — Fernauslöser 9207 am laufenden Live View: Aufnahme + Stream koexistieren
Aufbau:     Testskript `tools/capture_test.py` (eigene PTP-Session; Stream-
            Dienst dafür gestoppt — Single-Client). ControlMode 1 →
            StartLiveView → 5 s Frames (Baseline) → `GetObjectHandles`
            (33 Objekte) → **`9207 InitiateCaptureRecInMedia` mit (0, 0)**
            (auslöseart 0, Ziel 0 = SD-Karte, wie die App) → Frame-Polling
            → 8 s Frames → `GetObjectHandles` erneut.
Belegt:     - **9207 antwortet OK (0x2001) und löst wirklich aus:**
              Objektzähler 33 → 34, ein neues Bild auf der Karte.
            - **Live View übersteht die Aufnahme komplett:** erster Frame
              wieder 0,9 s nach dem Auslöser; danach 17,1 fps (davor 13,6,
              medianer Frame-Abstand unverändert 53 ms). Kein EndLiveView,
              kein Re-Setup nötig.
            - **AP-Falle bestätigt:** Dienst-Stop (PTP-Disconnect) schloss
              den AP sofort; remote-start über Bond weckt ihn in ~10 s
              wieder (SSID nach 9 s wieder im Scan).
Folge:      Der Astro-Workflow ist freigegeben: Stream zum Framing (640×480
              @ ~15 fps) + Fernauslöser für volle 16-MP-Auflösung auf SD,
              gleichzeitig, ohne Session-Wechsel. Nächster Baustein:
              `GetPartialObject`-Download der Aufnahme fortsetzbar in
              1-MiB-Blöcken (Opcode-Inventar: 0x101B).

### 25.08.2026 (23:33–23:35) — Dauer-Stream im Fernmodus: 15,2 fps @ 640×480, 30 KB/Frame
Aufbau:     `skyshutter-stream.service` (systemd, Restart=always) mit dem
            überarbeiteten `tools/stream-wrapper.sh`: BLE-Weck → **Warten auf
            frische Creds (mtime-Check, bis 90 s)** → nmcli-Join (20×, Creds
            je Versuch neu gelesen) → `stream --remote --fps 25` → MJPEG
            :8080. Zombie-LE-Cleanup zwischen Zyklen (`bluetoothctl
            disconnect` auf die RPA, NIE auf den Classic-Bond).
Messung:    12 s HTTP-Client auf `/stream.mjpg` (der Pfad `/` liefert nur
            die HTML-Indexseite!): **183 Frames = 15,2 fps**, Frame-Abstand
            median 55 ms, Framegröße 30–32 KB, Auflösung **640×480**
            (SOF-Parser), Beweisframe `docs/proof/stream_remote_mode_640.jpg`.
Deutung:    55 ms Frame-Takt = Kamera-Selbsttakt (~18 fps); der Dienst bremst
            auf --fps 25, der echte Durchsatz liegt bei ~15–18 fps. Das ist
            der SnapBridge-App-Stream: 8× schneller als der 1,85-fps-Modus
            ohne ControlMode 1.
Fallen (alle heute gemessen und gefixt):
            1. **Stale-Creds-Falle:** Wrapper las die Creds-Datei 10 s nach
               Start — der BLE-Handshake dauert aber bis 60 s und rotiert das
               WLAN-Passwort je Session. Join mit altem Passwort scheitert
               garantiert. Fix: mtime-Warteschleife + Creds je Versuch neu
               lesen.
            2. **Zombie-LE nach kill -9:** Der Wrapper killte remote-start
               hart; der LE-Link blieb offen und die Kamera hörte auf zu
               advertisen (Sighting 220 s alt). Fix: sauber disconnecten +
               RPA removen pro Zyklus.
            3. **StartLiveView DEVICE_BUSY ~30 s:** Im Fernmodus antwortet
               StartLiveView nach dem Moduswechsel lange busy, obwohl Frames
               fließen — die App ignoriert das und pollt Bilder. Fix:
               `start_live_view` prüft nach Busy-Erschöpfung, ob ein Frame
               kommt, und fährt dann fort.

### 25.08.2026 (22:39–23:08) — DURCHBRUCH Nr. 2: ControlMode 1 (0x90C2) = App-Fernmodus, 36-KB-Frames @ ~27 fps
Aufbau:     Nach versehentlichem Bond-Verlust (bluetoothctl remove der
            Classic-Adresse) Re-Pairing über auto-pair.sh (Code am
            Kamera-Display von Thomas bestätigt, BOND_OK 22:38:43).
            Danach Sweep-Skript (`tools/probe_mode.py`) über PTP/IP: pro
            Wert eine 0x90C2-Transaktion mit Parameter (mode_val,), dann
            Frame-Timing-Messung.
Belegt:     - **0x90C2-Sweep:** Wert `0` → OK · Wert `1` → **OK (0x2001)** ·
              Werte `2–5` → 0x201D (Parameter nicht unterstützt). Wert `1`
              ist der einzige interessante — über USB wurde Wert `1` früher
              abgelehnt (libgphoto2), über WLAN wird er akzeptiert.
            - **Sichtbarer Effekt:** Nach Setzen von Modus 1 schaltet das
              Kamera-Display in einen speziellen Fernmodus („Connected"-UI,
              von Thomas beobachtet und bestätigt) — derselbe Zustand, den
              die SnapBridge-App herstellt.
            - **Frames im Fernmodus: ~36 KB statt ~540 KB, Abruf 35–55 ms.**
              Gemessene Serie (12 Frames): 51.6/42.8/34.9/34.1/35.4/40.1/
              54.7/36.9/35.8/36.6/36.8/54.9 ms — median 37 ms. ⇒ theoretisch
              ~27 fps möglich (Kamera-Ausgabetakt noch zu messen, ob sie
              selbst bei 30 fps neu rendert).
            - **StartLiveView-Verhalten im Moduswechsel:** direkt nach
              ControlMode 1 → DEVICE_BUSY (0x2019) oder A00B „nicht im Live
              View"; nach ~2–5 s Wartezeit liefern 0x9203-Frames normal.
              Der Moduswechsel braucht Übergangszeit.
            - **Modus-Antwort, wenn schon drin:** 0xA003 „Moduswechsel
              fehlgeschlagen" — idempotent behandeln: A003 = bereits im
              Fernmodus, kein Fehler.
            - **AP-Lebenszyklus-Falle:** Der WLAN-AP stirbt wenige Sekunden
              nach Trennung des PTP-Clients, AUCH wenn remote-start --hold
              die BLE-Verbindung hält. Zweiter Join-Versuch nach
              Client-Disconnect schlägt fehl (SSID unsichtbar). Für
              Messreihen: Verbindung halten oder 0x2005 neu schreiben.
Neue Falle: Classic-Bond löschen ist teuer (Re-Pairing braucht Mensch am
            Display). NIE `bluetoothctl remove` auf die Classic-Adresse
            7C:B8:DA:A6:4F:FE ausführen — nur RPAs entfernen.
Folge:      **Damit ist der „perfekte Stream" der App erklärt und
              reproduzierbar:** 0x90C2=1 vor StartLiveView setzen, ~3 s
              warten, dann 0x9203-Polling. Nächster Schritt: stream-Wrapper
              und CLI um den Moduswechsel erweitern, Bildgröße des
              Fernmodus-Frames vermessen (SOF-Parser), dann Dauerlauf.

### 25.08.2026 (21:37–21:45) — Frame-Rate-Ursache gemessen: Kamera-AP ist 802.11g @ 48 Mbps, Kamera sendet 6,6 Mbps
Aufbau:     Passiv auf dem laufenden Stream (kein zweiter Client, kein
            Dienst-Stop): Frame-Inter-Arrival per MJPEG-Socket, 12 s tcpdump
            auf wlan0/15740 (`/tmp/cap.pcap`, 10 MB), Burst-Analyse,
            `iw station dump`, Power-Save-A/B. Beweisframe:
            `docs/proof/stream_frame_2137.jpg`.
Belegt:     - **Frame-Abstände steady-state ~540 ms** (HTTP-Messung:
              [508, 547, 538, 544, 555, 518, 533, 567] ms) ⇒ ~1,85 fps.
            - **Frameformat: 1552×1168 Baseline-JPEG, ~540 KB** — fix, der
              `0x9202`-Opcode nimmt keine Parameter (Größe nicht verhandelbar).
            - **Kamera-Antwortlatenz ~40 ms** (tcpdump: Request→erste
              Datenpakete 11–58 ms) — die Kamera ist nicht träge.
            - **Funk: exzellent, aber alt.** Signal −49 dBm / 89 %, Ping-RTT
              ~2 ms — doch `iw station dump`: **tx/rx bitrate 48,0 MBit/s**,
              d.h. Legacy-802.11g-Modulation, keine n-Raten. Der P1100-AP ist
              eine g-Funkstrecke auf Kanal 6.
            - **Effektiver Durchsatz nur ~6,6 Mbps** (Burst-Rate der
              Kamera-Pakete). Rechnung: 540 KB = 4,3 Mbit ÷ 6,6 Mbps ≈ 1,5–1,9
              fps — deckungsgleich mit der Messung. Selbst bei Sättigung der
              g-Strecke wären es max ~4–5 fps.
            - **Power-Save off: wirkungslos** (A/B: Abstände danach 536–833 ms,
              median schlechter). Kamera taket ihre Aussendung selbst.
            - Kamera erlaubt genau **einen** PTP-Client: zweiter Connect ⇒
              `InitFail 0x00000002` (gemessen). Messungen am laufenden Stream
              nur passiv.
Folge:      Die 1,8 fps sind ein **Hardware-Deckel der Kamera** (g-AP +
              Aussende-Takt), nicht unseres Codes. Für Astro-Framing/
              Fokussieren reicht das; flüssiges Video gibt es nur über einen
              anderen Pfad (App-Streaming-Protokoll, kleinere Frames —
              offen, siehe referenz.md). Kein Hebel an link-localen
              Stellschrauben (Power-Save, Fenster, MTU) messbar.

### 25.08.2026 (20:57–21:08) — Dauer-Stream live: systemd-Dienst, Zombie-BLE-Falle, 1,75 fps gemessen
Aufbau:     `skyshutter-stream.service` (systemd, `Restart=always`) ruft
            `tools/stream-wrapper.sh`: Endlos-Loop aus BLE-Wake
            (`remote-start.py --register skyshutter --hold 300`, Hintergrund) →
            10 s warten → Creds aus `/tmp/skyshutter_creds.txt` →
            `nmcli device wifi connect` ×10 → `ping 192.168.0.10` →
            `python3 -m skyshutter.cli --host 192.168.0.10 stream --bind
            0.0.0.0 --http-port 8080`. Verifikation per `curl` auf dem Pi.
Belegt:     - **Blockade gefunden:** Kamera eingeschaltet, aber kein LE-
              Advertising sichtbar (`bluetoothctl scan`, 15 s, leer) UND
              `Connected: yes` für eine alte RPA (`6B:EE:7D:59:8A:08`) am
              Raspberry — ein hängender LE-Link blockierte die Kamera.
              Nikon-BLE ist Single-Connection: solange der Pi (Zombie-Link
              aus abgebrochenem `remote-start`-Lauf) verbunden blieb,
              advertisierte die Kamera nicht.
            - **Fix:** `bluetoothctl disconnect` + `remove` der RPA, danach
              `systemctl restart bluetooth`. Nächster Wrapper-Durchlauf:
              WLAN-Join 21:05:36 erfolgreich, Stream-Start 21:05:37.
            - **Stream gemessen:** `HTTP 200` auf `http://127.0.0.1:8080/`
              (243 B Index), `curl /stream.mjpg` (8 s) = 7.585.067 Bytes,
              14 × JPEG-Magic `FF D8 FF`, MJPEG-Boundary `--skyshutterframe`
              korrekt. ⇒ **≈1,75 fps @ ~540 KB/Frame**.
            - **fps-Default 15 ist Obergrenze, nicht Sollvorgabe:** die Rate
              limitiert die Kamera bzw. der `0x9201`-Round-Trip (~570 ms/
              Frame bei dieser Framegröße). Ursache einzeln zu messen
              (WLAN-Durchsatz vs. Kamera-Antwortzeit).
Neue Falle: **Abgebrochene `remote-start`-Läufe hinterlassen LE-Zombie-Links,
            die das Advertising der Kamera dauerhaft unterdrücken.** Der
            Wrapper killt seinen BLE-Prozess zwar am Loop-Ende, aber ein
            Crash zwischenzeitlich lässt den Link liegen. Vor jedem
            Debugging: `bluetoothctl devices Connected` prüfen und alte RPAs
            (`remove`) entsorgen.
Folge:      Dauerbetrieb steht. Browser-Zugriff vom PC dauerhaft ohne Tunnel:
            **`http://192.168.1.143:8080/`** (Mango-DNAT `rec-stream`,
            8080→192.168.3.178:8080, uci-persistent, 25.08. analog zur
            bestehenden `rec-ssh`-Regel angelegt). Mango-Zugang: WSL-Key
            liegt auf dem Mango (`ssh root@192.168.1.143`, WAN-SSH :22);
            das Mesh-Admin-PW `Seaweed_1234` gilt dort NICHT (gemessen,
            Permission denied).

### 24.08.2026 (21:28–21:46) — DURCHBRUCH: BOND_OK → Live View auf dem Raspberry
Aufbau:     Live-Session. Gated Sequenz (Handshake → Inquiry → bt-pair mit
            gefixtem Agent), danach `--join` + Liveview. Beweisbilder:
            `docs/proof/lv_00.jpg` … `lv_02.jpg`.
Belegt:     - **BOND_OK 21:28:57**: `CONFIRM passkey=53437 -> yes` (Agent),
              Thomas OK am Display; `Paired: yes`, `Bonded: yes`, Trusted
              gesetzt. Erster Classic-Bond am Raspberry — nach dem
              Agent1-Interface-Fix (Abend-Messung) lief die Kette beim
              ersten sauberen Versuch durch.
            - **0x2005 ← 01 accepted** (21:29:32, 21:32:45, 21:42:xx):
              Offene Frage Nr. 1 beantwortet — der WLAN-Start-Befehl wird
              mit vorhandenem Bond akzeptiert und der AP hochgefahren.
            - **AP-Verhalten**: Broadcastet nach ~80 s (vorher nur
              gerichtete Probes); SSID P1100_<serno>, Passwort <AP-PSK>
              (0x2004, heute stabil über Sessions), Kamera-IP **192.168.0.10**
              (Gateway-Annahme .1 falsch), Ping erreichbar.
            - **Join-Falle 1 — polkit**: `nmcli connection add/up` als User
              thomas → „Not authorized to control networking" (NM-Journal),
              jeder Join-Versuch lief still ins Leere. Fix:
              `/etc/polkit-1/rules.d/40-skyshutter-network.rules` (Gruppe
              netdev → NetworkManager-Actions YES). Danach Join in ~30 s.
            - **Join-Falle 2 — autoconnect**: Der temporäre Join erzeugt
              kein Profil; NM zieht wlan0 sofort zu ThoTiTiMe zurück →
              PTP/IP-Connect timeout. Fix: ThoTiTiMe `connection.autoconnect
              no` (Pi-seitig; ssh läuft über eth0/Mango-LAN, unkritisch).
            - **PTP/IP + Live View**: `liveview.py --host 192.168.0.10` —
              TCP 15740 offen (offene Frage Nr. 2 beantwortet),
              StartLiveView 0x9201, 3 JPEG-Frames à ~62 kB nach
              `/tmp/lv_0*.jpg`. Erste echte Kamerabilder über den
              Raspberry-Stack.
Ursachen-    Drei Nächte Agent1-Tippfehler (Registrierung ≠ Erreichbarkeit),
kette:       dann polkit, dann autoconnect — jede Falle einzeln gemessen
             und beseitigt; die Kamera kooperierte die ganze Zeit.

### 24.08.2026 (Abend) — Durchbruch am Agent, aber Burst verpasst: Skill-Review der Pairing-Kette
Aufbau:     Live-Session mit bluetoothd-Debug-Log + btmon. Assumption-Table-
            Review (diagnose-Skill) über alle Pairing-Scripts nach den
            Messungen der Abendrunde.
Belegt:     - **ROOT CAUSE Agent (behoben)**: bt-agent.py deklarierte seine
              Methoden unter `org.bluez.AgentManager1` statt `org.bluez.Agent1`.
              bluetoothd rief korrekt (`Calling Agent.RequestConfirmation …
              passkey=647189`), bekam `UnknownMethod` → wertete als Ablehnung
              → `AuthenticationFailed` in ~2 ms. Seit Fix: `CONFIRM
              passkey=320131 -> yes` im Journal, **Code 320131 erschien am
              Kamera-Display** (Thomas bestätigt; Abbruch versehentlich).
              Kamera sendet Codes zuverlässig — sie wartete auf unser OK.
            - **Nebenbefund**: `wf-panel-pi` (Raspberry-Desktop-Panel)
              registriert bei bluetoothd-Start einen Agenten `/btagent` als
              Default. NOT the root cause (unser Fehler reichte), aber ein
              Konkurrent um die Default-Agent-Rolle; unser Agent holt sie
              sich per RequestDefaultAgent zurück. Im Kopf behalten, falls
              Pairing wieder "sofort scheitert".
            - **Burst-Verhalten quantifiziert** (ble-watch-Journal): AD-Phase
              21:05:39–21:06:13 (34 s), Pause davor 1071 s, eine weitere
              287 s. 25-s-Wartefenster sind damit Münzwurf.
            - **hcitool inq legt KEINE BlueZ-Device-Objekte an** (rc=2 bei
              bt-pair zweimal) — nur bluez-Discovery (`bluetoothctl scan on`
              bzw. Adapter1.StartDiscovery) legt sie an.
            - **rssi=-127** ist der HCI-Marker „nicht verfügbar", kein
              Empfangswert; Identität der Sichtung via `name` Feld
              verifizierbar (P1100_<serno>).
Fixes:      bt-pair (ensure_device per BlueZ-Discovery, kein bredr-Filter im
            Fallback), remote-start (`--ad-wait` 300 s, entkoppelt vom
            Connect-Timeout), ble-watch (-127 → n/a, name in Status),
            auto-pair (400 s Wrapper). Alles deployed (Commits 2552123,
            Agent-Fix früher).
Offen:      Ein sauberer Lauf mit OK am Display — Kette ist beweisbar komplett
            (Handshake → Code am Display → Agent bestätigt).

### 24.08.2026 (Nacht III) — Kamera kooperiert: Paging beantwortet, dann 3× AuthenticationFailed
Aufbau:     Korrigierter Lauf-Block (Vorchecks + Handshake-Gate): Sichtung
            frisch (rssi −70, neue RPA 58:27:6F:4F:39:20), Handshake OK
            („registered as"), Inquiry-Treffer 7C:B8:DA:A6:4F:FE, danach
            3× `bt-pair.py` → je `org.bluez.Error.AuthenticationFailed`.
Belegt:     - **Die Kamera ist bereit und kooperiert**: Gegenüber 02:02
              (Page Timeout — keine Funkantwort) hat sie das Paging jetzt
              beantwortet und den SSP-Ablauf begonnen. Radiokette und
              Bereitschaft stehen; das Scheitern liegt NACH dem Verbindungsauf-
              bau, in der Authentifizierung.
            - `AuthenticationFailed` = eine der beiden Seiten hat die SSP-
              Bestätigung verweigert oder nicht rechtzeitig gegeben (gleiche
              Fehlerklasse wie der bluetoothctl-Auto-Decline, Nacht II).
            - **Zwei Zweige, durch das pair-agent-Journal trennbar:**
              (A) `CONFIRM passkey=…`-Zeilen während der Versuche → unsere
              Seite bestätigte automatisch; die Kamera-Seite lehnte ab oder
              OK wurde im ~25-s-Fenster nicht gedrückt → Display beobachten,
              ggf. Kamera-Geräteliste leeren.
              (B) KEINE CONFIRM-Zeilen → der Agent wurde nie gefragt:
              Agent-Registrierung verloren (bluetoothd-Restart räumt
              Registrierungen — BlueZ-Standardverhalten, hier noch nicht
              direkt gemessen) → `Pair()` lief agent-los → plausibel
              IO-Capability-Downgrade auf Just Works ohne Code am Display
              (analog der gemessenen NoInputNoOutput-Falle 23.08., für den
              Agent-los-Fall ungemessen) → Kamera lehnt ab.
            - bt-agent.py jetzt selbstheilend: Re-Register bei
              NameOwnerChanged(org.bluez) — wirkt nach dem späteren Deploy.
Offen:      Erschien beim Lauf ein Code am Kamera-Display? (Thomas) Und:
            wie lange dauerte jeder AuthenticationFailed — sofort (~2 s,
              spricht für B) oder nach ~25 s (spricht für A)? Alte
              bt-pair.py-Version druckt keine Zeitstempel.
Folgt:      Journal-Diagnose → Zweig-Fix → EIN gated Versuch mit
            Display-Beobachtung.

### 24.08.2026 (02:02) — Ohne vorangegangenen Handshake: 3× Page Timeout; Kamera advertised nicht
Aufbau:     Manueller Lauf-Block auf dem Raspberry (Inquiry-Listener parallel,
            `remote-start --register --wait-for-ad --no-establish`, danach
            3× `bt-pair.py` auf die Inquiry-Adresse), ausgeführt 02:02.
Belegt:     - **Die Kamera advertised nicht**: `--wait-for-ad` lief 25 s leer
              („keine Scanner-Sichtung im Zeitfenster -- Kamera sendet
              nicht"). Der LE-Handshake lief also NIE. Auch nach dem früheren
              Neustart keine Sichtung — konsistent mit Falle-5a-Nachwirkung.
            - **Trotzdem inquiry-sichtbar**: Der Listener traf
              7C:B8:DA:A6:4F:FE (Klasse 080620). Inquiry-Sichtbarkeit ≠
              Pairing-Bereitschaft — die Kamera antwortet auf Inquiry, aber
              nicht auf Paging.
            - **3× `org.bluez.Error.ConnectionAttemptFailed: Page Timeout`**:
              Die Kamera hat auf Paging nicht einmal auf Radiopbene
              geantwortet. Kein Agent-, D-Bus- oder bluetoothctl-Problem —
              die Anfrage kam schlicht nie an.
            - **Kontrast 01:11 vs. 02:02**: Der einzige Lauf, bei dem der
              Code erschien (01:11, `240078`), hatte einen erfolgreichen
              Handshake davor; 02:02 lief keiner → Page Timeout. Einziger
              struktureller Unterschied: der vorausgegangene LE-Handshake
              (Classic-Pairing-Fenster öffnet sich nur Sekunden danach,
              Messung 00:53). Konfound: 5a-Erschöpfung ~1 h nach den letzten
              von vielen Versuchen.
            - **Lücke im manuellen Lauf-Block**: Er paarte ohne Gate auf
              Handshake-Erfolg (auto-pair.sh hat das Gate: „registered as").
              Korrigierter Block mit Vorchecks und Gate übergeben; Hinweistext
              in remote-start.py von bluetoothctl auf bt-pair.py umgestellt.
Folgt:      6 h Funkruhe ab 02:02 (Falle 5a). Danach: Kamera-Geräteliste
            leeren (analog der Windows-Stale-Bond-Falle), Vorchecks (ble-watch
            aktiv + Sichtung frisch), EIN Lauf mit Gate. Frische Kamera MIT
            Handshake trennt die Konfounder.

### 24.08.2026 (Nacht II) — Kette funktioniert: Code erschien am Display; bt-pair.py jetzt 1:1 zur Windows-Referenz
Aufbau:     btmon-Mitschnitt während der Pairing-Versuche; danach Analyse der
            Windows-Referenz `tools/classic-pair.py` im Repo. Nachgetragen
            24.08. aus der Session um 01:11.
Belegt:     - **`bluetoothctl pair` sabotiert sich selbst**: es registriert
              einen eigenen Session-Agent, der bei geschlossenem stdin die
              SSP-Bestätigung in ~2 ms auto-ablehnt → AuthenticationFailed,
              unser DisplayYesNo-Agent wird nie gefragt. Direkter D-Bus-Aufruf
              `Device1.Pair()` umgeht das (→ `tools/bt-pair.py`).
            - **Classic-Connect + SSP-Handshake funktionieren** (btmon: Create
              Connection → Connect Complete, IO Capability Exchange
              DisplayYesNo). Um 01:11 erschien der Code **240078** am
              Kamera-Display — die Kette steht, die Kamera verweigerte danach
              (Erschöpfung, Falle 5a nach vielen Versuchen der Nacht).
            - **Die Windows-Referenz paart nie nur einmal**: 3 Versuche mit
              2 s Pause, danach Fallback auf die Windows-Standard-
              Routine (`classic-pair.py` 226–251). Unser bt-pair.py machte
              EINEN Pair()-Aufruf. Jetzt nachgezogen: Retry-Loop
              (Standard 3×, 2 s Pause) + Fallback (RemoveDevice → Inquiry →
              Pair auf frischem Objekt).
            - Kamera nach Neustart (Nutzer-Option 1): kein Advertising
              (Sichtung driftete 858 → 1086 s alt); Vorbereitung sauber
              (pair-agent + ble-watch aktiv, 0 gepairte Devices).
Folgt:      Funk-Reset des Raspberry-Stacks (hci0 down/up + bluetooth restart —
            das, was Windows' pair.sh vor jedem Lauf tut) und EIN sauberer
            Lauf mit der erweiterten bt-pair.py.

### 24.08.2026 (Nacht) — Passiver Bluetooth-Radar aktiv: Der Raspberry sendet jetzt NICHTS mehr
Aufbau:     `tools/bt-listen.py` als root-Systemdienst (`bt-listen.service`) auf dem
            Raspberry. Roh-HCI-Socket im exklusiven USER-Kanal, passiver LE-Scan
            (scan_type 0x00 — der Adapter sendet kein einziges Bit), alle
            Advertisements werden dekodiert (Adresse/Typ/RSSI/Name/UUIDs/
            Manufacturer-Data), Nikon-Payload mit LSS-Byte in
            `/tmp/camera_seen.json` gespiegelt (remote-start --wait-for-ad
            bleibt kompatibel). Volle Ereignisliste in `/tmp/bt-radar.jsonl`.
Belegt:     - **Der Kernel verweigert Scan-Kommandos über raw sockets, solange
              bluetoothd läuft** (`Set scan parameters failed: Operation not
              permitted` — hcitool UND eigener Code gleichermaßen). Der Weg
              vorbei ist der HCI-USER-Kanal.
            - **Der USER-Kanal bindet nur bei Adapter DOWN** (EBUSY bei UP —
              bewiesen mit nativem C-Probe-Programm gegen alle Vermutungen:
              bluetoothd/hciuart/bthelper stoppen reichte NICHT; erst
              `hciconfig hci0 down` direkt vor dem Bind). bt-listen macht das
              jetzt selbst.
            - **bt-listen.service + maskierte bluetooth/hciuart/bthelper**:
              udev/D-Bus ziehen bluetoothd sonst sofort wieder hoch und
              töten den Radar über die Conflict-Kette. Maskiert ist die
              maximale Sendefreiheit — nicht mal BlueZ-Hintergrundverkehr.
            - Erste 25 s Testlauf: 9 Events von 3 Geräten (u. a. ADV_IND
              public 7C:E9:… mit Manufacturer-Data — passiver Empfang
              funktioniert ohne jede Sendung).
Zweck:      Das 5a-Experiment von der anderen Seite: Falls UNSER Funkverkehr
            (Scan-Requests, Inquiry, Pairing-Bombardement) die Kamera in den
            Verweigerungsmodus treibt, sieht sie jetzt stundenlang absolute
            Funkstille vom Raspberry — bei voller Beobachtung: Burst-/Pausen-
            Muster, LSS-Byte-Wechsel (inkl. bit0-Mysterium), und ob die Kamera
            über Nacht überhaupt noch advertised.
Rückweg:    Für Pairing später: `sudo systemctl stop bt-listen &&
            sudo systemctl unmask bluetooth hciuart &&
            sudo systemctl start bluetooth pair-agent` (Agent bleibt als
            user-Service konfiguriert).

### 23.08.2026 (Nacht) — Raspberry: BLE-Handshake top, Classic-Bond von der Kamera blockiert (Falle 5a)
Aufbau:     Raspberry als Funk-Zentrale (siehe Abend-Messung). Ablauf nach
            pairing.md: BLE-Handshake → Inquiry → Pair mit BlueZ-Agent.
Belegt:     - **Der BLE-Pfad funktioniert am Raspberry exzellent:** mehrfach
              authentiziert + registriert in ~9 s pro Session (remote-start
              Stage 2-3), Establishment-Write akzeptiert. Die Portierung
              (BlueZ + nmcli) arbeitet.
            - **Die Kamera ist nach dem BLE-Handshake sofort im Classic-Inquiry
              sichtbar** — aber unter einer **pro Aufwach-Zyklus rotierenden
              Classic-Adresse** (beobachtet: 5D:8F:…, 58:4D:…, 7F:CA:…,
              4E:68:…; nie die alte Bond-Adresse 7C:B8:DA:4F:FE). Ein Bond auf
              eine fest einprogrammierte MAC ist damit wertlos — der Ablauf
              muss die aktuelle Inquiry-Adresse dynamisch greifen (tut
              fullpair2.sh).
            - **Pairing lehnt die Kamera auf LMP-Ebene ab:** AuthenticationFailed
              ohne dass der BlueZ-Agent je kontaktiert wurde (kein
              RequestConfirmation) — d.h. bevor irgendein Dialog entsteht.
              Ausnahme: der ERSTE Versuch nach Kamera-Neustart (23:30:50)
              blieb ~25 s offen (Dialog-Fenster!) und fiel dann — vermutlich
              fehlte die OK-Bestätigung am Kamera-Display. Alle Folgeversuche
              (auch nach Windows-seitigem forget): sofortige Ablehnung →
              **Falle 5a** (pairing.md: nach ~10 Versuchen verweigert die
              Kamera stundenlang; Abhilfe: Aus/Ein + Funkruhe).
            - Agent-Lektion: NoInputNoOutput lässt SSP auf Just Works
              fallen — für Nikons Numeric-Comparison braucht der Agent
              **DisplayYesNo** (pair_agent.py auf dem Raspberry,
              auto-confirmend). Korrekt registriert, kam aber nie zum Zug.
            - Windows-Bonds vollständig entfernt (classic-pair.py forget:
              UNPAIRED bestätigt) — Falle 4b ausgeräumt.
Offen:      EIN sauberer Versuch mit Thomas AM DISPLAY (Neustart der Kamera
            vorher, Code sofort bestätigen). Wenn der durch ist: Bond +
            trust, danach voller remote-start --join --hold und liveview auf
            dem Raspberry (alles vorbereitet: /tmp/fullpair2.sh, /tmp/
            pair_agent.py, remote-start.py portiert b84c904). Scheitert auch
            der: 6 h Funkruhe laut pairing.md-Beobachtung, nächster Anlauf
            morgen.

### 23.08.2026 (Abend) — Architektur-Wechsel: Raspberry wird Funk-Zentrale; Mango-Join scheitert an der Kamera, nicht am Timing
Art:        Infrastruktur-Umbau + Systemmessungen; Kamera nur indirekt (AP-Fenster
            aus vorheriger Runde).
Aufbau:     reComputer AI R2140-12 (Raspberry-Pi-CM5-Basis, Debian 12 Bookworm,
            4 Kerne/16 GB, Hailo-NPU, WLAN `wlan0` + BLE `hci0` an Bord) hängt am
            Mango-LAN (DHCP 192.168.3.178); Mango-WAN im Heimnetz (192.168.1.143).
            Zugang WSL→Mango:2222→Raspberry:22 (DNAT+SNAT, uci-Persistenz).
Gemessen:   - **Der Kamera-AP-Join schlägt am Mango reproduzierbar fehl — NICHT
              am Timing.** Daemon-Log: `prepare connect 'P1100(7c:b8:da:a6:b7:9b)',
              WPA2PSK/TKIPAES channel 6` → 27 s Versuch → `connect fail`. BSS
              gefunden, Signal −45, Key frisch entschlüsselt (<AP-PSK>, 2× über
              verschiedene Sessions stabil). Auch Windows joinete mit demselben
              Key nie erfolgreich. Verdacht: TKIP/AES-Cipher-Mix oder
              AP-seitiger Client-Filter. → Auf wpa_supplicant/nmcli am Raspberry
              verlagert; schlägt es dort auch fehl, ist es Kamera/Key, nicht der
              Client-Stack.
            - **`iwinfo ra0 scan` segfaultet** auf dem Mango (MTK-Treiber);
              `iwpriv ra0 set SiteSurvey=1` + `get_site_survey` funktioniert und
              sieht auch den hidden Kamera-AP (Windows-netsh sieht ihn nie ohne
              Profil — der AP beacont nur als Antwort auf gerichtete Probes).
            - **`ubus repeater connect` mit `remember:true` setzt
              `repeater.@main[0].disabled=0`** (Autostart scharf) und schreibt
              SSID/Key in uci — Finger weg von remember:true, wenn der Boot
              sauber bleiben soll. Zurückgesetzt auf disabled=1, P1100-Eintrag
              gelöscht.
            - **GL-Firewall-Dienst war defekt** (`/etc/firewall.vpn_server_policy.sh`,
              fw3-Rest von 2023, bricht unter fw4 bei toter Kette `VPN_SER_POLICY`
              ab → uci-Regeln wurden NIE geladen). Include deaktiviert; danach
              lädt `firewall restart` sauber und der DNAT-Zugang ist
              reboot-fest (uci `rec-ssh` Redirect).
            - **Hintergrund-Prozesse auf dem Mango überleben SSH-Session-Ende
              NICHT** (dropbear räumt die Prozessgruppe ab; nohup reicht nicht).
              Zuverlässig: eigener procd-Service (`/etc/init.d/*`). Für die
              neue Architektur irrelevant (kein Watcher mehr nötig).
            - Raspberry: bleak 3.0.2 + BlueZ arbeiten (7 Geräte im 8-s-Scan);
              `remote-start.py` läuft unter Linux (`--help` ok). Login-Trail:
              alter Pi aus astro-cv-tracker war `thomas`/`thomas`
              (docs/README.md:73) — derselbe Benutzer auf dem R2140.
Folge:      `remote-start.py` plattformneutral (Windows-Zweige erhalten),
            Commits c323f39. Rig-Zugang: zuhause `ssh recomputer`
            (192.168.1.143:2222), im Feld `ssh recomputer-field`
            (192.168.3.178 direkt, Laptop im Mango-AP). AZ-GTi: FTDI bevorzugt;
              WLAN-Fallback braucht SSID+PSK vom Mount-Display (nirgends
              dokumentiert) → bei Thomas abfragen.

### 23.08.2026 — Mango-Join fast fertig: AP sichtbar (ch6/WPA2), Passwort rotiert, letzte Meile = Timing
Aufbau:     `remote-start.py` (BLE→AP) + GL.iNet Mango als WISP-Client über GLs
            `ubus call repeater connect` (SSH root@192.168.1.143). PTP/IP dann aus
            WSL via `tools/liveview.py` über eine Portweiterleitung `15740→Kamera`.
Belegt:     - Der Mango **sieht** den Kamera-AP im Scan: `P1100_…`, **Kanal 6**,
              BSSID `7c:b8:da:a6:b7:9b` (Kamera-OUI), **WPA2PSK/TKIPAES**,
              Signal −45. Kein WPA3 → `proto=psk2` ist richtig.
            - **Das WLAN-Passwort rotiert pro Session** (einmal 8, einmal 9
              Zeichen). Ein externer Joiner MUSS das *aktuelle* per `lssec`
              entschlüsselte Passwort nehmen — `remote-start` schreibt es dafür
              nach `%TEMP%/skyshutter_creds.txt`. Ein gemerktes/altes Passwort
              scheitert (`repeater fail_type: not-found`/auth).
            - GLs `repeater connect {ssid,key,proto,remember}` ist der richtige
              Mechanismus (macht den AP+STA-Kanalwechsel auf dem Einzel-Radio);
              rohes uci/iwpriv nicht.
Offen (Timing, kein Wissen mehr): (a) der Windows-BLE-Stack trennt ~1/3 der
            Läufe mitten im Flow (`WinError -2147023673`); (b) der Kamera-AP bleibt
            nur zuverlässig oben, wenn ein Client ihn aktiv anprobt — mit
            `--join` (netsh klopft an) stand er 110 s stabil, ohne fällt er in
            Sekunden; (c) die Mango-Scan-/Connect-Latenz muss das AP-Fenster
            treffen. Alle drei sind Flakiness/Timing, keine offene Erkenntnis.
Rezept (vollständig, sobald eine saubere BLE-Session steht):
            ```
            1. remote-start.py --register skyshutter --join --hold 240
               (hält den AP wach, schreibt frische Creds)
            2. Creds aus %TEMP%/skyshutter_creds.txt lesen
            3. ssh Mango: ubus call repeater connect {ssid,key(frisch),psk2,remember}
            4. Kamera-IP = apcli0-Lease-Gateway; Portweiterleitung 15740→Kamera
            5. liveview.py --host 192.168.1.143   (PTP/IP, 0x9201/0x9428)
            ```

### 23.08.2026 — DURCHBRUCH: der korrigierte BLE-Flow fährt den Kamera-AP hoch
Kommando:   `remote-start.py --register skyshutter --join` (Windows-Python),
            Sequenz aus [REMOTE_SEQUENCE.md].
Ergebnis:   Der komplette korrigierte Flow läuft an der Hardware sauber durch:
            ```
            classic bond vorhanden
            BLE connected mtu=515
            CCCD 2008 (notify) + 2000 (indicate) subscribed
            Handshake 1-4 (Kamera antwortet per INDICATION auf 2000)
            0x2001 power = 03  VALID_WAKE  <-- bereit
            0x2004 gelesen, SSID+Passwort via lssec entschlüsselt
            0x2005 <- 01 (WiFi) accepted
            ```
            **Danach fährt die Kamera ihren WLAN-AP hoch** — vom Nutzer am
            Display bestätigt (WLAN-Symbol, BT stetig) und einmal auch als
            broadcastende SSID im `netsh wlan show networks` gesehen
            (`SSID 4 : P1100_…`, WPA2, kein WiFi-Direct).
Bedeutung:  **Das Kern-Gate der Session ist geknackt.** Die drei Korrekturen
            zusammen bringen es: (1) CCCDs (Indicate 2000 / Notify 2008), die wir
            nie gesetzt hatten; (2) richtige Wake-Deutung (`0x03`=VALID_WAKE,
            Kamera war immer bereit); (3) voller In-Session-Ablauf mit
            vorhandenem Classic-Bond. Kein RFCOMM, kein `0x2021`-Wecker.
Offen:      **Beitritt inkonsistent.** In einem Lauf war der AP die ganze Zeit
            scanbar+stabil, in einem anderen nie sichtbar → AP-Hochfahrt variiert
            zwischen Läufen (Ursache offen: BLE-Drop-Timing? Kanal/Band, das der
            2.-WLAN-Adapter nicht sieht?). `remote-start --join` tritt jetzt auf
            dem freien Adapter bei (Profil broadcastend), sobald der AP scanbar
            ist; PTP/IP-Live-View (`host:15740`, `0x9201`/`0x9428`) ist der
            nächste Schritt, sobald der Beitritt steht.
Folge:      `remote-start.py` ist der Weg. Nächstes: AP-Hochfahrt stabilisieren
            (BLE nach `0x2005` halten? Kanal prüfen) und PTP/IP anschließen.

[REMOTE_SEQUENCE.md]: REMOTE_SEQUENCE.md

### 23.08.2026 — Deep-Dive (12 Agenten): zwei Fehlschlüsse widerlegt, volle Sequenz belegt
Art:        Multi-Agenten-Analyse (btsnoop + APK, 6 Miner + Synthese + 3
            Verifizierer + Gap-Fill), plan `zesty-leaping-peacock`.
Ergebnis:   Volle Fernaufnahme-Startsequenz rekonstruiert → [REMOTE_SEQUENCE.md].
            **Zwei frühere Schlüsse dieser Session sind widerlegt:**
            1. **`0x2001=0x03` ist `VALID_WAKE`, nicht `INVALID_WAKE`.** Selbst
               verifiziert in `BlePowerControlData$Types.smali`: der 3.
               Konstruktor-Parameter (Feld `a`/`getByte`, = Wire-Wert) ist
               STOP=0, WAKE_WAIT=1, INVALID_WAKE=2, VALID_WAKE=3. Früher wurden
               die Java-**Ordinale** (1/2/3/4) als Wire-Werte gelesen → falsch.
               **Die Kamera war bei allen Tests bereit; „INVALID_WAKE-Gate" gab
               es nie.**
            2. **Kein RFCOMM/SPP-Datenkanal zur Kamera.** Die RFCOMM-Verbindung
               zu `5e8945b0…` ging an `…2d:4c` = **„Watch Ultra (T6WE)"**
               (Samsung, dev_class 28:07:04) — `5e8945b0` ist Samsung, nicht
               Nikon. Kamera = `…4f:fe`, „P1100_…", dev_class 08:06:20;
               sie macht nur einen klassischen **createBond** (SSP), keinen
               Datenkanal. `tools/rfcomm-connect.py` zielt falsch.
            Bestätigt/präzisiert: LE-Link **unverschlüsselt** (kein LE-Pairing);
            CCCDs **Indicate 2000 + Notify 2008** vor Auth; AUTH 17-B-Frames;
            NAME 32 B UTF-8; TIME 10 B LE; Establishment `0x01`=WiFi (bit0);
            WLAN = WiFi-Direct, Creds über `0x2004`; PTP/IP `host:15740`, Live
            View `0x9201` start / `0x9428` GetLiveViewImageEx / `0x9203` end.
Folge:      `ble-probe.py` POWER_TYPES auf Wire-Werte korrigiert. Neuer Client-
            Flow siehe Stand-Block. Verbleibende Lücken (AUTH-Werte, AP-SSID/PW,
            WiFi-Bring-up) nur an der Hardware bzw. per WLAN-Mitschnitt.

[REMOTE_SEQUENCE.md]: REMOTE_SEQUENCE.md

### 23.08.2026 — Kombinierter Test: LE-`pair()` vor dem Handshake trennt die Kamera (Timing zählt)
Kommando:   Kombiniertes Skript: BLE verbinden → Notify 2000/2008 → `pair()` →
            RFCOMM → `0x2001` → `0x2005`.
Ergebnis:   BLE verband, Notify ging, aber **`client.pair()` (LE) trennte die
            Verbindung sofort** („Not connected"). Ohne `pair()` verband es
            erneut, danach aber Connect-Timeouts — `pair()` hinterließ **zwei
            LE-Bonds `P1100` auf Windows**, die die folgenden Connects störten.
Nuance:     Das Handy **hat** im btsnoop BLE-Schlüssel für die Kamera (LE-Bond
            existiert). LE-Pairing ist also Teil des normalen Ablaufs — aber
            offenbar **zum richtigen Zeitpunkt** (nach dem App-Handshake), nicht
            davor/willkürlich. Ein erzwungenes `pair()` vor dem Handshake wird
            von der Kamera mit Trennung quittiert.
Folge:      `--like-app` ruft **kein** `pair()` mehr auf (nur noch Notify). Die
            Verschlüsselung/LE-Bindung muss an der richtigen Stelle im Ablauf
            passieren — noch zu bestimmen. Die kombinierte Orchestrierung
            (BLE-Notify + RFCOMM + `0x2005`) ist strukturell richtig; Blocker
            bleiben (a) die BLE-Connect-Zuverlässigkeit des Rigs und (b) das
            LE-Pair-Timing. Evtl. die doppelten `P1100`-LE-Bonds unter Windows
            entfernen, bevor es weitergeht.

### 23.08.2026 — RFCOMM-Richtung geklärt: ausgehender Client zu `5e8945b0…`; Dienst im Ruhezustand nicht angeboten
Quelle:     btsnoop (`btsock_rfc_connect`) + neues Werkzeug `rfcomm-connect.py`.
Fund:       Die App ist RFCOMM-**Client**: `btsock_rfc_connect: service_uuid:
            5e8945b0-9525-11e3-a5e2-0800200c9a66`. Unser `rfcomm-listen.py` hatte
            die Richtung falsch (wir lauschten). Neues `rfcomm-connect.py`
            verbindet ausgehend zu genau dieser UUID.
Hardware:   `rfcomm-connect.py` findet die gekoppelte Kamera
            (`P1100…`, Classic-Adresse `7c:b8:da:a6:4f:fe`), aber die
            **SDP-Abfrage nach `5e8945b0…` liefert im Ruhezustand keinen Dienst.**
            Die App verbindet ihn nur, wenn die Kamera zuvor über den BLE-Flow in
            den Remote-Zustand versetzt wurde.
Adress-     Der btsnoop-RFCOMM-Connect zielt auf `…2d:4c`, nicht `…4f:fe`.
Rätsel:     `2d:4c` ist im Handy-Log ein gebondetes Gerät **mit BLE-Schlüsseln**
            (die BLE-Identität der Kamera), `4f:fe` die klassische Bond-Adresse.
            Dual-Mode-Gerät mit getrennten BR/EDR- und LE-Adressen — noch nicht
            vollständig aufgelöst, welche RFCOMM trägt.
Konsequenz: RFCOMM lässt sich **nicht isoliert** testen — der SPP-Dienst
            erscheint erst nach der BLE-Vorbereitung. Nächster Test ist die
            **kombinierte Orchestrierung**: BLE-Auth (`--like-app`) → prüfen, ob
            danach `5e8945b0…` per SDP auftaucht → RFCOMM verbinden → `0x2005`.

### 23.08.2026 — Der eigentliche fehlende Teil: eine Bluetooth-CLASSIC-Verbindung (RFCOMM), nicht nur BLE
Quelle:     btsnoop der funktionierenden SnapBridge-Fernaufnahme + APK
            (`CameraConnectByBtcUseCase`, `ptpclient/`).
Fund:       SnapBridge nutzt **drei** Transporte, nicht einen:
            - **BLE** (LSS/GATT) für Steuerung/Setup,
            - **Bluetooth Classic / RFCOMM (SPP)** — im Mitschnitt belegt
              (`BTA_JV`, `rfcomm send_app_scn`, BR/EDR-ACL, `SET_CONNECTION_
              ENCRYPTION` auf klassischem Handle). `sppMaxDataLength` aus `0x2004`
              konfiguriert genau diese SPP-Verbindung; `snapbridge/ptpclient/`
              fährt **PTP über RFCOMM**.
            - **WLAN** für Live View (hohe Bandbreite).
            Beide Use Cases (`CameraConnectByBtcUseCase` J3, `CameraConnectByWiFi`
            Z3) brechen bei `INVALID_WAKE` mit `NOT_READY_CAMERA` ab.
Deutung:    **Unser gesamter WLAN-Start scheiterte, weil wir nur BLE sprechen.**
            Die Kamera bleibt `INVALID_WAKE`, solange keine klassische
            RFCOMM-Verbindung steht — und honoriert den `0x2005`-Write dann nicht
            (er wird zwar angenommen, aber ignoriert). Der Ablauf von SnapBridge:
            BLE verbinden+auth (mit Notifications) → **RFCOMM/Classic verbinden**
            (Kamera wird `VALID_WAKE`) → `0x2005` → AP → Live View über WLAN.
            Thomas' Beobachtung passt exakt: BLE bleibt verbunden (kein Timeout),
            WLAN jederzeit startbar — weil die BT-Verbindungen (BLE **und**
            Classic) dauerhaft stehen.
Konsequenz: `rfcomm-listen.py` war die falsche Richtung (wir warteten auf die
            Kamera). Richtig: **wir müssen uns zur RFCOMM/SPP-Verbindung der
            Kamera verbinden** (ausgehend), wie SnapBridge. Das ist neue
            Funktionalität neben dem BLE-Client.
Nächster    RFCOMM-Client bauen: nach BLE-Auth die klassische SPP-Verbindung zur
Test:       Kamera öffnen (Kanal/UUID aus dem Mitschnitt bzw. SDP), dann `0x2001`
            erneut lesen — Erwartung: `VALID_WAKE`. Dann `0x2005` → AP.

### 23.08.2026 — Echte SnapBridge-Sequenz mitgeschnitten: der `0x2021`-Wecker entfällt, es fehlen Notifications + Verschlüsselung
Kommando:   `adb bugreport` → `btsnoop`/Bluetooth-Stack-Log der **funktionierenden**
            SnapBridge-Fernaufnahme extrahiert (Android-Stack-Log,
            Sitzung 16:16–16:18). SnapBridge zeigt an dieser P1100 **echtes
            WLAN-Live-View** (von Thomas bestätigt).
Fund 1:     **`0x2020`/`0x2021` existieren auch für die App nicht.** Die von
            SnapBridge entdeckte LSS-Charakteristikliste ist identisch mit unserer
            (`2000–2009, 200b, 2080, 2082–2084, 2086, 2087` + Batterie) — keine
            FOR_CONTROL-Charakteristik. **Der `0x2021`-Wecker (RemoteControl) gilt
            nicht für dieses Modell** und ist damit widerlegt.
Fund 2:     Die echte Startsequenz pro Verbindung (Value-Handles → UUID):
            ```
            CCCD 0x2000  Notify EIN   (die App abonniert 2000)
            CCCD 0x2008  Notify EIN   (die App abonniert 2008)
            0x2000       Auth-Writes (×2 Stufen) — Kamera ANTWORTET per Notification
            0x2002       Client-Name
            0x2006       Current Time
            0x2005       Establishment 01  -> AP startet, WLAN-Symbol erscheint
            ```
Fund 3:     Vor dem Establishment fährt der Stack **`SET_CONNECTION_ENCRYPTION`**
            (`BTM_SetEncryption`, klassischer Link `classic_handle:0x0009`,
            `new_encr_key_256=true`) — der Link ist **verschlüsselt**.
Deutung:    Unsere `pairing --establish`-Versuche unterschieden sich in **zwei**
            Punkten von der App: (a) wir haben **nie Notifications auf 2000/2008
            aktiviert** und den Notification-Handshake der Kamera nie empfangen;
            (b) wir hatten den Link **nicht verschlüsselt**. Sehr wahrscheinlich
            bleibt die Kamera ohne diesen Ablauf in `INVALID_WAKE` und ignoriert
            den `0x2005`-Write. Kein Wecker-Byte, kein `0x2082/2083`, kein
            PowerControl-Write nötig — es ist der **Notification+Encryption-
            Ablauf**, der fehlt.
Nächster    In `ble-probe.py`/Client: vor dem Establishment CCCD auf 2000 **und**
Test:       2008 schreiben (Notify an), Auth fahren, auf die Kamera-Notification
            warten, Link verschlüsseln (`client.pair()` bzw. Classic-Encryption),
            dann `0x2005`. Ground Truth liegt vor — nur nachbauen.

### 23.08.2026 — Vollständige GATT-Liste: `0x2020`/`0x2021` fehlen — der Wecker ist nicht erreichbar
Kommando:   `client.pair()` + Service-Discovery auf stabiler Verbindung
            (handshake-frei), Kamera im Verbindungsmenü.
Ergebnis:   Charakteristiken der Kamera (LSS + Standard):
            ```
            2000 2001 2002 2003 2004 2005 2006 2007 2008 2009 200b
            2080 2082 2083 2084 2086 2087
            2a00 2a01 2a04 2a05 2a19 2a24 2a26 2a28 2a29 2aa6 2b29 2b2a
            ```
Deutung:    **`0x2020` (STATUS_FOR_CONTROL), `0x2021` (CONTROL_POINT_FOR_CONTROL)
            und `0x2081` (STATUS_FOR_CAPTURE) sind NICHT im GATT-Baum** — auch
            nach erzwungenem `client.pair()` nicht. Der in der App gefundene
            Wecker (`startRemoteControl` auf `0x2021`) lässt sich damit auf dieser
            Kamera/in diesem Zustand nicht senden. `0x2001` bleibt `INVALID_WAKE`.
            Nebenbefund: `0x2082`–`0x2087` **existieren** (bis auf `0x2085`) —
            das beantwortet die offene Frage, *dass* es sie gibt (Funktion noch
            offen). `0x200a` (CABLE_ATTACHMENT) fehlt ebenfalls.
Interpretation: Die Remote-Control-Charakteristiken erscheinen vermutlich erst,
            wenn die Kamera in einen **Remote-/Fernaufnahme-Modus** versetzt wird
            — der aber advertisiert nur im „Mit Smartgerät verbinden"-Menü, wo
            genau diese Charakteristiken fehlen. Henne-Ei. Offen bleibt, ob ein
            Kamera-Menüpunkt (Wi-Fi/Fernaufnahme statt BT-Kopplung) die Kamera in
            einen Zustand bringt, der `0x2020/0x2021` freilegt — oder ob dieser
            Pfad an diesem Modell so nicht vorgesehen ist. Ground-Truth-Test:
            schafft SnapBridge selbst WLAN-Live-View an dieser Kamera?

### 23.08.2026 — Wecker-Kandidat `0x2021` RemoteControl: Bytes bekannt, an der Hardware blockiert
Art:        Analyse + Hardware-Versuch (mehrere Läufe, Windows-Python).
Fund (Code): Der Wecker ist `V0.startRemoteControl` → schreibt auf
            **`0x2021` LSS_CONTROL_POINT_FOR_CONTROL** den Frame
            `05 00 11 00 01` (LE: len=5, Opcode 0x11, Reserve 0, Mode
            REMOTE_CONTROL=1; Serializer `J$a`). Direkt danach liest die App
            `0x2001` und erwartet `VALID_WAKE` („wake up and function effective").
            PowerControl selbst wird nie geschrieben — dies ist der Wake-Trigger.
Hardware:   Nicht bestätigt — zwei Wände:
            1. **`0x2021` ist ohne authentifizierte Sitzung nicht im GATT-Baum**
               („Characteristic … was not found"). Ein handshake-freier Connect
               ist zwar stabil (hielt 40 s), zeigt aber nur `0x2001` (= 03
               INVALID_WAKE), nicht `0x2021`.
            2. **Der Handshake bricht auf diesem Rig reproduzierbar bei Stufe 1
               ab** (`WinError -2147023673`, „vom Benutzer abgebrochen" = Kamera/
               Stack trennt), während eine *idle* Verbindung stabil bleibt. Es
               sind die schnellen Auth-Writes, die die Trennung auslösen.
            Nebenbefund: Bei jedem frischen Connect liest `0x2000` sofort einen
            **Stufe-4-Wert** (`0400…200102…`) zurück — die Kamera hält uns über
            Verbindungen hinweg für authentifiziert. Trotzdem erscheint `0x2021`
            nicht; wahrscheinlich braucht die Characteristic einen **LE-
            verschlüsselten** Link (bleak `client.pair()`), nicht nur den
            App-Handshake/Classic-Bond.
Nächster    Kandidaten, in Reihenfolge: (a) `client.pair()` vor der Discovery
Test:       erzwingen — LE-Verschlüsselung könnte `0x2021` sichtbar machen;
            (b) Handshake mit Pausen zwischen den Stufen (gegen den Abbruch);
            (c) prüfen, ob SnapBridge selbst an dieser Kamera WLAN-Live-View
            schafft (Ground Truth). Werkzeug `--wake` ist fertig und committet.

### 23.08.2026 — Wake-Flags stehen im Advertisement — verbindungsfrei lesbar, aktuell alle 0
Kommando:   `ble-probe.py adwake` (Scan, kein Connect), Kamera im
            Verbindungsmenü, „Bluetooth blinkt, kein WLAN-Zeichen" (Thomas).
Ergebnis:   ```
            company=0x0399 (Nikon)  data=01c96e6b00
              clientId = 01c96e6b, LSS-Ad-Info-Byte = 0x00
              -> quickWakeUp=0  autoTransfer=0  btcCoopWait=0
            ```
Deutung:    Der Wake-/Bereitschaftszustand steckt in einem Byte der
            Hersteller-Advertise-Daten (`BleScanData`: `hasQuickWakeUp` = Bit
            0x8, `isAutoTransfer` = 0x2, `isBtcCoopWait` = 0x10). **Lesbar per
            Scan, ohne Verbindung** — wichtig, weil der Windows-Stack zuverlässig
            nur einmal direkt nach einem Funk-Reset verbindet, aber immer scannt.
            Offset: das Byte liegt im smali bei Index 6 eines Arrays *mit*
            Company-ID; bleak liefert die Nutzlast *ohne* Company-ID, also
            `payload[4]`. Aktuell `0x00` — deckt sich mit `INVALID_WAKE` und dem
            reinen BT-Modus. Die Kamera advertisiert nur, solange „Mit Smartgerät
            verbinden" offen ist.
Offen:      Welcher Kamerazustand setzt eines dieser Bits / kippt `0x2001` auf
            `VALID_WAKE`? Und: schafft SnapBridge selbst an dieser Kamera WLAN-
            Live-View — wenn ja, ist der Zustand erreichbar und mit `adwake`
            sichtbar zu machen.

### 23.08.2026 — Das WLAN-Gate ist `0x2001 = INVALID_WAKE`, nicht ein BLE-Schritt
Kommando:   `ble-probe.py pairing --register skyshutter --establish 01 --hold 60
            --quick`, ausgeführt über das Windows-Python aus der WSL-Session,
            Kamera in Reichweite (RSSI −58), Kameramenü offen.
Aufbau:     Voller Vier-Stufen-Handshake in-session, dann die nachgebaute
            Hersteller-Vorbedingungskette (`0x2008` → `0x2001` → `0x2004` →
            `0x2005`).
Ergebnis:   ```
            -> authenticated; als 'skyshutter' registriert
            0x2008 before  1100  (ConnectionRequest = 0 = OFF)
              -> App würde nichts schreiben; übersprungen
            0x2001 power   03    INVALID_WAKE  (remote shooting UNAVAILABLE)
            0x2004 config  102B  Chiffrat (SSID+PW, als gekoppelter Client)
            0x2005 before  03
            0x2005 write   01    -> accepted
            danach Disconnect; netsh: kein P1100-Netz
            ```
Deutung:    **Zwei Kandidaten fallen weg, einer bleibt.**
            (1) `0x2008` stand schon auf OFF — die Kamera kommt in unserer
            Session nie in ConnectionRequest=ON, der Reset ist ein No-Op. **Nicht
            das Gate.**
            (2) Der `0x2005`-Write wird angenommen — Auth ist es also auch nicht.
            (3) **`0x2001 = INVALID_WAKE` ist das Gate.** Die App liest genau
            dieses Byte als „Remote Shooting Available"; bei `INVALID_WAKE`
            springt sie (`Z3` ~2437) auf `goto_282` und **überspringt den
            `0x2005`-Write ganz** — die App selbst würde im aktuellen
            Kamerazustand keinen AP starten.
            POWER_CONTROL wird auf dem WiFi-Pfad **nie geschrieben** (Code
            verifiziert). `VALID_WAKE` (0x04) ist damit ein **Kamera-Zustand**,
            kein Kommando, das uns fehlt — er hängt an Menü/Modus/Power der
            Kamera. Der Wake-Status steckt sogar im Advertisement
            (`hasQuickWakeUp`).
Offen:      Welcher Kamerazustand macht `0x2001` = `VALID_WAKE`? Test: `0x2001`
            wiederholt lesen, während die Kamera aus dem Menü auf den
            Aufnahme-Screen geht / Fernaufnahme im Kameramenü aktiviert wird.
Folge:      Gate neu benannt: nicht „fehlender BLE-Schritt", sondern
            „Kamera meldet INVALID_WAKE". `--hold`/`--establish`-Kette bleibt als
            Diagnosewerkzeug; nächster Lauf pollt `0x2001` gegen Kamera-Aktionen.

### 23.08.2026 — App-Analyse: nach `0x2005` kommt nichts mehr — der fehlende Schritt liegt davor
Art:        **Analyse, keine Hardware-Messung.** Quelle: dekompilierte
            Hersteller-App (baksmali, 11.721 Dateien), drei unabhängige Durchläufe.
Frage:      Was tut die App, um den AP zu starten, das unserem `0x01`→`0x2005`
            fehlt?
Ergebnis:   Der WLAN-Start der App ist `CameraConnectByWiFiUseCase` → `M0.e()`,
            und der schreibt **byte-für-byte unser `0x01`** auf `0x2005`. Es gibt
            **kein verstecktes „AP starten"-Kommando** und **nach `0x2005` keinen
            weiteren BLE-Zugriff** — die App scannt danach nur noch das WLAN
            (Android-seitig) und wartet auf keine „AP steht"-Notification.
            Der Unterschied liegt in der **Vorbedingungskette in derselben
            authentifizierten Sitzung**, in dieser Reihenfolge:
            ```
            0x2000  Auth-Handshake (bei connect)
            0x2008  ConnectionRequest -> OFF  (M0.a(), read-modify-write,
                    nur falls gerade ON; Zeit/Standort-Nibble bleiben)
            0x2001  POWER_CONTROL lesen (Gate; INVALID_WAKE = keine Fernaufnahme)
            0x2004  Config lesen (SSID/PW)
            0x2005  <- 01
            ```
            Wire-Werte `0x2008`-ConnectionRequest: OFF=0, ON=1 (aus der Enum
            verifiziert; Agent-Erstlesung „OFF=1/ON=2" war der Ordinal, nicht der
            Wire-Wert). Vorbehalt: der ungekoppelte `0x2008`-Lesewert stand schon
            auf OFF — ob **unsere** Sitzung die Kamera je in ON bringt, ist offen.
Folge:      `ble-probe.py --establish` spielt jetzt die volle Kette und meldet
            `0x2008`/`0x2001`-Zustand; neues Flag `--no-connreq-reset` für den
            A/B-Test. Nächster Hardware-Lauf misst, ob der AP damit erscheint.

### 23.08.2026 — WLAN-Auslöser an der Hardware: `0x01` auf `0x2005` startet den AP nicht
Kommando:   `ble-probe.py pairing --device … --nonce … --establish 01`, als
            gekoppelter Client, zweimal — einmal auch mit vorherigem Lesen von
            `0x2004` wie die Hersteller-App.
Aufbau:     Kamera frisch gekoppelt (Bond `PAIRED` um 11:50), Kameramenü offen.
Ergebnis:   ```
            0x2004 config  102B  03 + Chiffrat + 03ef010000
              flags 0x03: WLAN-Block ja, BT-Block ja
              SSID-Feld     (32 B Chiffrat, nicht mehr null)
              Passwort-Feld (64 B Chiffrat)
            0x2005 before  03
            0x2005 write   01   -> accepted
            0x2005 after   03
            ```
            `netsh wlan show networks` danach: **kein `P1100`-Netz.** Zweimal
            gemessen, mit und ohne vorheriges `0x2004`-Lesen, einmal mit 60 s
            gehaltener BLE-Verbindung. Der Access Point erscheint nicht.

            **`0x01` auf `0x2005` ist notwendig, aber nicht hinreichend.** Die
            Erwartung aus dem Herstellercode ist an der Hardware widerlegt —
            irgendein Schritt fehlt noch. Kandidaten, ungeprüft: die App hält
            die Verbindung dauerhaft und tut noch etwas anderes; oder ein
            weiterer Schreibzugriff (`0x2001` POWER_CONTROL, `0x2008`) gehört
            dazu; oder der AP braucht eine STA-/AP-Moduswahl, die wir nicht
            gesetzt haben.

            **Wichtiger Nebengewinn:** Als *gekoppelter* Client liefert `0x2004`
            das Chiffrat von SSID und Passwort — ungekoppelt (Messung 22.08.)
            waren beide Felder null. Das belegt: Die Kamera gibt die
            Zugangsdaten nur an berechtigte Clients heraus, und liefert damit
            das Klartext-Chiffrat-Paar für die Krypto-Analyse (unten).
Folge:      Widerlegt-Eintrag zu `0x2005` bleibt bestehen und wird präzisiert:
            der Schreibzugriff wird angenommen, startet den AP aber nicht allein.
            `ble-probe.py` bekam `--give-up` (Zeitlimit) und `--hold`.

### 23.08.2026 — LsSec geknackt: WLAN-Zugangsdaten in reinem Python entschlüsselbar
Kommando:   Disassemblat von `LsSec1stStage`/`Stage3rd`/`GenerateKey`/`transform`
            (capstone, ARM64), Bibliothek zusätzlich per ctypes als Orakel
            ausgeführt, beides gegen zwei Klartext-Chiffrat-Paare geprüft.
Aufbau:     Werkzeugbank, kein Kamerazugriff. Die native `.so` läuft auf dem
            aarch64-WSL über ein winziges `libc.so`-Shim (acht bionic-Symbole).
Ergebnis:   **Beide Paare entschlüsseln korrekt — SSID und Passwort im
            Klartext.** Verifiziert über die Original-Bibliothek *und* einen
            unabhängigen reinen Python-Nachbau; beide liefern denselben
            Sitzungsschlüssel.

            **Der Fehler aller früheren Versuche:** In die Ableitung gehen die
            **Zeitstempel** der Handshake-Nachrichten ein, nicht die
            device/nonce-Felder. Das war die ganze Zeit die falsche Annahme.

            Die vollständige, verifizierte Kette (alle Blowfish-Wörter
            big-endian):

            1. **Feste Transform** = Blowfish, Schlüssel `ffffaa5511223300`
               (identisch mit dem Handshake), CBC, IV `L=0x01020304
               R=0x05060708`. Der Schlüsselplan lässt sich zur Laufzeit aus dem
               Schlüssel rechnen — keine `.so` nötig.
            2. **fieldA** (8 B) = `[0x01] ‖ cam_ts[1:4] ‖ our_ts[0:4]` —
               Kamera-Zeitstempel (Stufe 2) und eigener Zeitstempel (Stufe 1),
               erstes Byte auf `0x01` gesetzt.
            3. **Sitzungsschlüssel** = **letzter** CBC-Block (CBC-MAC) der
               festen Transform über `stage4Payload ‖ deviceID ‖ fieldA`.
               `stage4Payload` = die 8-Byte-Nutzlast aus Stufe 4, `deviceID` =
               die 8 Byte, die der Client in Stufe 1 sendet.
            4. **Entschlüsselung** = Blowfish-CBC mit dem Sitzungsschlüssel und
               **IV = 0** (aus dem Kontext gedumpt; der IV ist schlicht null —
               deshalb war er nie „ableitbar"). SSID = erste 32 Byte, Passwort =
               nächste 64 Byte von `0x2004`, je nullterminiert.

            **Zwei Wege, beide funktionieren:** der reine Python-Nachbau
            (`bf.py`, passt zur stdlib-Philosophie) und die Bibliothek als
            ctypes-Orakel (nützlich als Referenz und zum Kalibrieren).
Folge:      Die WLAN-Zugangsdaten lassen sich aus dem BLE-Chiffrat berechnen —
            **für jede Kopplung, auch bei rotierendem Passwort.** Damit ist der
            volle automatische WLAN-Zugang in Reichweite. Nächster Schritt:
            sauberes `src/skyshutter/lssec.py` mit eigenem Blowfish (stdlib-only)
            und synthetischem Testvektor (keine echten Gerätedaten im Repo).
            Arbeitsstand in `/tmp/lssec`, nicht im Repo (enthält Klartext-Paare).

### 23.08.2026 — LsSec-Verschlüsselung: Struktur analysiert (Vorstufe zum Knacken)
Kommando:   Statische Analyse von `libLsSec-jni.so` (ARM64) mit capstone,
            plus Abgleich gegen zwei Klartext-Chiffrat-Paare aus `0x2004`.
Aufbau:     Kein Kamerazugriff nötig — Werkzeugbank.
Ergebnis:   Der Algorithmus ist **vollständig verstanden und in Python
            nachgebaut** (`/tmp/lssec`, nicht im Repo — arbeitet mit Chiffrat):

            - **Blowfish**, Tabellen bitgenau die Standard-Pi-Init.
            - **Feste Transform:** Blowfish mit Schlüssel `ffffaa5511223300`
              (derselbe wie der Handshake — der eingebackene Schlüsselplan ab
              `.rodata 0x2e28` ist bitgenau `key-schedule` dieses Schlüssels),
              CBC, IV `L=0x04030201 R=0x08070605` (byteweise der
              Handshake-Startzustand).
            - **Sitzungsschlüssel** = letzter CBC-Block (CBC-MAC) über 24 Byte
              `arg1 ‖ arg2 ‖ fieldA`, alle Wörter big-endian.
            - `arg1` = Stufe-4-Nutzlast (die „interne Seriennummer").
            - `arg2` = die beim Pairing gespeicherte Client-DeviceID (8 Byte),
              genau das, was der Client in Stufe 1 sendet.
            - **Nutzdaten:** Blowfish-CBC mit dem Sitzungsschlüssel, IV aus dem
              Kontext, big-endian.

            **Warum der Nachbau trotzdem nicht rechnet:** Zwei Werte —
            `fieldA` (= `ctx[0:8]`) und der Nutzdaten-IV (= `ctx+0x10`) —
            werden **rein nativ in `Stage1st`/`Stage3rd` berechnet** und stehen
            nicht in den BLE-Nachrichten. Über 1.900 Kombinationen aus allen
            geloggten Handshake-Werten (beide Endianness, beide Modi) treffen
            das Klartext-Chiffrat-Paar nicht. Damit ist belegt: `fieldA` ist ein
            tieferer nativer Zwischenwert, nicht aus dem Mitschnitt ableitbar.
Folge:      Drei Wege zum vollen Nachbau bleiben, alle mit Aufwand:
            (1) `libLsSec-jni.so` als Orakel ausführen — scheitert bisher an
            bionic-Symbolversionierung (`version LIBC`) auf glibc;
            (2) `Stage3rd`/`GenerateKey` vollständig disassemblieren;
            (3) den persistierten `LssContextData` (Feld `d`=40 B mit IV,
            `e`+`f` = expandierter Blowfish-Schlüssel) zur Laufzeit dumpen.
            **Vorher zu klären:** ob das Passwort überhaupt rotiert — sonst ist
            der ganze Weg für den Betrieb unnötig.

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
                      Kennung: device=DDDDDDDD nonce=NNNNNNNN (geschwärzt)
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
| 26.08.2026 | 0x9522 liefert mit size_code 4 ein „8-MP-Preview" (App-Analyse) | Parameterprobe 0–7 an der HW (26.08., Messungen oben): 4 → INVALID_PARAMETER 0x201D. Liefern tun nur 1 und 3 — beide dasselbe **1440×1080**-JPEG (343.341 B, SOF-geprüft). |
| 26.08.2026 | Verschluss 0xD100 reist als 8-Byte-Bruch (Zähler, Nenner) wie das Desc-INT64 nahelegt | Value-Dataset an der HW ist 4 Bytes: u32-Paar, Zähler hoch / Nenner tief. cur 0x000A03E8 → 10/1000 = 1/100 s, desc-def 0x0001003C → 1/60 s — beide nur unter dieser Zuordnung sinnvoll. |
| 22.08.2026 | Der HCI-Snoop-Schalter in den Entwickleroptionen liefert auf diesem Handy einen brauchbaren Mitschnitt | Aufzeichnung war aktiv (`dumpsys bluetooth_manager` → `sSnoopLogSettingAtEnable = FULL`), der Bugreport enthält 310 btsnoop-Dateien unter `FS/data/misc/bluetooth/logs/bthci/CsLog_*/BT_HCI_*.cfa` — **alle exakt 16 Byte, also nur Header ohne ein einziges Paket.** Der Hersteller filtert über `INIT_gd_hal_snoop_logger_filtering=true`. Beide Wege, das abzuschalten, sind ohne Root gesperrt: `device_config put` scheitert mit `SecurityException: must add flag to the allowlist`, `setprop persist.bluetooth.btsnoopenable` mit `Failed to set property`. |
| 23.08.2026 | `0x01` auf `0x2005` startet den AP **allein** | Als vollständig gekoppelter Client zweimal geschrieben (einmal mit vorherigem `0x2004`-Lesen wie die App, einmal mit 60 s gehaltener Verbindung). Schreibzugriff jedes Mal `accepted`, aber kein `P1100`-Netz im `netsh`-Scan. `0x01` ist notwendig (steht so im Herstellercode), aber nicht hinreichend — es fehlt ein weiterer Schritt. Details in der Messung vom 23.08. |
| 22.08.2026 | ~~`01` auf `0x2005` bewirkt gar nichts~~ **Teil-Widerlegung, am 23.08. präzisiert.** | Damals gedeutet als „bewirkt nichts, Wert bleibt `03`". Richtig ist: `03` ist der Bitfeld-Lesewert („WLAN+BT aktiv"), keine Statusmeldung über Wirkungslosigkeit. Der Schreibzugriff wird angenommen. Dass damals nichts geschah, lag auch an fehlender Kopplung (`0x2004` lieferte leere Daten). Aber: Auch **mit** Kopplung startet `0x01` den AP nicht allein (23.08.). |
