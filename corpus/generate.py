"""Generate the fictional test corpus in ``corpus/inbox``.

Synthetic examples only: identities and addresses are placeholders.
IBAN-shaped values use deliberately invalid check digits and are not bank
accounts. The generated files are committed, so this only needs to run when
the corpus changes:

    pip install -e ".[dev]" && python corpus/generate.py   # macOS + LibreOffice
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import tempfile
from pathlib import Path

SYNTHETIC = "SYNTHETIC TEST FIXTURE / FIKTIVE TESTDATEN"

INBOX = Path(__file__).parent / "inbox"
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"


def order_folder(folder: Path) -> None:
    """Group from a subfolder: letter (docx) + positions table (xlsx)."""
    from docx import Document
    from openpyxl import Workbook

    folder.mkdir(parents=True)
    letter = Document()
    letter.core_properties.author = "Synthetic fixture generator"
    letter.core_properties.last_modified_by = "Synthetic fixture generator"
    letter.add_paragraph(SYNTHETIC)
    for line in [
        "Beispiel Werkzeuge GmbH · Beispielweg 1 · 00000 Beispielstadt",
        "Muster Baumarkt GmbH, Musterweg 2, 00000 Musterstadt",
        "Beispielstadt, 15.08.2026",
        "Bestellung Nr. NW-2026-0815",
        "Sehr geehrte Damen und Herren,",
        "wir bestellen hiermit die Artikel aus der beigefügten Positionsliste. "
        "Bitte liefern Sie bis spätestens 30.09.2026.",
        "Der Bestellwert beträgt 7.914,00 EUR netto.",
        "Mit freundlichen Grüßen",
        "Alex Beispiel, Einkauf",
    ]:
        letter.add_paragraph(line)
    letter.save(folder / "anschreiben.docx")

    book = Workbook()
    book.properties.creator = "Synthetic fixture generator"
    book.properties.lastModifiedBy = "Synthetic fixture generator"
    sheet = book.active
    sheet.title = "Positionen"
    sheet.append([SYNTHETIC])
    sheet.append(["Pos", "Artikelnummer", "Bezeichnung", "Menge", "Einzelpreis EUR"])
    for column, width in zip("ABCDE", (8, 18, 34, 12, 18), strict=True):
        sheet.column_dimensions[column].width = width
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 1
    for row in [
        (1, "BZ-110", "Bohrmaschine BZ 110", 5, 289.00),
        (2, "AK-18V", "Akkuschrauber 18 V", 12, 149.00),
        (3, "SB-250", "Sägeblatt 250 mm", 40, 23.50),
        (4, "WK-PRO", "Werkzeugkoffer Pro", 6, 623.50),
    ]:
        sheet.append(row)
    book.save(folder / "positionen.xlsx")


def _pdf(path: Path, blocks: list) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

    styles = getSampleStyleSheet()
    story = [Paragraph(SYNTHETIC, styles["Normal"]), Spacer(1, 8)]
    for block in blocks:
        if isinstance(block, list):
            table = Table(block)
            table.setStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)])
            story += [table, Spacer(1, 12)]
        else:
            story += [Paragraph(block, styles["Normal"]), Spacer(1, 8)]
    SimpleDocTemplate(
        str(path), pagesize=A4, author="Synthetic fixture generator", title=SYNTHETIC
    ).build(story)


def order_split_files(root: Path) -> None:
    """Group from groups.yaml via a glob: letter (pdf) + positions (csv)."""
    _pdf(
        root / "bestellung_B-2231_brief.pdf",
        [
            "<b>Beispielbäckerei Muster KG</b>, Demoweg 3, 00000 Musterstadt",
            "An: Muster Handel GmbH, Beispielstraße 4, 00000 Beispielort",
            "Musterstadt, 03.09.2026",
            "<b>Bestellung B-2231</b>",
            "Bitte liefern Sie die Waren aus der separaten Positionsliste "
            "(CSV) am 12.09.2026 an unsere Backstube.",
            "Gesamtbetrag netto: 1.236,40 EUR",
        ],
    )
    with (root / "bestellung_B-2231_positionen.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["artikel", "bezeichnung", "menge", "preis_eur"])
        writer.writerow(["MEH-25", "Weizenmehl Type 550, 25 kg", 20, "18.90"])
        writer.writerow(["ZUC-10", "Zucker, 10 kg", 15, "12.40"])
        writer.writerow(["HEF-1", "Frischhefe, 1 kg", 30, "4.48"])
        writer.writerow(["BUT-5", "Butter, 5 kg", 20, "26.90"])


def invoice_mail(folder: Path) -> None:
    """Group from groups.yaml taking files out of a folder: e-mail + invoice pdf.

    Due date and IBAN are only in the e-mail; number and totals only in the PDF.
    """
    folder.mkdir(parents=True)
    (folder / "2026-09-02_rechnung-4471.eml").write_text(
        "From: Buchhaltung Beispiel IT <buchhaltung@example-it.example>\n"
        "To: Muster Baumarkt <info@example-store.example>\n"
        "Subject: Ihre Rechnung 4471\n"
        "Date: Wed, 02 Sep 2026 09:12:00 +0200\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "Content-Transfer-Encoding: 8bit\n"
        "\n"
        f"{SYNTHETIC}\n\nGuten Tag,\n\n"
        "anbei erhalten Sie unsere Rechnung 4471 für die Wartung Ihres Kassensystems.\n"
        "Bitte überweisen Sie den Betrag bis zum 02.10.2026 auf folgendes Konto:\n"
        "IBAN: DE00 0000 0000 0000 0000 00\n\n"
        "Viele Grüße\nKim Muster\nBeispiel IT-Service GmbH\n",
        encoding="utf-8",
    )
    _pdf(
        folder / "2026-09-02_rechnung-4471.pdf",
        [
            "<b>Beispiel IT-Service GmbH</b>, Musterstraße 5, 00000 Musterstadt",
            "An: Muster Baumarkt GmbH, Musterweg 2, 00000 Musterstadt",
            "<b>Rechnung Nr. 4471</b>",
            "Rechnungsdatum: 02.09.2026",
            [
                ["Leistung", "Menge", "Einzelpreis", "Gesamt"],
                ["Wartung Kassensystem", "14 h", "150,00 €", "2.100,00 €"],
                ["Ersatzteil Bondrucker", "1", "350,00 €", "350,00 €"],
                ["", "", "Netto", "2.450,00 €"],
                ["", "", "USt. 19 %", "465,50 €"],
                ["", "", "Gesamtbetrag", "2.915,50 €"],
            ],
        ],
    )
    (folder / "newsletter_september.html").write_text(
        f"<html><body><p>{SYNTHETIC}</p>"
        "<h1>Beispiel IT Newsletter – September 2026</h1>"
        "<p>Neu im Programm: Cloud-Backups für kleine Betriebe.</p>"
        "<p>Besuchen Sie uns auf der Hausmesse am 24. September.</p>"
        "<p>Abmelden: newsletter@example-it.example</p></body></html>",
        encoding="utf-8",
    )


def invoice_scan(path: Path) -> None:
    """Single file needing OCR: an English invoice as an image."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1240, 1000), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, 30)
    bold = ImageFont.truetype(FONT, 44)
    draw.text((80, 70), "Example Consulting Ltd", font=bold, fill="black")
    lines = [
        "1 Example Street, Sampletown, United Kingdom",
        "",
        "INVOICE",
        "Invoice No.: INV-7731",
        "Invoice date: 21 July 2026",
        "Bill to: Beispiel Werkzeuge GmbH, Beispielstadt",
        "",
        "Workshop facilitation (2 days)          GBP 1,000.00",
        "Travel expenses                           GBP 250.00",
        "",
        "Total due: GBP 1,250.00",
        "Payment due by 20 August 2026",
    ]
    for index, line in enumerate(lines):
        draw.text((80, 160 + index * 52), line, font=font, fill="black")
    draw.text((80, 940), SYNTHETIC, font=ImageFont.truetype(FONT, 20), fill="black")
    image.save(path)


