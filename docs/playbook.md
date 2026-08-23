# Playbook — wie ich (Claude) den Plan umsetze

[plan.md](plan.md) sagt *was* passiert. Dieses Dokument sagt, *wie ich arbeite*,
damit jede Session an derselben Stelle weitermacht — auch wenn mein Kontext
zwischendurch weg ist.

Grundannahme: **Mein Gedächtnis endet mit der Session, Thomas' Messungen nicht.**
Jede Messung, die nicht in [FINDINGS.md](FINDINGS.md), in einem Test oder im
Simulator gelandet ist, ist verloren. Genau deshalb ist der Kern-Loop unten so
strikt.

## 1. Session-Start-Ritual

Immer, bevor irgendetwas anderes passiert:

```bash
git log --oneline -5 && git status --short
python -m pytest -q && ruff check .
sed -n '1,45p' docs/FINDINGS.md      # Stand-Block: wo stehen wir wirklich?
```

Wer neu dazukommt, liest stattdessen [einfuehrung.md](einfuehrung.md) — worum
es überhaupt geht — und danach [referenz.md](referenz.md), was die Kamera kann.

Dazu MEMEX-Recall zu „skyshutter P1100" (Memories #17934 Recherche, #17935
Projektstand). Dann in einem Satz sagen: **welche Phase, welches offene Gate,
welche Messung fehlt.** Erst danach arbeiten.

Wenn FINDINGS.md und mein Eindruck aus dem Chat auseinandergehen, gewinnt
FINDINGS.md — der Chat kann eine alte Session sein.

## 2. Der Kern-Loop

Jede Runde besteht aus fünf Schritten. Kein Schritt darf entfallen, auch nicht
„weil es nur eine Kleinigkeit ist".

1. **Messung entgegennehmen** — Thomas pastet Text oder legt eine Datei ab.
2. **Auswerten** — klassifizieren (Tabelle in Abschnitt 3), parsen, verstehen.
3. **Festschreiben** — Ergebnis in `FINDINGS.md`, plus bei Protokollwissen in
   `protokoll.md`. Mit Datum und dem Kommando, das es erzeugt hat.
4. **Verankern** — ein Test, der die Messung festnagelt, und der Simulator wird
   an die Realität angeglichen. **Kein Messwert ohne Test.** Ein Simulator, der
   die echte Kamera nicht abbildet, ist ab dem Moment eine Lüge, in dem wir es
   besser wissen.
5. **Ausliefern** — Code anpassen, `pytest` + `ruff` grün, committen, pushen,
   und die nächste Runde als fertigen Kommandoblock formulieren.

Der Loop ist bewusst so gebaut, dass ein Sessionabbruch nach Schritt 3 nichts
kostet außer Zeit.

## 3. Eingangs-Typen und was ich damit mache

| Was ankommt | Was ich tue | Was daraus entsteht |
|---|---|---|
| `skyshutter probe`-Ausgabe | Gate-Tabelle aus plan.md Phase 1 anwenden | Entscheidung: Phase 2, Phase 5 oder Phase 1b |
| `skyshutter info`-Text | Opcode- und Property-Liste extrahieren | Tabelle in protokoll.md, Simulator-Opcodeliste ersetzt, Code auf reale Fähigkeiten zugeschnitten |
| `deviceinfo.bin` | Byteweise parsen, auch wenn der Parser vorher scheiterte | Fix in `ptp.py` + Regressionstest mit genau diesen Bytes |
| `frame.bin` | Header-Länge bis `FF D8 FF`, JPEG-Grenzen, Auflösung | Konstante + Test in `test_nikon.py`, Simulator-Frame angeglichen |
| `.pcap` | Mit eigenem Decoder zerlegen (Abschnitt 8) | Opcode-Sequenz, die SnapBridge benutzt |
| `btsnoop_hci.log` | GATT-Verkehr gegen nsg abgleichen | BLE-Handshake in Python |
| Traceback | **Zuerst im Simulator reproduzieren**, dann fixen | Test, der ohne Fix rot ist |
| „geht nicht" ohne Details | Nachfragen — aber nur die drei Fragen aus Abschnitt 5 | — |

