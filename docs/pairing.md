# Kopplung mit der Kamera — der vollständige Ablauf

Stand 22.08.2026, zweimal erfolgreich durchlaufen. Alles hier ist gemessen;
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
[2] Klassischer Inquiry, Gerät über den Namen finden
      │   Bonding, Zahlencode an der Kamera mit OK bestätigen
      ▼
[3] Reconnect-Handshake mit der eben vergebenen Kennung
      │
      ▼
   „Your camera and smart device are connected!"
```

Schlägt Schritt 2 fehl, weil der Inquiry nichts findet: Bluetooth aus- und
einschalten, 12 s warten, alles wiederholen. Das Skript macht das selbst.

## Der Ablauf

`tools/pair.sh` macht alles und sagt an, wann du am Gerät sein musst:

```bash
bash tools/pair.sh
```

Drei Ansagen kommen dabei, und alle drei sind nötig:

1. **Menü öffnen** — nach dem Reset, für den Handshake
2. **Auf die Kamera schauen** — beim Code sofort OK drücken, das Fenster ist
   rund 30 Sekunden
3. **Menü erneut öffnen** — nach dem Bestätigen verlässt die Kamera den
   Advertising-Modus, und der abschließende Reconnect braucht ihn wieder

Ohne die dritte Ansage läuft Schritt 3 zwei Minuten ins Leere, und die Kamera
bleibt auf „could not connect" stehen.

### Zeitbedarf

Gemessen am 22.08.2026: Sobald die Kamera erreichbar ist, dauert der ganze
Vorgang **16 Sekunden** — Handshake 3 s, Kamera im Inquiry gefunden nach 1 s,
Code bis `PAIRED` 12 s. Alles darüber hinaus ist Warten darauf, dass jemand am
Gerät steht.

## Die fünf Fallen

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

**5. Der Windows-Bluetooth-Stack verschluckt sich.** Nach mehreren
Verbindungs- und Watcher-Zyklen findet der Inquiry **nichts mehr** — auch
Geräte nicht, die klar in Reichweite sind. Fünf Fehlversuche in Folge, dann
nach `Off`/`On` sofort wieder alles gefunden.

**6. Der Inquiry meldet Geräte, bevor ihr Name da ist.** Die Kamera erschien
mehrfach als `''` und mehrfach als `Bluetooth AA:BB:CC:DD:EE:FF` — Windows'
Platzhalter, wenn die Namensauflösung nicht durchkommt. Wer auf den Namen
filtert, wirft genau das Gerät weg, das er sucht.

**Zuverlässig ist die Geräteklasse:** `class_of_device == 0x080620`
(Imaging/Kamera). `classic-pair.py` erkennt die Kamera daran, unabhängig vom
Namen. Und die dort auftauchende Adresse `AA:BB:CC:DD:EE:FF` ist dieselbe, mit
der die Hersteller-App im Handy-Log klassisch gekoppelt hat — es ist die
**klassische** Bluetooth-Adresse der Kamera, eine andere als ihre BLE-Adresse.

## Zeitfenster

Zwischen dem Ende des Handshakes und dem Inquiry vergehen rund 35 Sekunden.
Das reicht — beide erfolgreichen Läufe hatten diesen Abstand. Der Zahlencode
erscheint danach, und für die Bestätigung an der Kamera bleiben etwa
**30 Sekunden**, bevor Windows mit `AUTHENTICATION_FAILURE` abbricht.

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
