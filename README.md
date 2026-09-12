# Namensschilder

`namensschilder.py` liest `Anmeldungen.csv`, erzeugt XSL-FO und lässt Apache
FOP daraus eine A4-PDF-Druckvorlage erzeugen. Die Seite enthält drei
Namensschilderzeilen bzw. sechs Schildhälften; jedes Schild ist
103,5 × 74 mm groß.

```sh
uv sync
uv run namensschilder Anmeldungen.csv -o namensschilder.pdf \
  --qr-text 'WIFI:T:WPA;S:Mein-Gastnetz;P:Mein-Passwort;;'
```

Die CSV ist semikolongetrennt und benötigt die Spalten `Name`, `Vorname`,
`Titel` und `Institution / Unternehmen`. Optional können die Spalten `Speaker`
und `QR-Text` angegeben werden. Ein Eintrag in `Speaker` wird magenta,
rechtsbündig neben dem Titel und über dem rechten Rand des Namens ausgegeben.
Die mitgelieferten SVG-Dateien werden direkt in die FO-Ausgabe eingebunden.
Sie liegen im Verzeichnis `assets/`.
`Bild.svg` sollte dabei bereits den
gewünschten Banner-Ausschnitt ohne zusätzlichen Rand enthalten.
Die verwendeten Fira-Sans-Schnitte liegen zusammen mit ihrer OFL-Lizenz im
Verzeichnis `fonts/` und werden von FOP automatisch eingebunden.

Enthält die CSV-Datei die optionale Spalte `QR-Text`, wird für jede Zeile mit
einem Eintrag ein individueller QR-Code aus diesem Feld erzeugt. Fehlt die
Spalte, wird der globale Wert aus `--qr-text` verwendet. Ohne QR-Text und ohne
`--qr-text` wird kein QR-Code ausgegeben. Semikolons im QR-Text müssen wie
üblich in der CSV in Anführungszeichen stehen.

Voraussetzungen:

- [uv](https://docs.astral.sh/uv/)
- Apache FOP im PATH (`fop`)
- Python 3.10 oder neuer (wird von uv verwaltet)
- `libqrencode4` für den QR-Code; mit `--no-qr` kann der QR-Code ausgeblendet
  werden

Für die Kontrolle oder Weiterverarbeitung kann zusätzlich die FO-Datei samt
den erzeugten Hilfsdateien behalten werden:

```sh
uv run namensschilder Anmeldungen.csv -o namensschilder.pdf \
  --fo namensschilder.fo
```

Mit `--no-rotate-back` werden beide Hälften in der Ansicht wie im
Beispielbild ausgegeben. Ohne diese Option ist die zweite Hälfte für das
Umklappen vorgesehen.

Mit `--banner` und `--logos` können eigene Branding-Dateien verwendet werden.
`--logos` erwartet ein JSON-Array, zum Beispiel:

```sh
uv run namensschilder Anmeldungen.csv -o namensschilder.pdf \
  --banner branding/banner.svg \
  --logos '["branding/logo-links.svg", "branding/logo-rechts.svg"]'
```

## Verwendung als GitHub Action

Die Action kann in einem anderen Repository verwendet werden. Der Runner muss
Linux verwenden, zum Beispiel `ubuntu-latest`; FOP, `libqrencode` und die
Python-Abhängigkeit werden von der Action eingerichtet.

```yaml
name: Namensschilder

on:
  workflow_dispatch:
  push:
    paths:
      - "data/anmeldungen.csv"

jobs:
  pdf:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Namensschilder erzeugen
        id: namensschilder
        uses: cgawron/namensschilder@main
        with:
          csv: data/anmeldungen.csv
          banner: branding/banner.svg
          logos: '["branding/logo-links.svg", "branding/logo-rechts.svg"]'
          output: dist/namensschilder.pdf
          # qr-text: "WIFI:T:WPA;S:Mein-Gastnetz;P:Mein-Passwort;;"

      - uses: actions/upload-artifact@v4
        with:
          name: namensschilder
          path: ${{ steps.namensschilder.outputs.pdf }}
```

`csv`, `banner`, `logos` und `output` sind relativ zum Workspace des
aufrufenden Repositories. `logos` ist ein JSON-Array; bei zwei Einträgen wird
der erste links und der zweite rechts platziert. Zusätzlich stehen `qr-text`,
`qr-label`, `no-qr`, `no-rotate-back` und `fo` als Inputs zur Verfügung.
Enthält die CSV die Spalte `QR-Text`, wird deren Wert pro Zeile verwendet;
`qr-text` dient dann nicht als Fallback.
