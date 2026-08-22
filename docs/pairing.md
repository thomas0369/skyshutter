# Kopplung mit der Kamera — der vollständige Ablauf

Stand 22.08.2026, zweimal erfolgreich durchlaufen. Alles hier ist gemessen;
Vermutungen sind als solche gekennzeichnet.

Die Kopplung besteht aus **zwei Hälften**, und beide sind nötig. Wer nur die
erste macht, ist authentifiziert, steht aber in keiner Geräteliste — das
kostete hier einen halben Tag.

```
Kamera-Menü öffnen
      │
      ▼
[0] Bluetooth-Stack zurücksetzen          ← ohne das scheitert alles
      │
      ▼
[1] BLE: vier Handshake-Stufen auf 0x2000
      │   Clientname (32 B) auf 0x2002
      ▼
[2] BLE-Verbindung trennen
      │
      ▼
[3] Klassischer Inquiry, Gerät über den Namen finden
      │
      ▼
[4] Bonding, Zahlencode an der Kamera mit OK bestätigen
      │
      ▼
   gekoppelt — skyshutter steht in der Kameraliste
      │
      ▼
[5] Kamera zeigt „Establishing connection"      ← hier stehen wir
```

## Der Kommandoblock

```bash
PY='/mnt/c/Users/thoma/AppData/Local/Programs/Python/Python312/python.exe'
cd /mnt/c/Users/thoma/AppData/Local/Temp

# 0. Funk zuruecksetzen und 15 s warten
powershell.exe -File bt_state.ps1 -Action Off
powershell.exe -File bt_state.ps1 -Action On
sleep 15

# 1./2. BLE-Handshake als UNBEKANNTER Client
"$PY" -u ble-probe.py --retries 40 --timeout 6 pairing --quick --register skyshutter

# 3./4. Klassisches Bonding, Code an der Kamera bestaetigen
"$PY" -u classic-pair.py --seconds 60 pair
```

Das Skript `tools/` liegt im Repo; die Kopien unter `Temp` sind nötig, weil das
Windows-Python keine WSL-Pfade mag.

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
nach `Off`/`On` sofort wieder alles gefunden. Deshalb steht der Reset an
Position 0 und nicht als Notlösung am Rand.

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

## Was danach offen ist

Nach dem Bonding zeigt die Kamera **„Establishing connection"** und wartet.
Die Referenzimplementierung hält an dieser Stelle einen klassischen
Bluetooth-Serial-Dienst offen und wartet ihrerseits darauf, dass die Kamera
sich verbindet. `tools/rfcomm-listen.py` bietet genau das an (Serial Port,
`00001101-0000-1000-8000-00805f9b34fb`) — **die Kamera verbindet sich
trotzdem nicht.** Woran das liegt, ist die nächste offene Frage.

Ein anschließender *Reconnect*-Handshake mit der beim Pairing vergebenen
Kennung bringt die Kamera zurück ins normale Menü, ohne Fehlermeldung.
