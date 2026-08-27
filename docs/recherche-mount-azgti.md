# Recherche: AZ-GTi-Anbindung (WLAN, Protokoll, Guiding-Tauglichkeit)

Stand: 27.08.2026. Recherche (Web), nicht Messung — alle Punkte sind an
Thomas' echtem Mount nachzumessen, bevor Code darauf baut (Regel 2).

## 1. WLAN-Modi des AZ-GTi

- Werkszustand: Mount ist **Accesspoint** (SSID `SynScan_xxxx`, Passwort
  werkseitig `synscan`, IP 192.168.4.1). Steuergerät verbindet sich direkt.
- **Station Mode** (Mount tritt einem Heimnetz bei) ist offiziell supported:
  SynScan-Pro-App → Settings → Wi-Fi Setting → Station Mode ON, Heim-SSID +
  PSK eintragen, Mount stromlos schalten. Danach holt es sich per DHCP eine
  IP im Heimnetz. (Quelle: Sky-Watcher-Doku + FAQ-Antworten, Rang 2)
- 2,4-GHz-only. Heimrouter mit kombiniertem SSID: Sichtbarkeit prüfen.

## 2. Ports und Protokoll

| Port | Transport | Zweck |
|---|---|---|
| 11880 | TCP **und** UDP | Direkte Kommunikation mit dem Mount-WLAN; lx200-artiges Subset; Motor-Controller-Befehle (Skywatcher-Protokoll `:e#`/`:V`/`:F`/`:J`-Familie) laufen hier über UDP |
| 11882 | TCP | Brücke: IP des Geräts, auf dem die SynScan-App läuft (App als Proxy) |

- lx200-Subset für GOTO/Position: `:GR#` (RA), `:GD#` (Dec), `:Sr#`/`:Sd#`
  (Ziel setzen), `:MS#` (Slew), `:Q#` (Stop). Befehle enden immer auf `#`.
  Koordinatenformat je Firmware `HH:MM.T` oder `HH:MM:SS`.
- GOTO setzt Alignment voraus (App oder Handcontroller).
- Offizielle Primärquelle: „Sky-Watcher Motor Controller Command Set" (PDF,
  skywatcher.com → Application Development). Referenzcode: INDI-Treiber
  (`indi_skywatcherAltAzMount`, github.com/indilib/indi) und EQMOD (SourceForge).
- UDP 11880 = low-level Motorprotokoll (der INDI-Treiber rechnet astronomisch
  selbst, schickt Schritt-/Puls-Befehle). TCP 11880 = lx200-Schicht.

## 3. Guiding-Tauglichkeit (kritischster Punkt)

- **Der AZ-GTi hat keinen ST4-Autoguider-Port.** Guiding läuft als
  **Pulse Guiding** über die Steuerschnittstelle (WLAN oder EQDIR-Kabel).
- **Alt-Az = Feldrotation**: ohne Derotator sind Deep-Sky-Belichtungen über
  ~20–30 s nicht sinnvoll; schon ab dort Trailing am Bildrand. (Konsens
  über alle Quellen.)
- Kleines FOV entschärft das leicht: P1100 (1/2,3") an 3000 mm → Bildfeld
  ≈ 4,3' × 3,2'. Mond/Sonne/Planeten + Stacking: unkritisch. Sterne:
  Rotation wird sichtbar, sobald Belichtung länger als die Toleranz des
  Bildfeldradius ist.
- **EQ-Modus** existiert (Firmware „AZ/EQ Dual Mode" nötig, Windows-Flash):
  Mount auf Keil (Wedge) zur geographischen Breite, Gegengewichtsschiene +
  1–2 kg, in der App beim Start „Equatorial Mode" wählen, polausrichten.
  Dann keine Feldrotation → langzeitfähig. (Mehrfach unabhängig berichtet.)
- Guide Rate muss ≠ 0 sein (typ. 0,5–0,9× siderisch), im Mount-Setup.
- Backlash in Dec erheblich (Einsteigerklasse): unidirektionales Guiding
  als Fallback. (Erfahrungsberichte Cloudy Nights/Stargazers Lounge, Rang 5)
- WLAN-Guiding funktioniert, gilt aber als weniger stabil als EQDIR-Kabel;
  EQDIR = USB-Seriell (FTDI) direkt am Motorcontroller, 9600 8N1.

## 4. Architektur-Entscheid für skyshutter

Empfehlung: **Station Mode (Variante B)** — kein Zweitfunkinterface am Pi.

```
[P1100] --AP--> [Pi wlan0]          (bestehend, flattert, wird geheilt)
[Pi end0] --> [Mango-LAN] --> [Router] --WLAN--> [AZ-GTi Station Mode]
```

- Pi steuert das Mount über end0/LAN → keine zweite Funkstrecke am Pi,
  keine zweite BLE/WLAN-Fehlerquelle am selben Gerät.
- Guiding-Latenz über WLAN (~5–30 ms) ist für 100–500-ms-Pulse unkritisch.
- Fallback/Upgrade-Pfad bleibt EQDIR-Kabel (FTDI), falls WLAN-Guiding der
  Stabilität nicht genügt.
- E1-Nutzungsszenario zunächst Alt-Az + Pixel-Drift-Kompensation (Mond/
  Sonne — rotationsunempfindlich). EQ-Umbau (Wedge + Firmware) als späterer
  Ausbauschritt für Stern-Führung.

## 5. Offen (an echtem Mount zu messen)

1. Station Mode an Thomas' Mount aktivieren; IP im Router NOTIEREN.
2. Was lauscht wirklich: TCP 11880? UDP 11880? Beides? (Quellen uneins)
3. Welche lx200-Befehle antworten (`:GR#`, `:GD#`, `:Me#/:Mw#/:Mn#/:Ms#`,
   `:RG#`, `:Q#`) und in welchem Format?
4. Guide Rate setzen (0,5–0,9×) und Reaktion auf Move-Pulse messen.
5. Firmware-Version: AZ/EQ Dual Mode vorhanden?

## Quellenlage

- Offiziell (Rang 2): Sky-Watcher-Doku/FAQ (Station Mode, Ports,
  Application-Development-PDFs), INDI-Projekt.
- Praxisberichte (Rang 5): Cloudy Nights, Stargazers Lounge, Reddit
  (Feldrotations-Grenzen, EQ-Umbau, Backlash, WLAN-Stabilität).
- Keine der Aussagen ist an Thomas' Mount gemessen — Messliste in §5.