def termination_letter(path: Path) -> None:
    """Single OpenDocument file of a third class."""
    from odfdo import Document, Paragraph

    document = Document("text")
    document.body.append(Paragraph(SYNTHETIC))
    for line in [
        "Robin Beispiel, Beispielallee 6, 00000 Beispielstadt",
        "An: Muster Wartung GmbH, Kundenservice, Demostraße 7, 00000 Beispielstadt",
        "Beispielstadt, 28.09.2026",
        "Kündigung des Wartungsvertrags für das Testgerät DEMO-1",
        "Sehr geehrte Damen und Herren,",
        "hiermit kündige ich den Wartungsvertrag Nr. DEMO-5520 "
        "fristgerecht zum 31.12.2026.",
        "Bitte bestätigen Sie mir den Eingang dieser Kündigung schriftlich.",
        "Mit freundlichen Grüßen",
        "Robin Beispiel",
    ]:
        document.body.append(Paragraph(line))
    document.save(path)


def order_without_number(path: Path) -> None:
    """Single file that should need review: an order with no order number."""
    path.write_text(
        f"{SYNTHETIC}\n\n# Nachbestellung\n\n"
        "Hallo Frau Beispiel,\n\n"
        "wie telefonisch besprochen bestellen wir noch einmal **8 Stück** "
        "Akkuschrauber 18 V (Art. AK-18V) zum bekannten Preis von 149,00 EUR.\n\n"
        "Lieferung bitte bis 15.10.2026.\n\n"
        "Gruß\nSam Muster, Muster Baumarkt GmbH\n",
        encoding="utf-8",
    )


