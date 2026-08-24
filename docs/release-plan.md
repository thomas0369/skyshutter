# Release-Plan — Recht, Hygiene, Packaging (tplan, 24.08.2026)

Ziel: Das Repo veröffentlichungsreif machen — (1) rechtliches Risiko minimieren,
(2) Queue aufräumen, (3) Dritten eine 1-Zeilen-Installation (pip/dpkg) geben.
Gates: **R** (Recht) → **H** (Hygiene) → **P** (Packaging) → **S** (Ship).

## Verifizierter Ist-Zustand (Phase 2, mit Beleg)

| # | Befund | Beleg |
|---|---|---|
| V1 | MIT-LICENSE existiert | `LICENSE` (Copyright 2026 thomas0369) |
| V2 | pyproject + hatchling + extras (usb/ble/windows), `[project.scripts]` ab Z. 38 | `pyproject.toml` |
| V3 | **AP-Passwort + SSID in getrackten Dateien** | `git grep <AP-PSK>` → FINDINGS.md; Tests nutzen echte SSID als Fixture |
| V4 | **Beide bereits in Origin-History gepusht** | `git log -S <AP-PSK> origin/…` → `e98dbcf`; SSID → `2032b52` |
| V5 | Beweisbilder ohne EXIF (baseline JPEG) | `docs/proof/lv_0*.jpg`, python-Check 24.08. |
| V6 | libgphoto2 nur in Kommentaren genannt, kein Code übernommen | `git grep -il gphoto` → 3 Kommentarstellen |
| V7 | README modellneutral; **pyproject.description enthält „Coolpix P1100"** | `README.md:3`, `pyproject.toml:7` |
| V8 | Kein CI-Workflow; 16 ungepushte Commits; Pi-Clone dirty auf `980cead` | `ls .github/workflows` leer; git log |
| V9 | App-GUID (fest, alle Installationen identisch) in 5 Dateien | `git grep -c 00112233-4455` |

## M1 — Rechtssicherheit (Gate R)

- **R1 Schwärzen in HEAD.** `<AP-PSK>` → `<AP-PSK>`, `P1100_<serno>` →
  `P1100_<serno>` in FINDINGS.md/tests/. Tests auf generische Fixtures
  (`P1100_SN1234`) umstellen. Echte Werte → `docs/secrets.local.md`
  (gitignored, wie `*.pcap`).
- **R2 History-Bereinigung.** `git filter-repo --replace-text` für V4-Muster
  über ALLE Branches → force-push (Regel-Ausnahme nötig, User entscheidet)
  → Alle Klones neu klonen (WSL, Pi). *Nur wenn Repo öffentlich wird/wurde;
  bei privatem Repo optional, empfohlen.*
- **R3 NOTICE.md** (neu): (a) Reverse-Engineering-Basis: Dekompilation/
  Protokollanalyse ausschließlich zur **Interoperabilität** (§69e UrhG;
  Art. 6 RL 2009/24/EG); (b) Verhältnis libgphoto2 (LGPL-2.1): **nur Lektüre
  zur Verifikation, kein Code übernommen** (V6 als Beleg); (c) Marken-
  Disclaimer: Nikon/Coolpix sind Marken ihrer Inhaber; Projekt unabhängig,
  nicht affiliiert, keine Unterstützung impliziert; (d) die feststehende
  Protokoll-GUID ist Interoperabilitätskonstante, kein Individualgeheimnis.
- **R4 Artefakt-Neutralität.** pyproject.description → „Control a Nikon
  Coolpix camera over its own WiFi via PTP/IP" (kein Modell). Prüfen:
  PyPI-Metadaten, debian/changelog, README (bereits neutral, V7).
- **R5 Secrets-Guard.** `tools/check-secrets.sh` (grep über `git grep` auf
  PSK-/SSID-/MAC-Muster) + pre-commit-Hook + CI-Schritt. Muster-Liste
  erweiterbar in `tools/secret-patterns.txt`.
- **Ehrlichkeitsklausel:** „Nicht verklagt werden" ist nicht garantierbar.
  Dieser Plan minimiert die drei konkreten Haftungskanäle (Urheberrecht,
  Marken, Privatsphäre/DSGVO-eigene Daten). Keine Rechtsberatung.

## M2 — Repo-Hygiene (Gate H)

- **H1** `ergebnis.md` → gitignore (Delegat-Artefakt, bleibt lokal).
- **H2** Push-Regel klären (User): 16 Commits → origin; danach Pi:
  `git checkout -- . && git fetch && git reset --hard origin/<branch>` —
  Pi hatte keine eigenen Edits (V8, scp-Überschreibungen verlustfrei).
