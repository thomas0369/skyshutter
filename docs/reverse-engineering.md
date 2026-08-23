# RE-Playbook

Ziel: die offenen Fragen aus [protokoll.md](protokoll.md) mit Messwerten statt
Vermutungen beantworten. Reihenfolge ist bewusst so gewählt, dass jeder Schritt
auch dann etwas liefert, wenn der nächste scheitert.

## Schritt 0 — Ohne Kamera vorbereiten

Der Client lässt sich vollständig gegen den mitgelieferten Simulator entwickeln:

```bash
python -m skyshutter.simulator --port 15740      # Terminal 1
skyshutter --host 127.0.0.1 info                 # Terminal 2
```

Der Simulator bildet den Handshake und die von `skyshutter` benutzten
Operationen nach. Er ist ein Entwicklungswerkzeug, **kein Modell der echten
Kamera** — seine Opcode-Liste ist die typische Nikon-Liste, keine Messung.

## Schritt 1 — Direkter Versuch (5 Minuten)

Bevor irgendetwas mitgeschnitten wird: Kamera in den SnapBridge-Remote-Modus
bringen, mit ihrem WLAN verbinden, und

```bash
skyshutter probe            # sucht 192.168.0.10 / 192.168.1.1 / ...
skyshutter --host 192.168.0.10 probe --ports 15740 80 8080 49152
```

Drei mögliche Ausgänge:

| Ergebnis | Bedeutung |
|---|---|
| Handshake OK | PTP/IP bestätigt → weiter mit `skyshutter info`, Schritt 2 kann entfallen |
| Port offen, `InitFail` | PTP/IP vorhanden, aber GUID nicht gepaart → Schritt 2 (BLE) nötig |
| Port zu, andere Ports offen | anderes Protokoll → Schritt 3 (Mitschnitt) entscheidet |

Bei Erfolg gehört die Ausgabe von `skyshutter info` in `protokoll.md`.

## Schritt 2 — den BLE-Verkehr sehen

> ### ⚠ Der naheliegende Weg funktioniert nicht
>
> ~~Entwickleroptionen → Bluetooth-HCI-Snoop-Log aktivieren, Bugreport ziehen,
> `btsnoop_hci.log` in Wireshark öffnen.~~
>
> **Am 22.08.2026 gemessen und verworfen.** Die Aufzeichnung lief nachweislich
> (`dumpsys bluetooth_manager` meldete `sSnoopLogSettingAtEnable = FULL`), und
> der Bugreport enthielt **310 Snoop-Dateien — alle exakt 16 Byte groß**, also
> nur Header ohne ein einziges Paket. Der Gerätehersteller filtert die Nutzdaten
> über `INIT_gd_hal_snoop_logger_filtering`, und beide Wege, das abzuschalten,
> sind ohne Root gesperrt: `device_config put` scheitert mit `SecurityException`,
> `setprop persist.bluetooth.btsnoopenable` mit `Failed to set property`.
>
> Wer diesem Weg folgt, verliert einen Abend. Details in
> [FINDINGS.md](FINDINGS.md#widerlegtes).

**Was stattdessen funktioniert hat**, in der Reihenfolge des Aufwands:

**a) Selbst mit der Kamera sprechen.** `tools/ble-probe.py` liest den gesamten
GATT-Baum und alle lesbaren Werte aus, ohne Kopplung. Das hat die
Characteristic-Tabelle in [referenz.md](referenz.md) geliefert — vollständiger,
als ein Mitschnitt es gekonnt hätte, weil die Hersteller-App sechs der
Characteristics nie anfasst.

**b) Sich zwischen App und Kamera setzen.** `tools/ble-proxy.py` greift die
Kamera zuerst, wodurch die App nur noch den Proxy findet, und protokolliert
jeden Byte in beide Richtungen. Damit ist der vollständige Handshake der App
gegen die echte Kamera mitgeschnitten.

**c) Die App auseinandernehmen.** Der ergiebigste Weg. Die APK vom eigenen
Gerät ziehen (`adb pull`), mit `baksmali` zerlegen und nach den
UUID-Konstanten suchen:

```bash
adb shell pm path com.nikon.snapbridge.cmru
adb pull <pfad> snapbridge.apk
unzip -o snapbridge.apk -d extracted
java -jar baksmali.jar d extracted/classes.dex -o smali
grep -rl "00002005-3DD4" smali/
```

Das hat den WLAN-Auslöser, das Frame-Format des Livebildes und die
Verschlüsselung der Zugangsdaten ergeben. Rechtlich gedeckt durch **§ 69e
UrhG** — Dekompilierung zur Herstellung der Interoperabilität, wenn die
Informationen nicht anders zugänglich sind. Genau das ist hier belegt.

Gelesen wird zur Verifikation, übernommen wird nichts.

## Schritt 3 — WiFi-Traffic mitschneiden

Die Kamera ist Access Point, das Handy Client — der Traffic läuft also nicht über
das Heimnetz. Zwei Wege:

**A. Auf dem Handy (gerootet oder per PCAP-Droid):**

```bash
tcpdump -i wlan0 -s 0 -w /sdcard/coolpix.pcap host 192.168.0.10
```

**B. Über den GL-X3000 als Zwischenstation:** Router als Client ins Kamera-WLAN
hängen, Handy an den Router, und dort mitschneiden:

```bash
tcpdump -i br-lan -s 0 -w /tmp/coolpix.pcap host 192.168.0.10
```

Auswertung in Wireshark: `tcp.port == 15740`, Dissector „PTP/IP" prüfen
(`Decode As…` falls Wireshark den Port nicht automatisch erkennt). Interessant
sind vor allem `OperationRequest`-Pakete mit Opcodes ≥ `0x9000` — das ist die
Liste dessen, was SnapBridge tatsächlich benutzt.

## Schritt 4 — Gegen die echte Kamera arbeiten

Sobald der Handshake steht, ist `raw` das Arbeitspferd für alles, was noch
unbekannt ist:

```bash
skyshutter info                                  # was kann die Kamera?
skyshutter raw 0x90E0                            # GetDevicePTPIPInfo
skyshutter raw 0x9201                            # StartLiveView
skyshutter raw 0x9203 -o frame.bin               # rohes Live-View-Paket sichern
skyshutter raw 0x1014 0x5005                     # GetDevicePropDesc, z. B. Weißabgleich
skyshutter -v events                             # was meldet die Kamera von sich aus?
```

`frame.bin` zeigt die tatsächliche Header-Länge vor dem JPEG-Marker `FF D8 FF` —
der Wert gehört nach `protokoll.md`.

## Schritt 5 — Ergebnisse festhalten

Jede Messung ändert genau eine Stelle:

* Neue Opcodes/Properties → `docs/protokoll.md`
* Kamera weicht vom PTP/IP-Standard ab → `src/skyshutter/ptpip.py` + Test in
  `tests/test_ptpip.py`, der die Abweichung festnagelt
* Simulator nachziehen, damit die Testsuite die reale Kamera abbildet

## Rechtliches

Reverse Engineering zur Herstellung von Interoperabilität mit selbst gekaufter
Hardware ist in der EU durch Art. 6 der Software-Richtlinie (2009/24/EG) und
§ 69e UrhG gedeckt. Weitergegeben wird hier nur eigener Code und Protokollwissen,
keine Nikon-Software.
