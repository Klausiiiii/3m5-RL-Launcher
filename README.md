# 3m5 RL Launcher

Der 3m5 Rocket League Launcher – weil der Epic Games Launcher Arsch ist.

Schlanker Desktop-Launcher im 3m5-Look, der den Epic Games Launcher für **Rocket League** ersetzt.
Unter der Haube arbeitet [Legendary](https://github.com/derrod/legendary) (Login, Download, Updates,
Spielstart mit Epic-Auth). Läuft unter **Windows** und **Linux**.

## Funktionen

- Epic-Login (Browser + Code einfügen) oder Übernahme der Anmeldung aus einem installierten Epic Games Launcher
- Rocket League installieren, aktualisieren, reparieren (Dateiprüfung) und deinstallieren
- Vorhandene Installation (z. B. aus dem Epic Games Launcher) übernehmen: Ordner wählen oder automatisch finden, Dateien prüfen, nur Fehlendes nachladen
- Download mit Fortschritt, Abbrechen und Fortsetzen
- Update-Prüfung vor jedem Start
- **Linux:** erkennt automatisch umu-launcher, GE-Proton / Proton (Steam) oder System-Wine und nutzt ein
  eigenes Prefix (`~/.local/share/3m5-rl-launcher/prefix`)

## Installation

### Fertige Builds

Unter *Actions → CI → Artifacts* (bzw. bei Tags unter *Releases*):

- `3m5-rl-launcher-<version>-windows.exe` – einfach starten
- `3m5-rl-launcher-<version>-linux-x86_64.tar.gz` – entpacken (`tar -xzf …`) und `3m5-rl-launcher` starten

### Aus dem Quellcode

```bash
pip install .            # Python >= 3.10
3m5-rl-launcher          # oder: python -m rl_launcher
```

### Linux-Voraussetzungen

Rocket League ist ein Windows-Spiel, du brauchst eine Kompatibilitätsschicht. Empfehlung in dieser Reihenfolge:

1. **[umu-launcher](https://github.com/Open-Wine-Components/umu-launcher)** (`umu-run`) – lädt GE-Proton
   automatisch und wendet Rocket-League-Fixes an. Beste Wahl.
2. **GE-Proton** in `~/.steam/root/compatibilitytools.d/` oder Valve-Proton aus Steam.
3. **System-Wine** (mit DXVK für brauchbare Performance).

Auswahl oder eigener Pfad: *Einstellungen → Wine / Proton*.

Für den Qt-Build unter X11 wird ggf. `libxcb-cursor0` benötigt (`sudo apt install libxcb-cursor0`).

## Benutzung

1. Starten → **Epic-Login im Browser öffnen** → anmelden.
2. Auf der angezeigten JSON-Seite den Wert von `authorizationCode` (oder die ganze Seite) kopieren und einfügen.
3. **INSTALLIEREN** → **SPIELEN**.

### Schon über Epic installiert?

**Vorhandene Installation wählen** statt *INSTALLIEREN*: Der Launcher schlägt eine gefundene Installation vor
(Epic Games Launcher, Heroic, Lutris) oder du wählst den Ordner selbst – egal ob `Epic Games`, `rocketleague` oder
`Binaries/Win64`. Danach werden alle Dateien geprüft (Verify); nur beschädigte oder fehlende Dateien werden
nachgeladen, nichts wird neu installiert. Ist eine neuere Version verfügbar, erscheint anschließend **UPDATE**.
Den Epic Games Launcher kannst du danach deinstallieren – **aber nicht das Spiel darüber**, sonst löscht er die
Dateien.

Rocket League muss in deiner Epic-Bibliothek sein. Falls nicht: im Epic Store kostenlos hinzufügen, dann *Neu laden*.

Fehlersuche: `3m5-rl-launcher --debug` bzw. Log unter *Einstellungen → Log-Ordner öffnen*.
`3m5-rl-launcher --print-launch` zeigt den genauen Startbefehl (Token geschwärzt).

## Dateien

| Was | Linux | Windows |
| --- | --- | --- |
| Launcher-Einstellungen | `~/.config/3m5-rl-launcher/settings.json` | `%APPDATA%\3m5-rl-launcher` |
| Log, Wine-Prefix | `~/.local/share/3m5-rl-launcher/` | `%LOCALAPPDATA%\3m5-rl-launcher` |
| Login & Spieldaten (Legendary) | `~/.config/legendary/` | `%USERPROFILE%\.config\legendary` |
| Spiel (Standard) | `~/Games/rocketleague` | `%USERPROFILE%\Games\rocketleague` |

Login und Installation werden mit einer evtl. vorhandenen Legendary-/Heroic-Installation geteilt – bitte nicht
gleichzeitig damit installieren.

## Entwicklung

```bash
pip install -e .[dev]
QT_QPA_PLATFORM=offscreen pytest
pyinstaller packaging/3m5-rl-launcher.spec   # Binary nach dist/
```

Aufbau (`src/rl_launcher/`):

- `backend.py` – Rocket-League-Logik auf Basis von `LegendaryCore` (Login, Install, Verify, Launch)
- `runners.py` – Erkennung von umu/Proton/Wine und Bau des Startbefehls
- `gui.py`, `theme.py` – PySide6-Oberfläche im 3m5-Theme (Farben von 3m5.de, Schrift Cabin)
- `settings.py` – eigene Einstellungen

## Lizenz & Hinweise

GPL-3.0-or-later (wie Legendary). Schrift *Cabin* unter SIL Open Font License (`assets/fonts/OFL.txt`).
Kein offizielles Produkt von Epic Games oder Psyonix. Rocket League ist eine Marke von Psyonix LLC.
