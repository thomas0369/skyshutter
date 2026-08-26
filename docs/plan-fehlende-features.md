# tplan — Restfeatures bis zur automatischen Nachtführung

Assumption-First-Plan (Phase 1–8), Stand 26.08.2026, 20:20 Uhr.
Ziel: **das Rig führt nachts selbst einen Stern** — Stream → star_tracker →
ZMQ → Mount-Loop → echte Mount-Bewegung. Plus die kleinen Reste.

> Vorbehalt: Die tplan-Skill-Datei selbst ist für die aktuelle Sandbox
> gesperrt (Read und bash verweigert); Phasenstruktur aus der globalen
> Konfiguration rekonstruiert. Format-Abweichung möglich.

## Phase 1 — ASSUME (Annahmen, alle explizit)

| # | Annahme | Risiko wenn falsch |
|---|---|---|
| A1 | Dunkelheit ab ~22:30, Kamera zeigt sternreichen Himmelsausschnitt | Nachtlauf verschiebt sich; nichts kaputt |
| A2 | WLAN-Tode (−71 dBm) sind für die Nachtvalidierung tolerierbar (Wrapper heilt in 60–90 s) | CSV-Lücken; Messlauf ggf. wiederholen |
| A3 | AZ-GTi ist per FTDI+INDI steuerbar — Vorgängerprojekt hat das bereits betrieben (indi_backend.py, pyindi-client vorhanden) | Mount-Integration scheitert an alter Bibliothek; dann: WLAN-Route des Mounts klären |
| A4 | WLAN-PSK des AZ-GTi liegt bei Thomas (Display) | Nur relevant, falls FTDI scheitert — FTDI ist Pfadroute |
| A5 | `/etc/astrotracker.env` genügt: `ASTRO_BACKEND=indi` umschalten + Dienst-Restart | Loop-Start müsste angepasst werden |
| A6 | **Unpark/Bewegung nur nach ausdrücklichem OK von Thomas** (Regel 3, playbook §7) | Sicherheitsverstoß — nicht akzeptabel |
| A7 | AF fokussiert helle Sterne bei offener Blende scharf genug für Centroiden | manueller Fokus am Objektiv nötig (0x9204 fehlt, s. A9) — kein Blocker für Tracking, nur für Aufnahmen |
| A8 | 0x9204/0x920C/BLE-Auslöser endgültig fehlend (messend vermisst) → **nicht Teil dieses Plans** | — |
| A9 | CPU-CV reicht (Rauschfloor 0,06 px gemessen); Hailo ungenutzt | — |
| A10 | star_tracker-Defaults (0.5/3/2000/12) liegen nahe genug für einen 120-s-Erstlauf | zu viele/falsche Blobs → Parameter aus CSV kalibrieren, zweiter Lauf |

## Phase 2 — VERIFY (messbar nachgehen, bevor gebaut wird)

| # | Messung | Gate |
|---|---|---|
| V1 | Nachtlauf `star_tracker --duration 120 --out /tmp/stars.csv --zmq`: echte Stern-Blobs? Flächengröße? Track-Stabilität? | ≥1 Track mit ≥30 Hits, Flächen liegen in klarem Band → min/max-area kalibriert |
| V2 | Mit FTDI: `/dev/ttyUSB0` vorhanden, indiserver startet, Loop verbindet (Backend indi, **geparkt**) | Telemetrie zeigt echte Achswinkel statt 0.0 |
| V3 | WLAN nach Umpositionierung: RSSI-Messung (Ziel > −60 dBm) | besser: Session-Längen steigen; schlechter: Antennenfrage eskalieren |
| V4 | Zoom-Schrittwerte > 1: zwei raw-Messungen (Value 3 und 10) | Kalibrierkurve erweitert oder „ein Schritt pro Befehl" bestätigt |
| V5 | `raw 0x90CA` einmalig, Datenphase sichern | Format dokumentiert (uint32-Count+uint16-Run oder roher Run) |
| V6 | ZMQ-Kette mit **echten** Stern-Detektionen (target.valid=true über Minuten) | Mock-Beweis (30/30) wird zum Echtbeweis |

## Phase 3 — SPIKE (Risiko isolieren, bevor es wehtut)

- **S1 indi-Trockenlauf:** `ASTRO_BACKEND=indi`, Mount geparkt, kein Unpark.
  Nur lesen: Verbindung, Achswinkel, Telemetrie. Abbruch: Loop-Crash →
  zurück auf mock, Fehler dokumentieren.