# Near misses for classification: each resembles a class but does not match its
# description, except the fee note, which is an invoice without the word.
NEAR_MISSES = {
    "auftragsbestaetigung_AB-5521.md": (
        "# Auftragsbestätigung AB-5521\n\n"
        "Beispiel Werkzeughandel GmbH · Beispielgasse 8 · 00000 Musterstadt\n\n"
        "An: Muster Baumarkt GmbH, Musterweg 2, 00000 Musterstadt\n\n"
        "Musterstadt, 18.09.2026\n\n"
        "Sehr geehrter Herr Muster,\n\n"
        "vielen Dank für Ihre Bestellung NW-2026-0815 vom 15.08.2026. Wir bestätigen "
        "die Lieferung von 12 Akkuschraubern AK-18V zu je 149,00 EUR netto. "
        "Voraussichtlicher Versand: 25.09.2026.\n\n"
        "Mit freundlichen Grüßen\nVertrieb, Beispiel Werkzeughandel GmbH\n"
    ),
    "gutschrift_GS-118.md": (
        "# Gutschrift GS-118\n\n"
        "Beispiel IT-Service GmbH · Musterstraße 5 · 00000 Musterstadt\n\n"
        "An: Muster Baumarkt GmbH, Musterweg 2, 00000 Musterstadt\n\n"
        "Datum: 30.09.2026\n\n"
        "Zu unserer Rechnung 4471 schreiben wir Ihnen für die nicht erbrachten "
        "Wartungsstunden 2 h × 150,00 EUR = 300,00 EUR zuzüglich 19 % USt. "
        "(57,00 EUR) gut. Der Betrag von 357,00 EUR wird auf Ihr Konto erstattet; "
        "eine Zahlung Ihrerseits ist nicht erforderlich.\n"
    ),
    "zahlungserinnerung_4471.md": (
        "# Zahlungserinnerung\n\n"
        "Beispiel IT-Service GmbH · Musterstraße 5 · 00000 Musterstadt\n\n"
        "Musterstadt, 09.10.2026\n\n"
        "Sehr geehrte Damen und Herren,\n\n"
        "sicher ist es Ihrer Aufmerksamkeit entgangen: Unsere Rechnung 4471 vom "
        "02.09.2026 über 2.915,50 EUR war am 02.10.2026 fällig. Bitte prüfen Sie "
        "den Vorgang. Sollte sich Ihre Zahlung mit diesem Schreiben überschnitten "
        "haben, betrachten Sie es als gegenstandslos.\n\n"
        "Freundliche Grüße\nBuchhaltung, Beispiel IT-Service GmbH\n"
    ),
    "lieferschein_LS-7702.md": (
        "# Lieferschein LS-7702\n\n"
        "Beispielbäckerei Muster KG · Demoweg 3 · 00000 Beispielstadt\n\n"
        "Lieferung zu Bestellung B-2231 vom 03.09.2026, geliefert am 12.09.2026.\n\n"
        "| Artikel | Menge |\n|---|---|\n| MEH-25 Weizenmehl Type 550 | 20 |\n"
        "| ZUC-10 Zucker | 15 |\n| HEF-1 Hefe | 30 |\n| BUT-5 Butter | 20 |\n\n"
        "Ware vollständig und unbeschädigt erhalten: ____________________\n"
    ),
    "honorarnote_2026-17.md": (
        "# Honorarnote Nr. 2026-17\n\n"
        "Mika Beispiel · Fachübersetzungen · Musterallee 9 · 00000 Beispielstadt\n\n"
        "An: Muster Baumarkt GmbH, Musterweg 2, 00000 Musterstadt\n\n"
        "Beispielstadt, 14.10.2026\n\n"
        "Für die Übersetzung Ihres Produktkatalogs (42 Normseiten à 38,00 EUR) "
        "berechne ich 1.596,00 EUR zuzüglich 19 % USt. (303,24 EUR), insgesamt "
        "1.899,24 EUR. Bitte überweisen Sie den Betrag bis zum 28.10.2026 auf "
        "IBAN DE00 0000 0000 0000 0000 01.\n\n"
        "Vielen Dank für den Auftrag!\nMika Beispiel\n"
    ),
}


