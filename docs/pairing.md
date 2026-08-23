# Kopplung mit der Kamera — der vollständige Ablauf

Stand 22.08.2026, fünfmal erfolgreich durchlaufen. Alles hier ist gemessen;
Vermutungen sind als solche gekennzeichnet.

Die Kopplung besteht aus **zwei Hälften**, und beide sind nötig. Wer nur die
erste macht, ist authentifiziert, steht aber in keiner Geräteliste — das
kostete hier einen halben Tag.

```
Kamera-Menü öffnen und offen lassen
      │
      ▼
[1] BLE: vier Handshake-Stufen auf 0x2000
      │   Clientname (32 B) auf 0x2002, dann trennen
      ▼
[2] Klassischer Inquiry, Gerät über die Geräteklasse finden
      │   Bonding, Zahlencode an der Kamera mit OK bestätigen
      ▼
   „Your camera and smart device are connected!"

[3] Reconnect-Handshake — nur, wenn die Kamera stattdessen auf
    „Establishing connection" hängenbleibt. Im Normalfall überflüssig.
```

**Schritt 3 gehört nicht zum Normalweg.** Am 22.08. um 21:57 lief er ins Leere
(`camera not advertising`) — genau deshalb, weil die Kamera zu diesem Zeitpunkt
schon verbunden war. Er ist die Reparatur für den Fall, dass zwischen Bond und
Bestätigung zu viel Zeit vergangen ist.

Schlägt Schritt 2 fehl, weil der Inquiry nichts findet: Bluetooth aus- und
einschalten, 12 s warten, alles wiederholen. Das Skript macht das selbst.

## Der Ablauf

`tools/pair.sh` macht alles und sagt an, wann du am Gerät sein musst:

```bash
bash tools/pair.sh
```

Zwei Ansagen kommen dabei, und beide sind nötig:

1. **Menü öffnen** — nach dem Reset, für den Handshake
2. **Auf die Kamera schauen** — beim Code sofort OK drücken, das Fenster ist
   rund 30 Sekunden

Meldet die Kamera danach „connected", ist der Vorgang fertig. Bleibt sie auf
„Establishing connection" stehen, das Menü erneut öffnen und den Reconnect
nachschieben — der Ablauf gibt das Kommando mit der vergebenen Kennung aus.

### Zeitbedarf

Gemessen am 22.08.2026, 21:56 — der bisher glatteste Durchlauf:

```
21:56:25  Funk-Reset fertig
21:56:50  BLE verbunden, mtu=515          (+25 s)
21:56:51  authentifiziert, registriert     (+ 1 s)
21:56:59  im Inquiry gefunden              (+ 8 s)
21:57:01  Zahlencode erscheint             (+ 2 s)
21:57:05  PAIRED                           (+ 4 s)
```

**40 Sekunden vom Reset bis zum Bond.** Der Löwenanteil ist der Funk-Hochlauf
nach dem Reset; der eigentliche Vorgang dauert 15 Sekunden. Alles darüber
hinaus ist Warten darauf, dass jemand am Gerät steht.

**Kurz halten.** Der Abstand zwischen Handshake und Inquiry betrug hier
9 Sekunden. Die früher notierten 35 Sekunden funktionierten auch, sind aber
kein Ziel — die Kamera verlässt den Kopplungsmodus von selbst.

## Die sieben Fallen

**1. Der Beacon hängt am Menü.** Die Kamera advertised nur, solange *Mit
Smartgerät verbinden* auf ihrem Display offen steht. „Nicht gefunden" heißt
meistens: niemand steht am Gerät.

**2. Der advertisierte Name ist abgeschnitten.** Im Advertising steht `P110`,
nicht `P1100_…` — die 128-Bit-Service-UUID frisst die Nutzlast. **Nie über den
Namen suchen, immer über die Service-UUID** `0000de00-3dd4-4255-8d62-6dc7b9bd5561`.
Die BLE-Adresse taugt auch nicht, sie rotiert.

**3. Der Handshake muss als unbekannter Client laufen.** Mit gespeicherter
Kennung (`--device`/`--nonce`) ist es ein *Reconnect*, und nach einem Reconnect
öffnet die Kamera ihre klassische Seite **nicht**. Der Inquiry findet dann
nichts, obwohl der Handshake sauber durchlief.

**4. Der Inquiry braucht den Selektor für ungepaarte Geräte.**
`DeviceInformation.find_all_async` liefert nur den Windows-Cache, und der ist
für ungepaarte Geräte leer — die Suche meldet null Geräte, obwohl die Kamera
sendet. Ein `DeviceWatcher` auf
`BluetoothDevice.get_device_selector_from_pairing_state(False)` macht den
echten Inquiry. Er muss das ganze Zeitfenster durchlaufen; ihn bei
`EnumerationCompleted` zu stoppen findet gar nichts, weil Windows das schon
nach einer Sekunde meldet.

