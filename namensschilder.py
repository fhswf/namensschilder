#!/usr/bin/env python3
"""Erzeugt eine A4-Druckvorlage für gefaltete Namensschilder.

Die eigentliche Seitenausgabe übernimmt Apache FOP. Dieses Programm liest die
Anmeldungen, erzeugt daraus XSL-FO und ruft anschließend FOP auf.
"""

from __future__ import annotations

import csv
import ctypes
import ctypes.util
import html
import re
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import typer


PAGE_WIDTH_MM = 210
PAGE_HEIGHT_MM = 297

CARD_WIDTH_MM = 103.5
CARD_HEIGHT_MM = 74
CARD_MARGIN_MM = 8
BANNER_WIDTH_MM = 103.5
BANNER_HEIGHT_MM = 23.3
NAME_AREA_BOTTOM_MM = BANNER_HEIGHT_MM + 5
NAME_AREA_HEIGHT_MM = CARD_HEIGHT_MM - BANNER_HEIGHT_MM - 24

LOGO_HEIGHT_MM = 10
VDI_LOGO_WIDTH_MM = 16.02
FH_LOGO_WIDTH_MM = 32.36
CARDS_PER_PAGE = 3

PAGE_MARGIN_TOP_MM = (PAGE_HEIGHT_MM - CARDS_PER_PAGE * CARD_HEIGHT_MM) / 2

MAGENTA = "#c00f74"
BLUE = "#004f9f"


