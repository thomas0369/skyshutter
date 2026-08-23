# Werkzeuge

Was hier liegt, gehört nicht zum Client, sondern zur **Messung an echter
Hardware**. Der Client in `src/skyshutter/` kommt mit der Standardbibliothek
aus; diese Werkzeuge brauchen Bluetooth, USB und meistens Windows.

---

## Zuerst: die Plattformfrage

**WSL hat keinen Bluetooth-Zugang.** Es gibt kein `hci0`, keinen BlueZ-Stack,
nichts. Alle BLE-Werkzeuge laufen deshalb unter dem **Windows-Python**, nicht
unter dem aus WSL — auch wenn man sie aus einer WSL-Shell heraus startet.

```bash
# unter Windows, einmalig:
pip install bleak pycryptodome winrt-runtime \
    winrt-Windows.Devices.Bluetooth \
    winrt-Windows.Devices.Bluetooth.GenericAttributeProfile \
    winrt-Windows.Devices.Bluetooth.Rfcomm \
    winrt-Windows.Devices.Enumeration \
    winrt-Windows.Devices.Radios \
    winrt-Windows.Foundation \
    winrt-Windows.Networking.Sockets \
    winrt-Windows.Storage.Streams
```

Kürzer, wenn das Repo unter Windows ausgecheckt ist: `pip install -e '.[windows]'`.

Für USB genügt der Linux-Python in WSL: `pip install -e '.[usb]'`, dazu
`usbipd-win` auf der Windows-Seite, um das Gerät durchzureichen.

| Werkzeug | Läuft unter | Braucht |
|---|---|---|
| `ble-probe.py` | **Windows-Python** | `bleak`, `pycryptodome` |
| `classic-pair.py` | **Windows-Python** | `winrt-*` |
| `ble-proxy.py` | **Windows-Python** | `bleak` **und** `winrt-*` |
| `ble-camera-sim.py` | **Windows-Python** | `winrt-*`, `pycryptodome` |
| `rfcomm-listen.py` | **Windows-Python** | `winrt-*` |
| `bt_state.ps1` | PowerShell | — |
| `pair.sh` | WSL-Bash | ruft die obigen auf |
| `nikon_pairing.py` | überall | `pycryptodome` |
| `first-contact.sh` | WSL-Bash | der installierte Client |

---

## Der übliche Weg

### 1. Koppeln

```bash
bash tools/pair.sh
```

Macht alles und sagt an, wann jemand am Gerät stehen muss: Funk zurücksetzen,
Kameramenü öffnen, BLE-Handshake, klassisches Bonding, Zahlencode bestätigen.
Dauert rund 40 Sekunden, wenn es läuft.

Am Ende gibt es eine **Kennung** aus (`device=…`, `nonce=…`). Die gehört
notiert — Reconnect und WLAN-Start brauchen sie, und sie wechselt bei jeder
neuen Kopplung.

Findet das Skript das Windows-Python nicht, hilft
`SKYSHUTTER_WINPY=/mnt/c/.../python.exe bash tools/pair.sh`.

Was dabei schiefgehen kann und warum, steht in
[docs/pairing.md](../docs/pairing.md) — sechs Fallen, alle einzeln erlebt.

### 2. Nachsehen, was die Kamera anbietet

```bash
python ble-probe.py scan                    # sendet sie überhaupt?
python ble-probe.py dump                    # GATT-Baum
python ble-probe.py session --seconds 0     # alle lesbaren Werte
```

### 3. Das WLAN starten

```bash
python ble-probe.py pairing --quick --device DDDDDDDD --nonce NNNNNNNN --establish 01
```

`--establish 01` schreibt das Byte auf `0x2005`, das laut Herstellercode den
Access Point öffnet. **Wirkung an der Hardware noch nicht bestätigt** — das ist
das offene Gate des Projekts.

### 3b. Die WLAN-Zugangsdaten mitschreiben und entschlüsseln

Beim Koppeln die Handshake-Werte und den `0x2004`-Blob sichern, dann
entschlüsseln — das Passwort der Kamera wechselt, aber es lässt sich aus dem
Mitschnitt zurückrechnen:

```bash
python ble-probe.py pairing --register skyshutter --pairing-json pairing.json
skyshutter wifi pairing.json          # gibt SSID und Passwort aus
```