def near_misses(root: Path) -> None:
    """Text documents that test classification and the verifier's class check."""
    for name, text in NEAR_MISSES.items():
        (root / name).write_text(f"{SYNTHETIC}\n\n{text}", encoding="utf-8")


def _textutil(source: Path, target: Path) -> None:
    """Write legacy .doc/.rtf with macOS textutil (generation only)."""
    fmt = target.suffix.lstrip(".")
    subprocess.run(
        ["textutil", "-inputencoding", "UTF-8", "-convert", fmt,
         "-output", str(target), str(source)],
        check=True,
    )  # fmt: skip


def legacy_order_folder(folder: Path) -> None:
    """Legacy Office group (needs LibreOffice): letter (.doc) + positions (.xls)."""
    import xlwt
    from docx import Document

    folder.mkdir(parents=True)
    letter = Document()
    letter.core_properties.author = "Synthetic fixture generator"
    letter.core_properties.last_modified_by = "Synthetic fixture generator"
    letter.add_paragraph(SYNTHETIC)
    for line in [
        "Beispiel Hotel GmbH · Demoring 10 · 00000 Beispielort",
        "Muster Einrichtung OHG, Musterplatz 11, 00000 Musterort",
        "Beispielort, 07.09.2026",
        "Bestellung SH-0907",
        "Sehr geehrter Herr Muster,",
        "für die Renovierung unserer Gästezimmer bestellen wir die Artikel aus der "
        "angehängten Excel-Liste. Liefertermin: 21.09.2026.",
        "Auftragswert netto: 3.052,00 EUR",
        "Mit freundlichen Grüßen",
        "Elli Beispiel, Hausdame",
    ]:
        letter.add_paragraph(line)
    with tempfile.TemporaryDirectory() as tmp:
        docx_path = Path(tmp) / "bestellung.docx"
        letter.save(docx_path)
        _textutil(docx_path, folder / "bestellung.doc")

    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet("Positionen")
    for column, width in enumerate((20, 36, 14, 22)):
        sheet.col(column).width = width * 256
    rows = [
        (SYNTHETIC,),
        ("Artikel", "Bezeichnung", "Menge", "Preis netto EUR"),
        ("TL-12", "Tischleuchte Messing", 12, 89.00),
        ("SK-40", "Sitzkissen Leinen 40 cm", 40, 24.80),
        ("VS-6", "Vorhangstoff Samt 6 m", 8, 124.00),
    ]
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            sheet.write(r, c, value)
    book.save(str(folder / "positionen.xls"))


