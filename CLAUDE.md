# skyshutter — Arbeitsanweisung

WiFi-API für die Nikon Coolpix P1100 (Livebild + Steuerung, Zweck: Astrofotografie).
Python, stdlib-only, PTP/IP über TCP 15740.

## Zuerst lesen

1. `docs/FINDINGS.md` — **Stand-Block**: welche Phase, welches Gate, welche Messung fehlt.
2. `docs/playbook.md` — wie hier gearbeitet wird (Kern-Loop, Sicherheitsregeln).
3. `docs/plan.md` — der Phasenplan mit Gates.

MEMEX-Recall zu „skyshutter P1100": #17934 (Recherche), #17935 (Projektstand).

## Die drei Regeln, die alles andere tragen

1. **Ich habe keinen Zugriff auf die Kamera.** Kein WLAN, kein Bluetooth, kein USB.
   Jede Aussage über die echte Hardware stammt aus einer Messung von Thomas oder
   ist unbelegt — und wird dann auch so benannt.
2. **Kein Messwert ohne Test.** Jede Messung wird in `FINDINGS.md` festgehalten,
   von einem Test festgenagelt und im Simulator nachgezogen. Ein Simulator, der
   von der Realität abweicht, wird sofort korrigiert.
3. **An echter Hardware nur, was in `operations_supported` steht.** Keine
   Opcode-Sweeps. Schreibende Operationen (`Set*`, `Delete*`, `Format*`,
   `Firmware*`) nur nach ausdrücklichem OK. Details: playbook.md, Abschnitt 7.

## Vor jedem Commit

```bash
python -m pytest -q && ruff check .
```

Branch `claude/coolpix-wifi-remote-api-92dw8v`, nie `main`. Commits englisch,
`docs/` deutsch, Code englisch. Keine Modellbezeichnungen in Repo-Artefakten.

## Öffentliches Repo

Mitschnitte können SSID, Passphrase, Pairing-GUID und Seriennummer enthalten —
vor jedem Commit schwärzen. `*.pcap` ist absichtlich in `.gitignore`.

## Lizenz

skyshutter ist MIT, libgphoto2 LGPL-2.1. Fremde Opcode-Tabellen und Codestücke
werden zur Verifikation gelesen, nicht kopiert.

## Ohne Hardware produktiv

Backlog in playbook.md, Abschnitt 8 — priorisiert. Oben: pcap-Decoder,
`skyshutter bundle`, `props --dump/--diff`.

## Sessionende

`FINDINGS.md` committen, MEMEX #17935 per `supersede_memory` aktualisieren,
nächste Runde als fertigen Kommandoblock hinterlassen.
