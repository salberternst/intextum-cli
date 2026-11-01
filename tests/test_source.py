from intextum_cli.convert import ConvertedFile
from intextum_cli.source import build_source, locate, locate_quotes, select_source_pages


def test_files_are_labelled_and_pages_tracked():
    source = build_source(
        [
            ConvertedFile("letter.pdf", ["Dear Sir", "Total due: 120 EUR"], paged=True),
            ConvertedFile("broken.pdf", error="conversion failed"),
            ConvertedFile("positions.xlsx", ["| Widget | 100 |"]),
        ],
        max_chars=10_000,
    )
    assert source.text.startswith("=== FILE: letter.pdf ===\n=== PAGE: 1 ===\nDear Sir")
    assert "=== FILE: positions.xlsx ===\n| Widget | 100 |" in source.text
    assert "broken.pdf" not in source.text
    assert [(s.file, s.page) for s in source.segments] == [
        ("letter.pdf", 1),
        ("letter.pdf", 2),
        ("positions.xlsx", None),
    ]
    assert source.truncated_files == []

    _, evidence = locate("Total due:", source)
    assert evidence["file"] == "letter.pdf" and evidence["page"] == 2
    _, evidence = locate("Widget", source)
    assert evidence == {
        "file": "positions.xlsx",
        "page": None,
        "snippet": "Widget | 100 |",
    }


def test_truncation_keeps_small_files_whole():
    long_letter = ConvertedFile("letter.pdf", ["x" * 5_000])
    small_table = ConvertedFile("table.xlsx", ["| a | 1 |"])
    source = build_source([long_letter, small_table], max_chars=1_000)
    assert "| a | 1 |" in source.text
    assert source.truncated_files == ["letter.pdf"]
    assert sum(s.end - s.start for s in source.segments) == 1_000


def test_locate_ignores_headers_tolerates_whitespace_and_respects_start():
    source = build_source(
        [
            ConvertedFile(
                "Invoice.pdf", ["Invoice   No.\n42", "item A", "item A"], paged=True
            )
        ],
        max_chars=10_000,
    )
    assert locate("Invoice.pdf", source) is None
    _, evidence = locate("invoice no. 42", source)
    assert evidence["page"] == 1
    first, _ = locate("item A", source)
    second, evidence = locate("item A", source, start=first + 1)
    assert second > first and evidence["page"] == 3
    assert locate("not there", source) is None
    assert locate("", source) is None


def test_locate_matches_table_rows_across_cells_and_garbled_characters():
    source = build_source(
        [
            ConvertedFile("letter.docx", ["Müller Beispieltechnik GmbH, Musterstadt"]),
            ConvertedFile(
                "positions.xlsx",
                [
                    "| Pos | Artikel |\n|   1 | HX-200          | Hydraulikzylinder 200mm |"
                ],
            ),
        ],
        max_chars=10_000,
    )
    _, evidence = locate("HX-200 Hydraulikzylinder 200mm", source)
    assert evidence["file"] == "positions.xlsx"
    assert evidence["snippet"].startswith("HX-200")
    _, evidence = locate("M\x0fller Beispieltechnik", source)
    assert evidence["file"] == "letter.docx"


def test_locate_ignores_markdown_markup():
    source = build_source(
        [
            ConvertedFile(
                "order.md", ["wir bestellen **8 Stück** Akkuschrauber, Art. AK\\_18"]
            )
        ],
        max_chars=10_000,
    )
    _, evidence = locate("8 Stück Akkuschrauber", source)
    assert evidence["snippet"].startswith("8 Stück**")
    assert locate("Art. AK_18", source) is not None