def subscription_cancellation(path: Path) -> None:
    """Legacy single file (needs LibreOffice): RTF letter."""
    html = (
        f"<html><body><p>{SYNTHETIC}</p>"
        "<p>Sascha Muster, Beispielpfad 12, 00000 Beispielort</p>"
        "<p>An: Beispielverlag Werkstatt Heute, Leserservice, "
        "Postfach 0001, 00000 Musterstadt</p>"
        "<p>Beispielort, 10.09.2026</p>"
        "<p><b>Kündigung meines Abonnements</b></p>"
        "<p>Sehr geehrte Damen und Herren,</p>"
        "<p>hiermit kündige ich mein Abonnement der Zeitschrift „Werkstatt Heute“ "
        "(Kundennummer WH-88213) zum 31.03.2027.</p>"
        "<p>Mit freundlichen Grüßen<br>Sascha Muster</p>"
        "</body></html>"
    )
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "letter.html"
        source.write_text(html, encoding="utf-8")
        _textutil(source, path)


def quarterly_presentation(path: Path) -> None:
    """A .pptx that matches no class."""
    from pptx import Presentation

    deck = Presentation()
    deck.core_properties.author = "Synthetic fixture generator"
    deck.core_properties.last_modified_by = "Synthetic fixture generator"
    slides = [
        ("Quartalsbericht Q3 2026", "Beispiel Werkzeuge GmbH – Vertrieb Nord"),
        ("Umsatz", "Umsatz +8 % gegenüber Vorjahr\nStärkstes Segment: Akkuwerkzeuge"),
        ("Ausblick Q4", "Neue Filiale in Musterort\nHerbstaktion ab 1. Oktober"),
    ]
    for title, body in slides:
        slide = deck.slides.add_slide(deck.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = body + "\n\n" + SYNTHETIC
    deck.save(path)


def legacy_presentation(path: Path) -> None:
    """Legacy .ppt matching no class; LibreOffice converts it from .pptx."""
    from pptx import Presentation

    soffice = shutil.which("soffice")
    if soffice is None:
        raise SystemExit("generating .ppt needs LibreOffice (soffice)")
    deck = Presentation()
    deck.core_properties.author = "Synthetic fixture generator"
    deck.core_properties.last_modified_by = "Synthetic fixture generator"
    for title, body in [
        ("Messe-Nachbericht Holz & Handwerk 2026", "Stand B12 · 3 Messetage"),
        ("Ergebnisse", "412 Besucher am Stand\n37 qualifizierte Kontakte"),
    ]:
        slide = deck.slides.add_slide(deck.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = body + "\n\n" + SYNTHETIC
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / f"{path.stem}.pptx"
        deck.save(source)
        subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "ppt",
                "--outdir",
                tmp,
                str(source),
            ],
            check=True,
            capture_output=True,
        )
        shutil.move(Path(tmp) / f"{path.stem}.ppt", path)


GROUPS_YAML = """\
# Files that belong together but are not alone in one subfolder.
groups:
  - name: order-B-2231
    files: ["bestellung_B-2231_*"]
  - name: invoice-4471
    files: ["postfach/2026-09-02_rechnung-4471.*"]
"""