**5a. Die Kamera verweigert nach mehreren Kopplungen jedes Bonding.** Das war
der teuerste Effekt des Tages. Nach etwa zehn Kopplungs- und Entkopplungszyklen
antwortete sie überhaupt nicht mehr: im Inquiry sofort gefunden, aber die
Kopplungsanfrage blieb unbeantwortet, dreimal in Folge, über eine Stunde. Auch
**Windows' eigene Kopplungsroutine** scheiterte dann (`FAILED`), nicht nur die
eigenen API-Aufrufe — daran erkennt man, dass es nicht am Client liegt.

**Abhilfe: die Kamera aus- und wieder einschalten.** Danach lief das Bonding
beim ersten Versuch, Code nach einer Sekunde. Vorher hatten wir stundenlang
Windows zurückgesetzt und die Kamera nie.

**Der Aus-/Einschalter half aber nicht immer.** Am Nachmittag des 22.08.
scheiterten zwischen 14:12 und 15:39 neun Bonding-Versuche in Folge mit
`AUTHENTICATION_TIMEOUT`, auch nach Kamera-Neustart, auch mit Windows' eigener
Routine. Derselbe Ablauf lief um 21:56 beim ersten Versuch glatt durch. Der
einzige messbare Unterschied: **sechs Stunden Funkruhe dazwischen.**

Praktisch heißt das: Wenn zwei, drei Versuche hintereinander scheitern, hört
auf. Weitermachen verschlimmert es, und die Ursache liegt nicht im Ablauf.
*(Vermutung — was in der Ruhephase geschieht, wurde nicht gemessen.)*

**5b. Der Windows-Bluetooth-Stack verschluckt sich.** Nach mehreren
Verbindungs- und Watcher-Zyklen findet der Inquiry **nichts mehr** — auch
Geräte nicht, die klar in Reichweite sind. Fünf Fehlversuche in Folge, dann
nach `Off`/`On` sofort wieder alles gefunden.

**6. Der Inquiry meldet Geräte, bevor ihr Name da ist.** Die Kamera erschien
mehrfach als `''` und mehrfach als `Bluetooth AA:BB:CC:DD:EE:FF` (geschwärzt) — Windows'
Platzhalter, wenn die Namensauflösung nicht durchkommt. Wer auf den Namen
filtert, wirft genau das Gerät weg, das er sucht.

**Zuverlässig ist die Geräteklasse:** `class_of_device == 0x080620`
(Imaging/Kamera). `classic-pair.py` erkennt die Kamera daran, unabhängig vom
Namen. Und die dort auftauchende Adresse ist dieselbe, mit
der die Hersteller-App im Handy-Log klassisch gekoppelt hat — es ist die
**klassische** Bluetooth-Adresse der Kamera, eine andere als ihre BLE-Adresse.

## Zeitfenster

Zwischen dem Ende des Handshakes und dem Inquiry liegen im schnellsten
gemessenen Lauf **9 Sekunden** (22.08.2026, 21:56). Frühere Läufe mit rund
35 Sekunden Abstand funktionierten ebenfalls — kurz ist aber besser, weil die
Kamera den Kopplungsmodus von selbst verlässt.

Der Zahlencode erscheint danach, und für die Bestätigung an der Kamera bleiben
etwa **30 Sekunden**, bevor Windows mit `AUTHENTICATION_FAILURE` abbricht.

`--quick` überspringt den Werte-Dump nach der Authentifizierung; der kostet
sonst zusätzliche zwanzig Sekunden.

## Aufräumen vor einem neuen Versuch

Beide Seiten müssen den alten Bond vergessen, sonst geht die Kamera gar nicht
erst in den Kopplungsmodus:

```bash
"$PY" -u classic-pair.py --seconds 20 forget    # Windows-Seite
```

An der Kamera den Eintrag `skyshutter` aus der Liste der gekoppelten Geräte
löschen.

## Was die Kamera über klassisches Bluetooth anbietet

Gemessen am 22.08.2026 mit `classic-pair.py services`. Sie hat genau **einen**
RFCOMM-Dienst:

```
0x0100  Servicename:  "MFi Bluetooth"
0x0001  Service-UUID: 00000000-deca-fade-deca-deafdecacaff
0x0004  L2CAP -> RFCOMM, Kanal 1
class_of_device = 0x080620   (Imaging / Kamera)
```

Das ist Apples iAP-Zubehörkanal — für iPhones. **Für alles andere bietet die
Kamera über klassisches Bluetooth nichts an.** Sie ist auf dieser Seite also
kein Server, zu dem man sich verbinden könnte; sie will selbst verbinden.

## Was danach offen ist

Nach dem Bonding zeigt die Kamera **„Establishing connection"**. Läuft
danach nichts, endet das nach einer Weile in **„could not connect"** — der Bond
bleibt zwar bestehen und `skyshutter` steht in der Liste, aber die Kamera
meldet einen Fehler.

**Der Reconnect-Handshake ist der Abschluss.** Mit der Kennung, die beim
Pairing vergeben wurde, quittiert die Kamera mit
**„Your camera and smart device are connected!"** Ohne diesen dritten Schritt
ist die Kopplung zwar eingetragen, aber nicht abgeschlossen.

Ein RFCOMM-Serial-Dienst auf unserer Seite (`tools/rfcomm-listen.py`) wird
dabei **nicht** benutzt. Die Kamera verbindet sich dorthin nicht.