def test_page_selection_preserves_original_page_offsets_and_ignores_labels():
    source = build_source(
        [
            ConvertedFile(
                "register.pdf",
                [
                    "Bestandsverzeichnis: neu vorgetragen",
                    "Erste Abteilung: Alex Beispiel",
                    "Kosten: entfernt",
                ],
                paged=True,
                document_key="key",
                elements=[{"page_index": 1, "start": 0, "end": 30, "ref": "#/texts/4"}],
            )
        ],
        max_chars=60000,
    )
    selected = select_source_pages(source, "Erste Abteilung")
    assert "Bestandsverzeichnis" not in selected.text
    assert "Kosten" not in selected.text
    _, evidence = locate("Alex Beispiel", selected)
    assert evidence["page"] == 2 and evidence["element_refs"] == ["#/texts/4"]
    assert locate("=== PAGE: 2 ===", selected) is None
    assert not select_source_pages(source, "Dritte Abteilung").segments


def test_quote_continues_down_column_with_original_page_and_element_reference():
    page = (
        "Bestandsverzeichnis\n| Nummer | Vermerk |\n|---|---|\n"
        "| 1,2 | Die alten Einträge werden nach Berichti- |\n"
        "| 4,5 | gung unter neuen Nummern vorgetragen. |"
    )
    source = build_source(
        [
            ConvertedFile(
                "register.pdf",
                ["Titel", page],
                paged=True,
                document_key="document",
                elements=[
                    {
                        "page_index": 1,
                        "start": page.index("| Nummer"),
                        "end": len(page),
                        "ref": "#/tables/1",
                    }
                ],
            )
        ],
        max_chars=60000,
    )
    source = select_source_pages(source, "Bestandsverzeichnis")
    quote = (
        "Die alten Einträge werden nach Berichti- gung unter neuen Nummern vorgetragen."
    )
    assert locate(quote, source) is None
    [(position, evidence)] = locate_quotes(quote, source)
    assert source.text[position:].startswith("Die alten Einträge")
    assert evidence["page"] == 2
    assert evidence["document_key"] == "document"
    assert evidence["element_refs"] == ["#/tables/1"]


def test_quote_does_not_jump_between_columns_tables_or_pages():
    source = build_source(
        [
            ConvertedFile(
                "register.pdf",
                [
                    "| 1 | Alpha Anfang |\n| 2 | Beta Ende |\n\n| 3 | Gamma Schluss |",
                    "| 4 | Delta Fortsetzung |",
                ],
                paged=True,
            )
        ],
        max_chars=60000,
    )
    assert locate_quotes("Alpha Anfang Beta Ende", source)
    assert locate_quotes("Alpha Anfang 2", source)  # Literal row text.
    assert not locate_quotes("1 Beta Ende", source)
    assert not locate_quotes("Beta Ende Gamma Schluss", source)
    assert not locate_quotes("Gamma Schluss Delta Fortsetzung", source)
    assert not locate_quotes("", source)


def test_quote_column_matching_keeps_hyphens_and_escaped_pipes():
    source = build_source(
        [
            ConvertedFile(
                "register.pdf", ["| 1 | Berichti- mit A\\|B |\n| 2 | gung bestätigt. |"]
            )
        ],
        max_chars=60000,
    )
    assert locate_quotes("Berichti- mit A|B gung bestätigt.", source)
    assert not locate_quotes("Berichtigung bestätigt.", source)


def test_quote_may_join_a_word_divided_at_a_line_or_row_break():
    source = build_source(
        [
            ConvertedFile(
                "register.pdf",
                [
                    "| 1a) | Alex Example, | Zu 1a): Ohne Eigentums- |\n"
                    "| | - zu 1/2 - | wechsel; eingetragen. |\n\n"
                    "Note: entered after correc-\ntion of the code."
                ],
            )
        ],
        max_chars=60000,
    )
    assert locate_quotes("Zu 1a): Ohne Eigentumswechsel", source)
    assert locate_quotes("entered after correction of the code", source)
    assert locate_quotes("Alex Example, - zu 1/2 -", source)
    assert not locate_quotes("Ohne Eigentumsrecht", source)