# Ruled inventory register forms for ruled tables, marks and verbatim status quotes.
REGISTER_COLUMNS = (40, 90, 270, 360, 555)
# Close header rules, then one row rule directly below the third entry's text.
REGISTER_RULES = (60, 85, 110, 285, 780)
REGISTER_SIZE = (595, 842)
_BLACK, _RED, _BLUE = (0, 0, 0), (220, 30, 30), (30, 30, 160)
REGISTERS = {
    "inventory_sample_scan.pdf": (
        "Beispieldepot",
        "101",
        ("Team Alpha", "Team Beta", "Team Gamma", "Team Delta",
         "Team Epsilon", "Team Zeta"),
        ("Transport", "Wartung", "Material"),
    ),
    "inventory_example_digital.pdf": (
        "Mustermagazin",
        "202",
        ("Team Eta", "Team Theta", "Team Iota", "Team Kappa",
         "Team Lambda", "Team My"),
        ("Versand", "Service", "Zubehör"),
    ),
}  # fmt: skip


def register_pages(name: str) -> list[dict]:
    """Two sections; a row is ``(top, cells, {column: (mark kind, colour)})``."""
    site, sheet, custodians, costs = REGISTERS[name]
    underline, strike = ("underline", _BLACK), ("strike", _RED)
    return [
        {
            "title": f"Inventar von {site}, Blatt {sheet}, Betreuung",
            "header": ("Nr.", "Betreuer", "Quote", "Vermerk"),
            "rows": [
                (130, ("1", custodians[0], "1/2", "Entfernt am"),
                 {1: underline, 3: underline}),
                (146, ("", "", "", "07.04.2016"), {3: underline}),
                (190, ("2", custodians[1], "1/2", "Entfernt"), {1: strike, 3: strike}),
                (270, ("3", custodians[2], "1/4", ""), {}),
                (330, ("4", custodians[3], "1/4", ""), {}),
                (400, ("5", custodians[4], "1/2", "Entfernt"),
                 {1: ("underline", _BLUE), 3: ("underline", _BLUE)}),
                (470, ("6", custodians[5], "1/2", "Erfasst am 22.08.2017"), {}),
            ],
        },
        {
            "title": f"Inventar von {site}, Blatt {sheet}, Kosten",
            "header": ("Nr.", "Vorgang", "Betrag", "Vermerk"),
            "rows": [
                (130, ("1", costs[0], "30.000 DM", "Entfernt am 21.05.2020"),
                 {1: ("cross", _RED)}),
                (190, ("2", costs[1], "3.000 DM", ""), {}),
                (270, ("3", costs[2], "120.000 DM", "Erfasst am 11.11.2019"), {}),
            ],
        },
    ]  # fmt: skip


def register_cell_left(column: int) -> int:
    return REGISTER_COLUMNS[column] + 6


def register_text_width(text: str) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    return stringWidth(text, "Helvetica", 10)


def _mark_line(kind: str, left: float, top: float, width: float) -> tuple:
    """A mark over a text box, in top-left page coordinates."""
    if kind == "underline":
        return (left - 2, top + 11, left + width + 2, top + 11)
    if kind == "strike":
        return (left - 2, top + 5, left + width + 2, top + 5)
    # Long enough for line detection even over a short word.
    return (left - 4, top + 12, left + max(width + 4, 90), top - 2)


def _page_strokes(page: dict) -> list[tuple]:
    """Every text and mark of a page: ``("text", ...)`` or ``("line", ...)``."""
    strokes = [("text", SYNTHETIC, 40, 20), ("text", page["title"], 40, 40)]
    for column, text in enumerate(page["header"]):
        strokes.append(("text", text, register_cell_left(column), 92))
    for top, cells, marks in page["rows"]:
        for column, text in enumerate(cells):
            left = register_cell_left(column)
            if text:
                strokes.append(("text", text, left, top))
            if column in marks:
                kind, colour = marks[column]
                line = _mark_line(kind, left, top, register_text_width(text))
                strokes.append(("line", line, colour))
    return strokes


def _grid_lines() -> list[tuple]:
    top, bottom = REGISTER_RULES[0], REGISTER_RULES[-1]
    left, right = REGISTER_COLUMNS[0], REGISTER_COLUMNS[-1]
    return [(x, top, x, bottom) for x in REGISTER_COLUMNS] + [
        (left, y, right, y) for y in REGISTER_RULES
    ]