- **H3** `tools/README.md`: Welche Tools brauchen welches Extra (usb/ble/
  windows/pi); produktive (ble-watch, bt-agent, bt-pair, remote-start,
  liveview, auto-pair) vs. Bench (bt-listen, classic-pair, …).
- **H4** CI: `.github/workflows/ci.yml` — pytest + ruff auf push/PR (Linux,
  py3.10/3.12-Matrix, optional-deps-Strategie wie bisher).
- **H5** History-Check vor jedem künftigen Push: `git log -S <muster> @{u}..`
  als Routine in R5-Skript.

## M3 — Packaging (Gate P)

- **P1 CLI-Entry.** `src/skyshutter/cli.py` (`main()`), dünner Wrapper:
  `skyshutter wifi|liveview|pair …` delegiert an die tools-Logik; tools
  bleiben eigenständig lauffähig (import absolut: `skyshutter.…`).
  `[project.scripts] skyshutter = "skyshutter.cli:main"` (Zeile existiert
  bereits — Modul prüfen/anlegen).
- **P2 Extra `pi`**: bleak + pycryptodome (= Feld-Rig-Install: 
  `pip install skyshutter[pi]`).
- **P3 dpkg-Gerüst.** `debian/` (debhelper-compat 13, pybuild,
  python3-all): Paket `python3-skyshutter`; systemd-**user**-Units als
  Beispiele unter `debian/skyshutter-pi.examples` oder eigenes
  `skyshutter-pi`-Metapaket (Units: ble-watch, pair-agent). Build-Host =
  der Pi selbst (Debian 12; docker ist blockiert).
- **P4 Wheel-Smoke.** `python -m build` → frisches venv →
  `pip install dist/*.whl` → `skyshutter --help` + `pytest` gegen
  installiertes Paket. Deb-Smoke: auf dem Pi `dpkg -i … &&
  python3 -c "import skyshutter"`.
- **P5 Version/TAG.** v0.2.0 („first live view over WiFi"), GitHub-Release
  mit Beweis-Frame (metadatenfrei).

## M4 — Ship (Gate S)

Reihenfolge: R → H → P → S. Jedes Gate schließt mit pytest+ruff+R5-Guard.
S = push (normal), Pi-Rebind, Tag, Release-Notes.

## Attack / Pre-Mortem (Phase 5)

| Angriff | Antwort im Plan |
|---|---|
| „History behält das Passwort trotz Schwärzen" | R2 filter-repo + Verifikation `git log --all -S` leer + Klones neu |
| „force-push zerstörtorigin-Stand anderer Rechner" | Repo hat genau 2 Klones (WSL, Pi), beide werden neu gebunden; Sperre im Plan dokumentiert |
| „tools/ brechen bei pip-install (relative Imports)" | P1: absoluter Import; Smoke-Test P4 fängt es |
| „pyproject-Beschreibung verrät Modell" | R4 explizit; check-secrets erweitert um Modell-Muster für Artefakte |
| „dpkg untestbar (docker blockiert)" | P3: Pi als Build-Host |
| „App-GUID = ,'Dekompilat-Veröffentlichung'" | R3(d): Konstante, nicht individuell; Interop-Zweck dokumentiert |
| „Kamera-Passwort rotiert — Schwärzen überflüssig?" | Nein: SSID (Serienderivat) konstant; Muster-Schutz zukünftiger Werte (R5) |

## Teststrategie (Phase 6)

- **Unit:** 147 bestehend + neuer Test: check-secrets-Skript gegen Fixture-
  Repo mit/ohne Leck (grün/rot).
- **Integration:** P4 Wheel-Install-Smoke in temp-venv; cli --help.
- **Acceptance:** frischer Ort (Pi-Neuinstall via deb ODER venv):
  `pip install skyshutter[pi]` → `skyshutter liveview --help` funktioniert
  ohne Repo-Kontext.
- **Manuell (Hardware):** eine vollständige Nacht-Sequenz nach S (Bond
  existiert → nur Sanity: handshake+join+1 Frame).

## Selbst-Score (Phase 7)

1. Annahmen verifiziert (V1-V9 mit Belegen) ✓
2. Angriffsfläche behandelt (7 Attacks ↔ Maßnahmen) ✓
3. Gates testbar (jedes Gate: Befehl + erwartetes Ergebnis) ✓
4. Abhängigkeiten geordnet (R vor H2-Push! sonst Leck erneut gepusht) ✓
5. Ehrlichkeit über Restrisiko (R5-Klausel) ✓

**Score: 10/10.** (Iteration 1: 9/10 — pyproject-Beschreibung (V7) und
History-in-origin (V4) fehlten als explizite Punkte → aufgenommen.)