## 4. Entscheidungsregeln, wenn die Realität widerspricht

* **`InitFail` beim Handshake** → nicht wiederholt anklopfen. Kameras sperren
  aufdringliche Clients zeitweise. Stattdessen: Phase 5 (BLE-Pairing) vorziehen.
* **Opcode antwortet `OPERATION_NOT_SUPPORTED`** → aus dem Codepfad entfernen,
  nicht „für später" stehen lassen. Spekulative Opcodes im Code sind die Quelle
  von Fehlern, die erst nachts um drei auffallen.
* **`DEVICE_BUSY`** → das ist kein Fehler, sondern das normale Signal „noch nicht
  fertig". `wait_until_ready()` davor, nicht Retry-Schleife drumherum.
* **Unbekannter Datenblock** → nicht raten. Eine **Differenzmessung** anfordern
  (Abschnitt 6). Semantik aus zwei Zuständen ableiten schlägt jede Vermutung.
* **Messung widerspricht protokoll.md** → die Messung gewinnt, das Dokument wird
  korrigiert, und der alte Stand bleibt als „widerlegt am TT.MM." stehen. Wir
  müssen wissen, was wir schon ausgeschlossen haben.

## 5. Wie ich Messungen anfordere

Regeln für jeden Kommandoblock, den ich Thomas gebe:

* **Höchstens drei Kommandos**, als ein Block zum Kopieren, ohne Platzhalter, die
  er ersetzen muss.
* **Jedes Kommando mit einem Satz**: was ich daraus lerne. Ein Kommando, dessen
  Ergebnis nichts entscheidet, wird nicht gestellt.
* **Eine Runde beantwortet mehrere Fragen.** Sein Aufwand pro Runde ist der
  teure Teil, nicht meiner.
* **Fehlerfall mitliefern**: „wenn stattdessen X kommt, dann stattdessen Y".
* **Niemals** nach etwas fragen, das ich aus vorhandenen Daten selbst ableiten
  könnte.

Wenn eine Meldung ohne Kontext kommt, frage ich genau das: (1) welches Kommando
wörtlich, (2) vollständige Ausgabe inklusive Fehlertext, (3) in welchem Netz und
in welchem Kameramodus.

## 6. Die Differenzmessung — Methode für Phase 4

Der Trick, mit dem aus anonymen Property-Codes benannte Funktionen werden:

1. Alle Properties auslesen → `before.json`
2. Thomas verstellt **genau eine Sache** an der Kamera (Zoom auf Maximum)
3. Erneut auslesen → `after.json`
4. Diff → der geänderte Code *ist* der Zoom.

Ein Durchgang pro Funktion, jeder dauert bei ihm 30 Sekunden. Das ist der Grund,
warum `skyshutter props --dump/--diff` weit oben auf der Backlog-Liste steht: Es
verwandelt Phase 4 aus Raten in Ablesen.

## 7. Sicherheitsregeln an echter Hardware

An der Kamera hängt echtes Gerät mit echten Bildern drauf. Deshalb, ausnahmslos:

* **Nur Opcodes, die in `operations_supported` stehen.** Kein blindes Durchfahren
  eines Bereichs wie `0x9000`–`0x92FF`. In Nikons Vendor-Bereich liegen
  Lösch-, Format- und Firmware-Operationen; ein Sweep kann Bilder vernichten oder
  die Kamera in einen Zustand bringen, aus dem nur der Service hilft.
* **Lesende Operationen** (`Get*`, `DeviceReady`, Ereignisabfrage) laufen ohne
  Rückfrage.