Der Krypto-Weg steckt in `src/skyshutter/lssec.py`, verifiziert gegen echte
Hardware. Kein Gerätegeheimnis nötig.

### 4. Über USB messen, ohne WLAN

```bash
usbipd list                                    # Windows, Bus-ID der Kamera finden
usbipd bind --busid <id>                       # einmalig, Adminrechte
usbipd attach --wsl --busid <id>               # bei jedem Anstecken
sudo chmod 666 /dev/bus/usb/001/<n>            # udev läuft in WSL nicht
python -c "from skyshutter.ptpusb import PtpUsbConnection; ..."
```

Über USB funktioniert alles außer Live View — die Kamera zieht beim Anstecken
das Objektiv ein und sperrt es. Das ist keine Fehlfunktion, sondern Absicht;
Beleg in [docs/referenz.md](../docs/referenz.md), Abschnitt USB.

---

## Die einzelnen Werkzeuge

**`ble-probe.py`** — das Arbeitspferd. Scannen, GATT-Baum ausgeben, Werte
lesen, Benachrichtigungen mitschneiden, den vierstufigen Handshake fahren,
koppeln, entkoppeln, einzelne Bytes schreiben. Sucht die Kamera **immer über
die Service-UUID**, nie über den Namen — der ist im Advertising abgeschnitten.

**`classic-pair.py`** — die zweite Hälfte der Kopplung. Der BLE-Handshake
allein registriert niemanden; erst das klassische Bonding trägt den Client in
die Geräteliste der Kamera ein. Erkennt sie an der Geräteklasse `0x080620`,
weil Windows den Namen oft nicht auflöst.

**`ble-proxy.py`** — hängt sich zwischen die Hersteller-App und die Kamera und
protokolliert jeden Byte. Greift die Kamera zuerst, damit die App sie nicht
mehr findet. Hat den vollständigen Handshake der App gegen die echte Kamera
mitgeschnitten.

**`ble-camera-sim.py`** — spielt die Kamera für die App. Beantwortet den
Handshake selbst. Stößt an eine Grenze: Windows nimmt seinen klassischen
Bluetooth-Namen zwingend vom Rechnernamen, deshalb kann der Doppelgänger nicht
gleichzeitig unter dem Kameranamen auffindbar sein.

**`nikon_pairing.py`** — der Handshake als Bibliothek, ohne Bluetooth.
Verkettetes Blowfish, acht Salt-Paare, beide Richtungen. Von den anderen
Werkzeugen eingebunden, einzeln testbar.

**`rfcomm-listen.py`** — bietet einen seriellen Dienst an, zu dem die Kamera
sich verbinden könnte. Tut sie nicht; sie bietet ihrerseits nur Apples
Zubehörkanal an. Bleibt als dokumentierter Irrweg liegen.

**`bt_state.ps1`** — Funk aus, Funk an. Klingt trivial, ist es nicht: Nach
mehreren Verbindungszyklen findet der Windows-Stack gar nichts mehr, auch keine
Geräte in Reichweite. Ohne diesen Reset scheiterten fünf Kopplungsversuche in
Folge.

**`first-contact.sh`** — für den Moment, in dem der Rechner ins Kamera-WLAN
wechselt und dabei die Verbindung zur Außenwelt verliert. Wartet auf den
Netzwechsel, misst selbstständig, wartet auf die Rückkehr und legt das Ergebnis
in `measurements/` ab. Gedacht für den Fall, dass niemand am Terminal sitzt.

---

## Sicherheitsregeln

Diese Werkzeuge sprechen mit echter Hardware, die sich nicht ersetzen lässt.

1. **Nur Operationen, die in `operations_supported` stehen.** Keine
   Opcode-Sweeps, kein Durchprobieren.
2. **Schreibende Operationen** (`Set*`, `Delete*`, `Format*`, `Firmware*`) nur
   nach ausdrücklicher Absprache. `0x100F FormatStore` steht in der Liste der
   Kamera — es anzufassen wäre unumkehrbar.
3. **Jede Messung wird festgehalten** — in `docs/FINDINGS.md`, von einem Test
   festgenagelt und im Simulator nachgezogen. Ein Simulator, der von der
   Realität abweicht, gilt als Fehler.

Mitschnitte können SSID, Passphrase, Kopplungskennung und Seriennummer
enthalten. `captures/` ist deshalb bis auf verschlüsselte Archive gesperrt.
