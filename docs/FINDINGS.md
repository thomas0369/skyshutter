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
| **Stand vom** | 2026-08-21 |

**Nichts in diesem Dokument ist bisher an echter Hardware gemessen.** Der Code
ist ausschließlich gegen den Simulator getestet.

---

## Offene Fragen

Spiegelt die Liste in [protokoll.md](protokoll.md); abgehakt wird nur mit Messung.

- [ ] Antwortet die Kamera im Remote-Modus auf TCP 15740?
- [ ] Wird eine ungepaarte GUID akzeptiert, oder ist der BLE-Handshake Pflicht?
- [ ] Welche Vendor-Opcodes stehen in `operations_supported`?
- [ ] Live View vorhanden — Header-Länge, Auflösung, Bildrate?
- [ ] Vendor-Properties für den 125×-Zoom?
- [ ] Verträgt die Kamera parallele Sessions neben SnapBridge?
- [ ] Welche IP hat die Kamera als AP tatsächlich?
- [ ] WPA3-SAE bestätigt? (Herstellerangabe, ungeprüft)

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

*(noch keine Einträge)*

---

## Widerlegtes

Was wir ausgeschlossen haben — damit es niemand erneut versucht.

| Datum | Annahme | Womit widerlegt |
|---|---|---|
| — | — | — |
