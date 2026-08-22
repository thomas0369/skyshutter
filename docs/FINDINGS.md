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
- [ ] Welche IP hat die Kamera als AP tatsächlich? (Kandidaten: `192.168.1.1`,
      `192.168.0.10` — beide aus fremden Coolpix-Setups belegt)
- [ ] WPA3-SAE bestätigt? (Herstellerangabe, ungeprüft — entscheidet, ob
      Monitor-Mode als Messmethode überhaupt taugt)
- [ ] Liefert die P1100 über **USB**-PTP eine `operations_supported`-Liste?
      (Fremdmessung #1201 legt nahe: ja — umgeht die WLAN-Frage komplett)
- [ ] Ist die P1100 tatsächlich ML-L7-kompatibel? (zuvor als belegt geführt,
      Nachrecherche fand keine offizielle Bestätigung — der furble-Quick-Win
      hängt daran)

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
