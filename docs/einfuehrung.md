# Worum es geht

## Die Kamera

Eine Nikon Coolpix P1100 ist eine Kompaktkamera mit einem ungewöhnlichen
Objektiv: **24 bis 3000 Millimeter**, kleinbildäquivalent, in einem Gehäuse ohne
Wechseloptik. Das ist ein 125-facher Zoom.

Diese Zahl ist hier keine Herstellerangabe, sondern gemessen — die Kamera meldet
sie über PTP selbst:

```
Focal Length Minimum:  24 mm
Focal Length Maximum:  3000 mm
```

Zum Vergleich: Ein Teleobjektiv für eine Systemkamera endet üblicherweise bei
400 oder 600 Millimetern. Für 3000 mm bräuchte man dort ein Spiegelteleobjektiv
oder ein Teleskop mit Adapter — beides schwerer, teurer und umständlicher.

Der Preis dafür ist ein kleiner Sensor (1/2,3 Zoll, 16 Megapixel). Bei Tageslicht
ist das gleichgültig, bei Nacht nicht: Rauschen und Dynamik liegen deutlich unter
dem, was eine Vollformatkamera leistet.

## Warum das für Astrofotografie taugt

Nicht für alles. Für zwei Dinge sehr gut.

**Der Mond.** Bei 3000 mm beträgt das Bildfeld rund **0,69°** — gerechnet aus
`2·arctan(18 mm / 3000 mm)`. Der Vollmond misst etwa 0,52°. Er füllt also drei
Viertel der Bildbreite. Krater, Rillen und der Terminator sind formatfüllend, ohne
dass ein Teleskop aufgebaut werden muss.

**Die hellen Planeten.** Jupiter erscheint unter etwa 47 Bogensekunden, also
0,013°. Auf 4608 Pixel Bildbreite sind das rund **90 Pixel** — genug für die
Wolkenbänder und die vier großen Monde. Saturn mit Ring liegt in derselben
Größenordnung. Für Lucky Imaging, bei dem man aus einem Video die schärfsten
Einzelbilder stapelt, reicht das.

**Wofür sie nicht taugt:** Deep-Sky. Nebel und Galaxien brauchen lange
Belichtungen und Nachführung; dafür ist der Sensor zu klein und die längste
Verschlusszeit zu kurz.

## Das Problem

Bei 3000 Millimetern wird jede Berührung der Kamera zum Bildfehler. Ein
Tastendruck am Auslöser reicht, um das Bild zu verwackeln — die Vergrößerung
überträgt sich auf jede Erschütterung. Dazu kommen zwei praktische Ärgernisse:

- **Der Fokus ist elektrisch geführt** („by wire"). Der Ring bewegt keinen
  Mechanismus, sondern gibt einen Wunsch an einen Motor weiter, und der schießt
  gern über das Ziel hinaus. Von Hand exakt zu fokussieren ist mühsam.
- **Das Motiv zu finden ist schwer.** Bei 0,69° Bildfeld ist der Mond schnell
  außerhalb, und die Erddrehung schiebt ihn in gut einer Minute aus dem Bild.

Die naheliegende Lösung ist Fernsteuerung: auslösen, fokussieren und zoomen, ohne
die Kamera anzufassen — und das Bild währenddessen auf einem größeren Schirm
sehen.

## Warum nicht die Hersteller-App

Nikons SnapBridge kann Fernaufnahme, aber mit Einschränkungen, die genau an der
falschen Stelle liegen:

- Sie läuft auf dem Telefon. Für eine Nacht mit Belichtungsreihen und
  automatischer Auswertung ist das der falsche Ort.
- Sie bietet keine Skriptbarkeit — keine Serien mit wechselnden Parametern, keine
  Anbindung an vorhandene Astronomie-Software.
- Sie ist die einzige Möglichkeit, das WLAN der Kamera einzuschalten. Ohne App
  kein Livebild, auch nicht am eigenen Rechner.

Der letzte Punkt ist der eigentliche Anlass dieses Projekts. **Die Kamera kann
mehr, als ihre App freigibt** — sie spricht ein offenes Protokoll, das seit
Jahren dokumentiert ist. Nur der Schalter, der es einschaltet, liegt hinter der
App.

## Was skyshutter ist

Ein freier Client für dieses Protokoll, in Python, ohne Abhängigkeiten. Er soll
das, was die Kamera ohnehin kann, ohne Umweg über das Telefon erreichbar machen:

| Funktion | Nutzen am Nachthimmel |
|---|---|
| Livebild als Videostrom | Motiv finden und scharfstellen, auf einem großen Schirm |
| Auslösen per Kommando | keine Berührung, also keine Verwacklung |
| Zoom per Kommando | Bildausschnitt ändern, ohne die Ausrichtung zu stören |
| Belichtungsreihen | mehrere Einstellungen automatisch durchfahren |
| Bilder direkt abholen | kein Kartenwechsel im Dunkeln |

Alles davon setzt voraus, dass die Kamera diese Operationen anbietet. Was sie
tatsächlich anbietet, steht gemessen in [referenz.md](referenz.md) — und dort
zeigt sich, dass zwei ursprüngliche Annahmen falsch waren.

## Zwei Korrekturen an der eigenen Ausgangsthese

**Der manuelle Fokus per Kommando fällt aus.** Der Projektplan nannte
`MfDrive` als „die eigentliche Rechtfertigung des ganzen Projekts" — den Opcode,
mit dem man den Fokusmotor schrittweise fahren kann, um die Hysterese des
Fokusrings zu umgehen. **Diese Kamera unterstützt ihn nicht.** Gemessen am
23.08.2026: `0x9204` steht nicht in ihrer Operationsliste, und die Hersteller-App
kennt ihn für kein einziges Modell.

Was bleibt, ist der Autofokus per Kommando plus das Setzen des Messfeldes
(`0x90C1`, `0x9205`). Für den Mond, der hell und kontrastreich ist, dürfte das
genügen — für schwache Objekte ist es ein echter Verlust.

**Der Fernauslöser über Bluetooth fällt ebenfalls aus.** Er war als
stromsparende Rückfallebene geplant. Die Kamera meldet über ihre Feature-Bits
selbst, dass sie die Kamerasteuerung über Bluetooth nicht anbietet — Bluetooth
kann bei ihr aufwecken, konfigurieren und Bilder anstoßen, aber nicht auslösen.

Damit bleibt **WLAN als einziger Weg**, der Bild und Steuerung zugleich liefert:
HDMI schaltet den Funk ab, USB zieht das Objektiv ein und sperrt das Livebild.
Diese drei Wege und ihre Belege stehen in [referenz.md](referenz.md).

## Wo das Projekt steht

Das Protokoll ist verstanden: 38 Operationen und 20 Einstellwerte sind
ausgelesen, das Format des Livebildes ist bekannt, die Kopplung über Bluetooth
läuft reproduzierbar. Der Client spricht beide Transportwege — Kabel und Funk.

Was fehlt, ist ein einzelnes Byte: der Befehl, mit dem die Kamera ihr WLAN
öffnet. Er ist aus der Hersteller-App gelesen und dokumentiert, aber an der
Hardware noch nicht bestätigt. Solange er nicht wirkt, gibt es kein Livebild.

Der jeweils aktuelle Stand steht im Kopf von [FINDINGS.md](FINDINGS.md).

## Rechtlicher Rahmen

Das Protokollwissen stammt aus drei Quellen: eigenen Messungen an der eigenen
Kamera, veröffentlichter Vorarbeit anderer, und der Analyse der Hersteller-App.
Letzteres ist nach **§ 69e UrhG** ausdrücklich zulässig — Dekompilierung zur
Herstellung der Interoperabilität eines unabhängig geschaffenen Programms, wenn
die Informationen nicht anders zugänglich sind. Genau das trifft hier zu und ist
in [recherche.md](recherche.md) belegt: Kein öffentliches Projekt dokumentiert
diesen Teil des Protokolls.

Gelesen wurde zur Verifikation, übernommen wurde nichts.
