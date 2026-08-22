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
| **Offenes Gate** | Antwortet die P1100 im Fernsteuerungsmodus auf TCP 15740? |
| **Fehlende Messung** | Ausgabe von `skyshutter probe` im Kamera-WLAN |
| **Blockiert durch** | Hardware-Zugang (nur Thomas) |
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
- [ ] Welche IP hat die Kamera als AP tatsächlich? (Kandidaten: `192.168.1.1`,
      `192.168.0.10` — beide aus fremden Coolpix-Setups belegt)
- [ ] WPA3-SAE bestätigt? (Herstellerangabe, ungeprüft — entscheidet, ob
      Monitor-Mode als Messmethode überhaupt taugt)
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
| — | — | — |
