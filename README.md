# Namensschilder

`namensschilder.py` liest `Anmeldungen.csv`, erzeugt XSL-FO und lässt Apache
FOP daraus eine A4-PDF-Druckvorlage erzeugen. Die Seite enthält vier
Namensschilder pro Seite; jedes Schild steht zweimal nebeneinander und ist
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
