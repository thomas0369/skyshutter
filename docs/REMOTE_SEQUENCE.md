# Fernaufnahme-Startsequenz (P1100) — aus dem Mitschnitt rekonstruiert

Quelle: `adb`-btsnoop einer **funktionierenden** SnapBridge-Fernaufnahme
(23.08.2026) + dekompilierte App, ausgewertet durch einen Multi-Agenten-Deep-Dive
(6 Miner, Synthese, 3 adversarische Verifizierer, Gap-Fill). Jeder Schritt ist im
btsnoop (Zeitstempel) oder im Smali (`Datei:Zeile`) belegt; Unbelegtes ist als
**[GAP]** markiert.

> **Zwei Korrekturen gegenüber früheren Session-Schlüssen — beide belegt:**
> 1. **`0x2001` = `0x03` ist `VALID_WAKE`, nicht `INVALID_WAKE`.** Wire-Werte des
>    Enums (Feld `a`/`getByte` in `BlePowerControlData$Types.smali`): STOP=0,
>    WAKE_WAIT=1, INVALID_WAKE=2, **VALID_WAKE=3**. Die frühere „INVALID_WAKE ist
>    das Gate"-Erzählung beruhte auf den Java-**Ordinalen** (1/2/3/4) — falsch.
>    **Die Kamera war bei unseren Tests bereit.**
> 2. **Es gibt KEINEN RFCOMM/SPP-Datenkanal zur Kamera.** Die RFCOMM-Verbindung
>    zu `5e8945b0-9525-11e3-a5e2-0800200c9a66` im Mitschnitt ging an eine
>    **Samsung „Watch Ultra"** (`…2d:4c`, dev_class 28:07:04) — `5e8945b0` ist
>    eine Samsung-UUID, keine Nikon. Die Kamera (`…4f:fe`, dev_class 08:06:20)
>    macht nur einen klassischen **createBond** (SSP), keinen Datenkanal.
>    `tools/rfcomm-connect.py` zielt damit auf das falsche Gerät.

## Transport-Architektur (korrigiert)

- **BLE (LSS/GATT), unverschlüsselt** — Steuerung, Auth, WLAN-Auslöser.
- **Bluetooth Classic — nur `createBond` (SSP)** zur Kamera, kein Datenkanal.
- **WLAN (WiFi-Direct)** — Live View via PTP/IP. AP-Zugangsdaten kommen über die
  BLE-Charakteristik `0x2004` (SSID+Passwort), entschlüsselt mit `lssec.py`.

## Handle-Karte (aus dem Mitschnitt)

Value-Handles: `0x2b`=2000 AUTH · `0x2e`=2001 POWER · `0x30`=2002 NAME ·
`0x34`=2004 CONFIG · `0x36`=2005 ESTABLISHMENT · `0x38`=2006 TIME ·
`0x3c`=2008 CONTROL_POINT · `0x3f`=2009 FEATURE · `0x45`=2080 CATEGORY.
CCCDs: `0x2c`=2000, `0x3d`=2008.

## Die Sequenz