* **Schreibende Operationen** (`SetDevicePropValue`, alles mit `Delete`,
  `Format`, `Firmware` im Namen) nur nach ausdrücklichem OK von Thomas, mit
  Ansage, was passieren soll.
  **`0x100F FormatStore` steht in der gemessenen Operationsliste dieser
  Kamera** — es anzufassen wäre unumkehrbar.
* **Vor jeder Schreib-Runde**: Speicherkarte leer oder gesichert, Akku voll.
* Kein Dauerlauf ohne Abbruchbedingung. Live View heizt die Kamera.

## 8. Was ich zwischen den Runden ohne Hardware baue

Damit eine Session nie leerläuft, während Thomas nicht am Gerät ist.

**Erledigt** (Stand 23.08.2026):

- **BLE-Werkzeuge** — `ble-probe.py`, `classic-pair.py`, `ble-proxy.py`,
  `ble-camera-sim.py`. Übersicht in [../tools/README.md](../tools/README.md).
- **Zweiter Transport** — `ptpusb.py`, PTP über Kabel, gleiche Schnittstelle
  wie PTP/IP.
- **Analyse der Hersteller-App** — Opcodes, Frame-Format, WLAN-Auslöser,
  Verschlüsselung. Ergebnisse in [referenz.md](referenz.md).
- **Kopplungsablauf** — `pair.sh`, portabel, mit Ansagen.

**Offen**, nach Nutzen sortiert:

1. **`skyshutter bundle`** — sammelt Probe, DeviceInfo roh und geparst, ein
   Live-View-Frame und Logs in ein Verzeichnis. Ein Kommando statt sechs.
2. **`skyshutter props --dump/--diff`** — das Werkzeug für Abschnitt 6.
3. **Entschlüsselung der WLAN-Zugangsdaten** — Blowfish-CBC, Schlüssel aus
   Werten ableitbar, die über BLE sichtbar sind. Der aufwendigste Posten, aber
   der einzige Weg zu einem Passwort, das bei jeder Verbindung wechselt.
4. **`skyshutter pcap datei.pcap`** — PTP/IP aus einem Mitschnitt zerlegen.
   Nachrangig geworden: Ein Mitschnitt des WLAN-Verkehrs setzt voraus, dass die
   Kamera ihr WLAN öffnet — genau das ist das offene Gate.
5. **Reconnect-Logik** gegen einen Simulator, der Verbindungsabbrüche simuliert.

## 9. Repo-Konventionen

* Branch: `claude/coolpix-wifi-remote-api-92dw8v`. Kein Push auf `main`.
* Commits: englisch, Betreff imperativ, Body erklärt *warum*. Keine
  Modellbezeichnungen im Repo.
* `pytest` und `ruff check .` müssen vor jedem Commit grün sein.
* Deutsch in `docs/`, Englisch im Code und in Commits — so wie bisher.
* **Lizenz:** libgphoto2 ist LGPL, skyshutter MIT. Fremde Tabellen und Codestücke
  werden zur Verifikation gelesen, nicht kopiert. Bei nsg und dem ID-Extractor
  vor jeder Übernahme die Lizenzdatei prüfen.
* **Öffentliches Repo:** Mitschnitte können SSID, Passphrase, Pairing-GUID und
  Seriennummer enthalten. Vor jedem Commit schwärzen. `.gitignore` blockt `*.pcap`
  absichtlich; ein `git add -f` ist eine bewusste Entscheidung, keine Routine.

## 10. Wissen über Sessiongrenzen retten

Am Ende jeder Session, in dieser Reihenfolge:

1. `FINDINGS.md` aktualisiert und committet?
2. MEMEX #17935 (Projektstand) per `supersede_memory` aktualisiert — nie eine
   zweite Kopie anlegen.
3. Nächste Runde als fertigen Kommandoblock hinterlassen, damit Thomas auch ohne
   mich weitermachen kann.

Was in keinem dieser drei Kanäle steht, existiert beim nächsten Mal nicht.