class QRCode(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_int),
        ("width", ctypes.c_int),
        ("data", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def xml(value: object) -> str:
    return html.escape(str(value), quote=True)


def file_url(path: Path) -> str:
    """Return a file URL suitable for FOP's url('...') syntax."""
    return path.resolve().as_uri()


def read_registrations(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        if reader.fieldnames is None:
            raise ValueError("Die CSV-Datei enthält keine Kopfzeile.")
        reader.fieldnames = [field.strip() for field in reader.fieldnames]
        required = {"Name", "Vorname", "Titel", "Institution / Unternehmen"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError("Fehlende CSV-Spalten: " + ", ".join(sorted(missing)))

        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {key: (value or "").strip() for key, value in raw.items() if key}
            if not any(row.values()):
                continue
            row["Name"] = row.get("Name", "")
            row["Vorname"] = row.get("Vorname", "")
            row["Titel"] = row.get("Titel", "")
            row["Institution / Unternehmen"] = row.get("Institution / Unternehmen", "")
            rows.append(row)
        return rows


def make_cropped_svg(source: Path, destination: Path, view_box: str, add_dimensions: bool = True) -> None:
    content = source.read_text(encoding="utf-8")
    pattern = r'(<svg\b[^>]*\bviewBox\s*=\s*["\'])[^"\']+(["\'])'
    cropped, count = re.subn(pattern, rf"\g<1>{view_box}\g<2>", content, count=1)
    if count != 1:
        raise ValueError(f"Kein viewBox im SVG gefunden: {source}")
    values = view_box.split()
    if add_dimensions and len(values) == 4:
        width, height = values[2], values[3]
        root_end = cropped.find(">", cropped.find("<svg"))
        root = cropped[:root_end]
        if " width=" not in root:
            cropped = cropped[:root_end] + f' width="{width}" height="{height}"' + cropped[root_end:]
    destination.write_text(cropped, encoding="utf-8")


def make_qr_svg(text: str, destination: Path) -> None:
    library_name = ctypes.util.find_library("qrencode")
    if not library_name:
        raise RuntimeError(
            "Für den QR-Code wird libqrencode benötigt. Installieren Sie z. B. "
            "das Paket 'libqrencode4' oder verwenden Sie --no-qr."
        )

    library = ctypes.CDLL(library_name)
    encode = library.QRcode_encodeString
    encode.argtypes = [
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
    ]
    encode.restype = ctypes.POINTER(QRCode)
    free = library.QRcode_free
    free.argtypes = [ctypes.POINTER(QRCode)]
    free.restype = None

    # version 0 = automatisch, Fehlerkorrekturstufe M, Byte-Modus.
    qr = encode(text.encode("utf-8"), 0, 1, 2, 1)
    if not qr:
        raise RuntimeError("Der QR-Code konnte nicht erzeugt werden.")

    try:
        width = qr.contents.width
        data = qr.contents.data
        quiet = 4
        paths: list[str] = []
        for y in range(width):
            x = 0
            while x < width:
                if not data[y * width + x] & 1:
                    x += 1
                    continue
                start = x
                while x < width and data[y * width + x] & 1:
                    x += 1
                paths.append(f"M {start + quiet} {y + quiet}h {x - start}v 1h {-x + start}z")
        size = width + quiet * 2
        svg = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
            f'width="{size}" height="{size}" shape-rendering="crispEdges">\n'
            f'<rect width="{size}" height="{size}" fill="white"/>\n'
            f'<path fill="black" d="{" ".join(paths)}"/>\n</svg>\n'
        )
        destination.write_text(svg, encoding="utf-8")
    finally:
        free(qr)


def make_rounded_line_svg(destination: Path) -> None:
    """Create the small vector accent used below the name."""
    destination.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 25 1.2" '
        'width="25" height="1.2">\n'
        f'<rect width="25" height="1.2" rx="0.6" fill="{MAGENTA}"/>\n'
        '</svg>\n',
        encoding="utf-8",
    )


def make_fop_config(destination: Path) -> None:
    font_dirs = [
        Path(__file__).resolve().parent / "fonts",
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/liberation"),
        Path("/usr/share/fonts/opentype/futura"),
    ]
    directories = "".join(
        f"<directory recursive=\"true\">{xml(directory)}</directory>"
        for directory in font_dirs
        if directory.is_dir()
    )
    destination.write_text(
        '<?xml version="1.0"?>\n'
        '<fop version="1.0"><renderers><renderer mime="application/pdf">'
        f"<fonts>{directories}</fonts>"
        "</renderer></renderers></fop>\n",
        encoding="utf-8",
    )


def font_size_for_name(name: str) -> str:
    length = len(name)
    if length > 30:
        return "11pt"
    if length > 24:
        return "13pt"
    return "16pt"


def badge_xml(
    row: dict[str, str],
    assets: dict[str, Path],
    qr_path: Path | None,
    qr_label: str,
    rotate: bool,
    show_qr: bool,
) -> str:
    title = row.get("Titel", "")
    speaker = row.get("Speaker", "")
    name = " ".join(part for part in (row.get("Vorname", ""), row.get("Name", "")) if part)
    company = row.get("Institution / Unternehmen", "")
    name_size = font_size_for_name(name)
    rotation = ' fox:transform="rotate(180)"' if rotate else ""

    qr = ""
    if show_qr:
        if qr_path is None:
            raise ValueError("Für dieses Namensschild wurde kein QR-Code erzeugt.")
        qr = f"""
        <fo:block-container position="absolute" right="{CARD_MARGIN_MM}mm" top="41mm" width="20mm" height="5mm">
          <fo:block font-family="Fira Sans" font-size="5.5pt" font-weight="bold" color="#000000" text-align="center">{xml(qr_label)}</fo:block>
        </fo:block-container>
        <fo:block-container position="absolute" right="{CARD_MARGIN_MM}mm" top="20mm" width="20mm" height="20mm">
          <fo:block><fo:external-graphic src="url('{file_url(qr_path)}')" content-width="20mm" content-height="20mm" scaling="non-uniform"/></fo:block>
        </fo:block-container>"""

    heading = ""
    if title and speaker:
        heading = f"""
          <fo:table table-layout="fixed" width="62mm">
            <fo:table-column column-width="47mm"/>
            <fo:table-column column-width="15mm"/>
            <fo:table-body>
              <fo:table-row>
                <fo:table-cell padding="0mm">
                  <fo:block font-family="Fira Sans" font-size="9pt" font-weight="bold" color="{BLUE}" line-height="1.05">{xml(title)}</fo:block>
                </fo:table-cell>
                <fo:table-cell padding="0mm">
                  <fo:block font-family="Fira Sans" font-size="9pt" font-weight="bold" color="{MAGENTA}" line-height="1.05" text-align="right">{xml(speaker)}</fo:block>
                </fo:table-cell>
              </fo:table-row>
            </fo:table-body>
          </fo:table>"""
    elif title:
        heading = f"""
          <fo:block font-family="Fira Sans" font-size="9pt" font-weight="bold" color="{BLUE}" line-height="1.05">{xml(title)}</fo:block>"""
    elif speaker:
        heading = f"""
          <fo:block font-family="Fira Sans" font-size="9pt" font-weight="bold" color="{MAGENTA}" line-height="1.05" text-align="right">{xml(speaker)}</fo:block>"""

    name_area = f"""
        <fo:block-container position="absolute" left="{CARD_MARGIN_MM}mm" bottom="{NAME_AREA_BOTTOM_MM}mm" width="62mm" height="{NAME_AREA_HEIGHT_MM}mm" overflow="hidden" display-align="after">
          {heading}
          <fo:block font-family="Fira Sans" font-size="{name_size}" font-weight="bold" color="{BLUE}" line-height="1.05" space-after="1.1mm">{xml(name)}</fo:block>
          <fo:block font-size="0pt" line-height="1.2mm" space-after="1.8mm"><fo:external-graphic src="url('{file_url(assets['rounded_line'])}')" content-width="25mm" content-height="1.2mm" scaling="non-uniform"/></fo:block>
          <fo:block font-family="Fira Sans" font-size="8.5pt" font-weight="bold" color="#000000" line-height="1.05">{xml(company)}</fo:block>
        </fo:block-container>"""

    return f"""
    <fo:table-cell padding="0mm" margin="0mm" width="{CARD_WIDTH_MM}mm" height="{CARD_HEIGHT_MM}mm"
                   border="0.2pt solid #bcbcbc" keep-together.within-page="always">
      <fo:block-container padding="0mm" margin="0mm" width="{CARD_WIDTH_MM}mm" height="{CARD_HEIGHT_MM}mm" overflow="hidden"{rotation}>
        <fo:block-container position="absolute" left="{CARD_MARGIN_MM}mm" top="3mm" width="{VDI_LOGO_WIDTH_MM}mm" height="{LOGO_HEIGHT_MM}mm">
          <fo:block font-size="0pt"><fo:external-graphic src="url('{file_url(assets['vdi'])}')" content-width="{VDI_LOGO_WIDTH_MM}mm" content-height="{LOGO_HEIGHT_MM}mm" scaling="non-uniform"/></fo:block>
        </fo:block-container>
        <fo:block-container position="absolute" right="{CARD_MARGIN_MM}mm" top="3mm" width="{FH_LOGO_WIDTH_MM}mm" height="{LOGO_HEIGHT_MM}mm">
          <fo:block font-size="0pt"><fo:external-graphic src="url('{file_url(assets['fh'])}')" content-width="{FH_LOGO_WIDTH_MM}mm" content-height="{LOGO_HEIGHT_MM}mm" scaling="non-uniform"/></fo:block>
        </fo:block-container>
        {name_area}
        {qr}
        <fo:block-container padding="0mm" margin="0mm" position="absolute" left="0mm" bottom="0mm" width="{BANNER_WIDTH_MM}mm" height="{BANNER_HEIGHT_MM}mm"><fo:block><fo:external-graphic src="url('{file_url(assets['banner'])}')" content-width="{BANNER_WIDTH_MM}mm" content-height="{BANNER_HEIGHT_MM}mm" scaling="non-uniform"/></fo:block></fo:block-container>
      </fo:block-container>
    </fo:table-cell>"""


def table_xml(
    rows: list[dict[str, str]],
    assets: dict[str, Path],
    qr_paths: list[Path | None],
    options: SimpleNamespace,
    row_offset: int,
) -> str:
    table_rows = []
    for index, row in enumerate(rows):
        qr_path = qr_paths[row_offset + index] if not options.no_qr else None
        show_qr = qr_path is not None
        table_rows.append(
            f"""
            <fo:table-row height="{CARD_HEIGHT_MM}mm">
              {badge_xml(row, assets, qr_path, options.qr_label, False, show_qr)}
              {badge_xml(row, assets, qr_path, options.qr_label, not options.no_rotate_back, show_qr)}
            </fo:table-row>"""
        )
    return f"""
    <fo:table table-layout="fixed" width="207mm" margin-left="1.5mm" margin-top="0.5mm"
              border-collapse="collapse" keep-together.within-page="always">
      <fo:table-column column-width="{CARD_WIDTH_MM}mm"/>
      <fo:table-column column-width="{CARD_WIDTH_MM}mm"/>
      <fo:table-body>{''.join(table_rows)}</fo:table-body>
    </fo:table>"""


def make_fo(
    rows: list[dict[str, str]],
    assets: dict[str, Path],
    qr_paths: list[Path | None],
    options: SimpleNamespace,
) -> str:
    pages = [rows[start : start + CARDS_PER_PAGE] for start in range(0, len(rows), CARDS_PER_PAGE)]
    tables = []
    for index, page_rows in enumerate(pages):
        end = " page-break-after=\"always\"" if index < len(pages) - 1 else ""
        row_offset = index * CARDS_PER_PAGE
        tables.append(f"<fo:block{end}>{table_xml(page_rows, assets, qr_paths, options, row_offset)}</fo:block>")

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<fo:root xmlns:fo="http://www.w3.org/1999/XSL/Format"
         xmlns:fox="http://xmlgraphics.apache.org/fop/extensions">
  <fo:layout-master-set>
    <fo:simple-page-master master-name="a4" page-width="{PAGE_WIDTH_MM}mm" page-height="{PAGE_HEIGHT_MM}mm" margin="0mm">
      <fo:region-body margin="0mm" margin-top="{PAGE_MARGIN_TOP_MM}mm"/>
    </fo:simple-page-master>
  </fo:layout-master-set>
  <fo:page-sequence master-reference="a4">
    <fo:flow flow-name="xsl-region-body" font-family="DejaVu Sans">
      {''.join(tables)}
    </fo:flow>
  </fo:page-sequence>
</fo:root>
'''


def prepare_assets(source_dir: Path, assets_dir: Path) -> dict[str, Path]:
    assets_dir.mkdir(parents=True, exist_ok=True)
    source_assets_dir = source_dir / "assets"
    banner = source_assets_dir / "Bild.svg"
    vdi = source_assets_dir / "VDI_Logo_2022.svg"
    fh = source_assets_dir / "FH-SWF Logo-CMYK.svg"
    rounded_line = assets_dir / "rounded-line.svg"
    make_rounded_line_svg(rounded_line)
    return {"banner": banner, "vdi": vdi, "fh": fh, "rounded_line": rounded_line}


def prepare_qr_assets(
    rows: list[dict[str, str]],
    assets_dir: Path,
    default_qr_text: str | None,
    show_qr: bool,
) -> list[Path | None]:
    if not show_qr:
        return []

    use_row_text = any("QR-Text" in row for row in rows)
    qr_paths: list[Path | None] = []
    for index, row in enumerate(rows, start=1):
        text = row.get("QR-Text", "") if use_row_text else default_qr_text
        if not text:
            qr_paths.append(None)
            continue
        qr_path = assets_dir / f"qr-{index:04d}.svg"
        make_qr_svg(text, qr_path)
        qr_paths.append(qr_path)
    return qr_paths


def run_fop(fop: str, config: Path, fo: Path, pdf: Path) -> None:
    pdf.parent.mkdir(parents=True, exist_ok=True)
    command = [fop, "-c", str(config), "-fo", str(fo), "-pdf", str(pdf)]
    try:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
    except FileNotFoundError as error:
        raise RuntimeError(
            f"Apache FOP wurde nicht gefunden ({fop!r}). Installieren Sie FOP "
            "oder verwenden Sie --fop mit dem Pfad zum fop-Programm."
        ) from error
    if completed.returncode:
        details = (completed.stdout + "\n" + completed.stderr).strip()
        raise RuntimeError(f"Apache FOP ist mit Status {completed.returncode} fehlgeschlagen:\n{details}")


app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)


@app.command()
def generate(
    csv: Path = typer.Argument(..., help="CSV-Datei mit den Anmeldungen"),
    output: Path = typer.Option(Path("namensschilder.pdf"), "--output", "-o", help="Ziel-PDF"),
    fo: Path | None = typer.Option(None, "--fo", help="zusätzlich erzeugte XSL-FO-Datei behalten"),
    fop: str = typer.Option("fop", "--fop", help="FOP-Kommando oder Pfad (Standard: fop)"),
    qr_text: str | None = typer.Option(
        None,
        "--qr-text",
        help="Fallback-Text für den QR-Code ohne QR-Text-Spalte",
    ),
    qr_label: str = typer.Option("Gastzugang WLAN", "--qr-label", help="Beschriftung unter dem QR-Code"),
    no_qr: bool = typer.Option(False, "--no-qr", help="QR-Code und QR-Beschriftung ausblenden"),
    no_rotate_back: bool = typer.Option(
        False,
        "--no-rotate-back",
        help="zweite Schildhälfte nicht um 180 Grad drehen (Ansicht wie im Beispielbild)",
    ),
) -> None:
    options = SimpleNamespace(
        fo=fo,
        fop=fop,
        no_qr=no_qr,
        no_rotate_back=no_rotate_back,
        output=output,
        qr_label=qr_label,
        qr_text=qr_text,
    )
    source_dir = Path(__file__).resolve().parent
    try:
        rows = read_registrations(csv)
        if not rows:
            raise ValueError("Die CSV-Datei enthält keine Anmeldungen.")

        keep_assets = options.fo is not None
        if keep_assets:
            assets_dir = options.fo.resolve().parent / f"{options.fo.stem}-assets"
            context = None
        else:
            context = tempfile.TemporaryDirectory(prefix="namensschilder-")
            assets_dir = Path(context.name)

        try:
            assets = prepare_assets(source_dir, assets_dir)
            qr_paths = prepare_qr_assets(rows, assets_dir, options.qr_text, not options.no_qr)
            fo_content = make_fo(rows, assets, qr_paths, options)
            fo_path = options.fo.resolve() if options.fo else assets_dir / "namensschilder.fo"
            fo_path.parent.mkdir(parents=True, exist_ok=True)
            fo_path.write_text(fo_content, encoding="utf-8")
            config = assets_dir / "fop-config.xml"
            make_fop_config(config)
            run_fop(options.fop, config, fo_path, options.output.resolve())
        finally:
            if context is not None:
                context.cleanup()
    except (OSError, ValueError, RuntimeError) as error:
        typer.echo(f"Fehler: {error}", err=True)
        raise typer.Exit(code=1) from error

    pages = (len(rows) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
    typer.echo(f"{len(rows)} Namensschilder auf {pages} A4-Seite(n): {options.output}")
    if options.fo:
        assets_path = options.fo.resolve().parent / f"{options.fo.stem}-assets"
        typer.echo(f"FO-Datei und verwendete SVG-Hilfsdateien: {options.fo} und {assets_path}/")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