| # | Transport | Operation | Wert | Beleg |
|---|---|---|---|---|
| 1 | BLE | Connect zur Kamera-RPA, **kein** LE-Pairing/-Encryption | Plaintext-Link | `BleConnection.smali:1318` connectGatt transport=LE; kein `encryption_change` im Log |
| 2 | BLE | CCCD `0x2008` → **Notify** | `01 00` | btsnoop CCCD `0x003d`=0x0100 |
| 3 | BLE | CCCD `0x2000` → **Indicate** | `02 00` | btsnoop CCCD `0x002c`=0x0200; Auth-Antworten kommen als **Indications** |
| 4 | BLE | AUTH Stufe 1 auf `0x2000` | 17 B `[01][nonce:8][deviceId:8]` **[GAP: Werte nicht im Log]** | `b.smali` 17-B-Codec; Kamera-Indication = Stufe 2 |
| 5 | BLE | AUTH Stufe 3 auf `0x2000` | 17 B `[03][…]` via `IBleLssSecret.stage3` **[GAP: Werte]** | `a.smali` lssAuthProc; Stufe 4 → `generateKey`==0 |
| 6 | BLE | READ-Burst: FEATURE `0x2009`, CATEGORY `0x2080`, POWER `0x2001` | — (POWER liest **`0x03`=VALID_WAKE**) | 27× GATTC_Read; **[GAP: welcher Read welchen Handle trifft, nicht geloggt]** |
| 7 | BLE | Write NAME `0x2002` | 32-B-Puffer, UTF-8, null-gepaddet | `BleConnection.pairing()`; Serializer allocate 0x20 |
| 8 | BLE | Write TIME `0x2006` (nur im frühen Zyklus) | 10 B LE `[year:i16][mon][day][h][m][s][…]` | Serializer allocate 0xA |
| 9 | CLASSIC | **`createBond()`** auf Kamera-Classic `…4f:fe` (transport=0), SSP | Bond, `SET_CONNECTION_ENCRYPTION` key_size 16, link_key 0x8 | btsnoop createBond→encrypt 16:35:27→35; `V1.smali:772` BtcPairingUseCase; danach Classic-Link getrennt |
| 10 | BLE | Frischer Reconnect: 2–7 erneut, dann **ESTABLISHMENT `0x2005`** | **`0x01` = WiFi** (bit0=WiFi, bit1=BT, bit7=notRequired) | `m.smali:113` `(bt<<1)\|wifi\|(nr<<7)`; Gap-Fill bestätigt bit0=WiFi |
| 11 | WIFI | WiFi-Direct zur Kamera-AP; Host-IP = `DhcpInfo.serverAddress` | **[GAP: SSID/Pass + AP-Trigger nicht im BT-Log]** (Creds via `0x2004`) | `Q3.smali:335` WiFiDirectUseCase, `:785` getDhcpInfo |
| 12 | WIFI | PTP/IP: COMMAND-Socket `host:15740`, Init_Command_Request (GUID+Name) | Port 15740; GUID `00112233-…-EEFF`; Name „Android Device" | `ConnectWifiAction.smali:68/72/80` |
| 13 | WIFI | EVENT-Socket `host:15740`, Init_Event_Request; dann OpenSession + GetDeviceInfo | connection number aus 12 | `ConnectWifiAction.call()`; `m7`/`h2` |
| 14 | WIFI | **StartLiveView `0x9201`**; dann Frames pollen: **`0x9428` GetLiveViewImageEx** (bevorzugt) oder `0x9202`; DeviceReady `0x90C2` | JPEG via `LiveViewInfo.getJpegData()` (jpeg-/whole-size, Display-/AF-Rechtecke) | `pd.smali:29`=0x9201, `b4.smali:29`=0x9428, `f1.smali:29`=0x9202, `j0.smali:29`=0x90C2 |
| 15 | WIFI | **EndLiveView `0x9203`** | Stopp | `c4.smali:29`=0x9203 |

## Was das für unseren Client bedeutet

- **Kein Wake-Problem.** Die Kamera war bereit (`VALID_WAKE`). Der AP blieb bei
  unseren Tests aus **nicht** wegen `INVALID_WAKE`.
- **Kein RFCOMM zur Kamera nötig.** Der Classic-Teil ist nur ein `createBond`.
- **Vermutliche echte Lücken unseres Versuchs** (zu testen): (a) wir setzten die
  **CCCDs** (Indicate `0x2000`, Notify `0x2008`) nie; (b) der Establishment-Write
  gehört in **eine frische, vollständige In-Session-Kette** (CCCDs → Auth →
  Config-Read → Name → `0x2005`), mit vorhandenem Classic-**Bond**; (c) nach
  `0x2005` muss der Rechner der Kamera-**WiFi beitreten** (Creds aus `0x2004`),
  nicht nur scannen — der AP ist WiFi-Direct.

## Offene Punkte, die NUR die Hardware/ein WiFi-Mitschnitt klärt

- AUTH-Payload-Werte, TIME/NAME-Bytes (Struktur bekannt, Werte live).
- AP-SSID/Passwort + der genaue WiFi-Bring-up nach `0x2005` (BT-Log endet dort;
  ein WLAN-seitiger Mitschnitt oder ein Hardware-Lauf zeigt es).
- Welcher der 27 READs `0x2001` trifft (Read-Handles nicht geloggt).