def scanned_register(path: Path) -> None:
    """An image-only PDF: faint background, noise and a very slight skew."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen.canvas import Canvas

    scale = 150 / 72
    canvas = Canvas(str(path), pagesize=REGISTER_SIZE)
    canvas.setAuthor("Synthetic fixture generator")
    canvas.setTitle(SYNTHETIC)
    noise = np.random.default_rng(412)
    size = tuple(round(side * scale) for side in REGISTER_SIZE)
    paper = (246, 245, 242)
    for page in register_pages(path.name):
        image = Image.new("RGB", size, paper)
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(FONT, round(10 * scale))
        for line in _grid_lines():
            draw.line([v * scale for v in line], fill=(40, 40, 40), width=2)
        for stroke in _page_strokes(page):
            if stroke[0] == "text":
                _, text, left, top = stroke
                position = (left * scale, top * scale)
                draw.text(position, text, font=font, fill=(30, 30, 30))
            else:
                _, line, colour = stroke
                draw.line([v * scale for v in line], fill=colour, width=3)
        image = image.rotate(0.1, fillcolor=paper)
        grain = noise.normal(0, 4, (size[1], size[0], 1))
        pixels = np.asarray(image, dtype=np.float64) + grain
        image = Image.fromarray(pixels.clip(0, 255).astype(np.uint8))
        with tempfile.TemporaryDirectory() as folder:
            scan = Path(folder) / "scan.jpg"
            image.save(scan, quality=75)
            canvas.drawImage(ImageReader(str(scan)), 0, 0, *REGISTER_SIZE)
        canvas.showPage()
    canvas.save()


def digital_register(path: Path) -> None:
    """Native PDF text with cancellation lines drawn as vector paths."""
    from reportlab.pdfgen.canvas import Canvas

    height = REGISTER_SIZE[1]
    canvas = Canvas(str(path), pagesize=REGISTER_SIZE)
    canvas.setAuthor("Synthetic fixture generator")
    canvas.setTitle(SYNTHETIC)

    def draw(line: tuple, colour: tuple, width: float) -> None:
        canvas.setStrokeColorRGB(*(channel / 255 for channel in colour))
        canvas.setLineWidth(width)
        x0, y0, x1, y1 = line
        canvas.line(x0, height - y0, x1, height - y1)

    for page in register_pages(path.name):
        canvas.setFont("Helvetica", 10)
        for line in _grid_lines():
            draw(line, _BLACK, 1)
        for stroke in _page_strokes(page):
            if stroke[0] == "text":
                _, text, left, top = stroke
                canvas.drawString(left, height - top - 8, text)
            else:
                draw(stroke[1], stroke[2], 1.2)
        canvas.showPage()
    canvas.save()


def generate(inbox: Path) -> None:
    """Build fixtures in a new, empty directory."""
    inbox.mkdir()
    order_folder(inbox / "order-2026-0815")
    order_split_files(inbox)
    invoice_mail(inbox / "postfach")
    invoice_scan(inbox / "invoice_scan_INV-7731.png")
    termination_letter(inbox / "service_cancellation.odt")
    order_without_number(inbox / "nachbestellung.md")
    legacy_order_folder(inbox / "order-L-0907")
    subscription_cancellation(inbox / "kuendigung_abo.rtf")
    quarterly_presentation(inbox / "quartalsbericht_q3.pptx")
    legacy_presentation(inbox / "messebericht_2026.ppt")
    near_misses(inbox)
    scanned_register(inbox / "inventory_sample_scan.pdf")
    digital_register(inbox / "inventory_example_digital.pdf")
    (inbox / "groups.yaml").write_text(GROUPS_YAML, encoding="utf-8")


def main() -> None:
    # Build outside the destination: local caches and private inputs stay intact.
    with tempfile.TemporaryDirectory(prefix="intextum-corpus-") as folder:
        generated = Path(folder) / "inbox"
        generate(generated)
        for source in sorted(generated.rglob("*")):
            if source.is_file():
                target = INBOX / source.relative_to(generated)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                print(f"{target.stat().st_size:>8}  {target.relative_to(INBOX)}")


if __name__ == "__main__":
    main()