- **S2 erste geführte Korrektur:** Unpark NUR nach OK (A6). Minimalgeschwindigkeit,
  Zeitfenster ≤ 60 s, Stop-Bedingung: Fehler < 0.02 norm oder Timeout.
  Beobachter: Telemetrie-Mitschnitt; Not-Aus: Dienst-Stopp + Park-Kommando.

## Phase 4 — DESIGN

- **Deployment auf dem Pi als Dienste:** stream-wrapper (läuft),
  star_tracker als `skyshutter-tracker.service` (Restart=always, ARGS aus
  `/etc/skyshutter-tracker.conf` — Nachtprofil), Mount-Loop (läuft als
  astrotracker-Dienst). Ein `tracker-on.sh`/`tracker-off.sh` Paar als Schalter.
- **Nachtprofil** als Datei (`tools/cv/night-profile.sh` mitEXPORT der
  Parameter) statt langer CLI-Zeilen im Kopf.
- **Sicherheit:** Unpark bleibt manuell (nie im Tracker), Geschwindigkeits-
  Limit im Loop konfiguriert, Tracker publish nur (bewegt nichts selbst).
- Keine neuen Abhängigkeiten im skyshutter-venv (stdlib-only bleibt);
  Tracker nutzt weiter System-python3.

## Phase 5 — ATTACK (Epics, priorisiert)

| Epic | Inhalt | hängt ab von | Abnahme |
|---|---|---|---|
| **E1 Nachtvalidierung** (heute) | V1 + V6: Nachtläufe, Parameter aus CSV, FINDINGS | A1/A2 | V1+V6-Gates grün |
| **E2 Mount-Integration** | FTDI angeschlossen (Thomas), V2, S1; env auf indi; Telemetrie echt | A3/A5, Kabel | V2-Gate; Loop läuft 10 min stabil, geparkt |
| **E3 Führungsschleife** | S2: erster geschlossener Regelkreis am Stern; Speed-Tuning; ggf. Anti-Auto-Chase-Verhalten prüfen (Vorgänger-Code) | E1+E2, OK von Thomas | Stern bleibt über 10 min im Zentrum-Fenster (±0.05 norm) |
| **E4 WLAN-Härtung** | Thomas: Position/Antenne; danach V3; optional `tools/hw/rssi-log.sh` (minütlicher iw-Dump ins CSV) | physisch | Session-Längen > 10 min üblich |
| **E5 Reste (jede Session ein Posten)** | V4 Zoom-Schritte · V5 0x90CA · `props --diff` · pcap-Decoder (Backlog-Position) | — | je Messung in FINDINGS |
| **E6 Hygiene** | Mango-WAN statisch, Pi-Strom trennen (physisch); MEMEX-Supersedes sobald Session lebt | — | erledigt/verbucht |

## Phase 6 — TEST

- pytest+ruff vor jedem Commit (Stand 176 grün); neue Features bekommen
  Unit-Tests gegen den Simulator (Muster: keepalive-, battery-Tests).
- Jede Hardware-Messung: FINDINGS-Eintrag mit Rohwerten (Regel 2).
- E3-Abnahme ist ein Messprotokoll, kein Gefühl: Telemetrie-CSV zeigt
  Fehlerkurve um Null.

## Phase 7 — DOCUMENT

- FINDINGS je Messung (laufend), plan.md-Phase „CV/Tracking" ergänzt,
- playbook §8-Backlog abhaken, was E5 erledigt,
- Sessionende: MEMEX #17935 supersede + Kommandoblock für nächste Runde.

## Phase 8 — SHIP

- Branch `claude/coolpix-wifi-remote-api-92dw8v` bleibt; Merge auf main nur
  nach OK (Regel: kein push/merge ohne Auftrag).
- „Ausgeliefert" heißt hier: Dienste laufen auf dem Pi, eine Nacht
  Führungsbetrieb protokolliert.

## Heute Nacht (Reihenfolge)

1. Thomas: Rig ausrichten (Kamera auf Sternfeld, Pi-Antenne Richtung Kamera).
2. `star_tracker`-Nachlauf 120 s → CSV → Parameter kalibrieren → zweiter Lauf.
3. FINDINGS + Commit + Sync. E1 fertig, wenn Gates V1/V6 grün sind.
