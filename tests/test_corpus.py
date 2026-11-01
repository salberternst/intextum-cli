"""Keep the test corpus, its schemas and expected.yaml consistent (no model needed)."""

import importlib.util
import re
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from pathlib import Path
from types import SimpleNamespace

import pypdfium2 as pdfium
import pytest
import yaml
from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DoclingDocument,
    ImageRef,
    ProvenanceItem,
    Size,
)
from docling_core.types.doc.page import BoundingRectangle, TextCell

from intextum_cli.conversion_marks import MARK_TAGS, mark_cancellations
from intextum_cli.conversion_tables import restore_ruled_tables
from intextum_cli.groups import discover_groups
from intextum_cli.schema import find_class, load_classes

CORPUS = Path(__file__).parents[1] / "corpus"


def load_score_module():
    spec = importlib.util.spec_from_file_location("score", CORPUS / "score.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_expected_groups_classes_and_fields_exist():
    expected = yaml.safe_load((CORPUS / "expected.yaml").read_text(encoding="utf-8"))
    groups = discover_groups(CORPUS / "inbox")
    assert sorted(g.name for g in groups) == sorted(expected)
    classes = load_classes(CORPUS / "schemas")
    for name, group in expected.items():
        if group["class"] is None:
            continue
        document_class = find_class(classes, group["class"])
        assert document_class is not None, name
        field_names = {field.name for field in document_class.fields}
        assert set(group.get("data") or {}) <= field_names, name


def test_score_matching_rules():
    matches = load_score_module().matches
    assert matches("Beispielbäckerei  Muster KG", "beispielbäckerei muster kg")
    assert matches(
        {"amount": 1236.4, "currency": "EUR"}, {"amount": 1236.40001, "currency": "EUR"}
    )
    assert matches([{"quantity": 5}], [{"quantity": 5, "description": "extra keys ok"}])
    assert not matches([{"quantity": 5}], [{"quantity": 5}, {"quantity": 6}])
    assert matches(None, None) and matches(None, [])
    assert not matches("4471", 4471)


def test_score_reads_database_and_exported_json_equally(tmp_path, monkeypatch):
    from intextum_cli.exports import export_workspace
    from intextum_cli.store import WorkspaceStore

    scorer = load_score_module()
    expected = tmp_path / "expected.yaml"
    expected.write_text("invoice:\n  class: Invoice\n  data: {number: RE-1}\n")
    monkeypatch.setattr(scorer, "EXPECTED", expected)
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    store.results.save(
        {
            "group": "invoice",
            "status": "completed",
            "files": [],
            "class": {"name": "Invoice"},
            "data": {"number": "RE-1"},
            "fields": {},
            "review_reasons": [],
            "needs_review": False,
        },
        [],
    )
    export_workspace(store, tmp_path / "exports", "json")
    assert scorer.score(store.path) == scorer.score(tmp_path / "exports")
    passed, total, _ = scorer.score(store.path)
    assert passed == total and total > 0


def load_generate_module():
    spec = importlib.util.spec_from_file_location("generate", CORPUS / "generate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_regeneration_preserves_unrelated_local_files(tmp_path, monkeypatch):
    generator = load_generate_module()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    local = inbox / "local.txt"
    local.write_text("Local input")
    cached = inbox / ".intextum" / "cache"
    cached.parent.mkdir()
    cached.write_bytes(b"Local cache")
    fixture = inbox / "fixture.txt"
    fixture.write_text("Old fixture")

    def generate(destination):
        destination.mkdir()
        (destination / "fixture.txt").write_text("Updated fixture")

    monkeypatch.setattr(generator, "INBOX", inbox)
    monkeypatch.setattr(generator, "generate", generate)
    generator.main()
    assert fixture.read_text() == "Updated fixture"
    assert local.read_text() == "Local input"
    assert cached.read_bytes() == b"Local cache"


def test_corpus_email_and_accounts_are_explicit_placeholders():
    for path in (CORPUS / "inbox").rglob("*.eml"):
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        addresses = getaddresses([str(message["From"]), str(message["To"])])
        assert addresses
        assert all(address.endswith(".example") for _, address in addresses)
        assert "SYNTHETIC TEST FIXTURE" in message.get_content()
    expected = (CORPUS / "expected.yaml").read_text()
    accounts = re.findall(r"iban: (DE\d{2}(?: \d{2,4})+)", expected)
    assert accounts
    assert all(account.startswith("DE00 ") for account in accounts)


def register_text(left, top, width, value, from_ocr):
    box = BoundingBox(
        l=left, t=top, r=left + width, b=top + 10, coord_origin=CoordOrigin.TOPLEFT
    )
    return TextCell(
        index=0,
        text=value,
        orig=value,
        from_ocr=from_ocr,
        rect=BoundingRectangle.from_bounding_box(box),
    )


def register_page_cells(generator, page, from_ocr):
    """Recognized text of a register page, without running OCR or layout models."""
    cells = []
    for column, value in enumerate(page["header"]):
        left = generator.register_cell_left(column)
        width = generator.register_text_width(value)
        cells.append(register_text(left, 92, width, value, from_ocr))
    for index, (top, row, _) in enumerate(page["rows"]):
        columns = [column for column, value in enumerate(row) if value]
        if not from_ocr and index == 0:
            # Native PDF parsing can join neighbours across a printed rule.
            joined = " ".join(row[1:3])
            left = generator.register_cell_left(1)
            right = generator.register_cell_left(2)
            width = right - left + generator.register_text_width(row[2])
            cells.append(register_text(left, top, width, joined, from_ocr))
            columns = [column for column in columns if column not in (1, 2)]
        for column in columns:
            left = generator.register_cell_left(column)
            width = generator.register_text_width(row[column])
            cells.append(register_text(left, top, width, row[column], from_ocr))
    return cells


def tagged_register(name, from_ocr):
    generator = load_generate_module()
    path = CORPUS / "inbox" / name
    size = Size(width=generator.REGISTER_SIZE[0], height=generator.REGISTER_SIZE[1])
    pages = generator.register_pages(name)
    document = DoclingDocument(name=name)
    conversion_pages = []
    with pdfium.PdfDocument(path) as pdf:
        for number, page in enumerate(pages, start=1):
            image = pdf[number - 1].render(scale=1).to_pil().convert("RGB")
            document.add_page(
                page_no=number, size=size, image=ImageRef.from_pil(image, dpi=72)
            )
            document.add_picture(
                prov=ProvenanceItem(
                    page_no=number,
                    bbox=BoundingBox(
                        l=40, t=60, r=555, b=780, coord_origin=CoordOrigin.TOPLEFT
                    ),
                    charspan=(0, 0),
                )
            )
            conversion_pages.append(
                SimpleNamespace(
                    page_no=number,
                    size=size,
                    cells=register_page_cells(generator, page, from_ocr),
                )
            )
    conversion = SimpleNamespace(document=document, pages=conversion_pages)
    source = None if from_ocr else path
    assert restore_ruled_tables(conversion, source) == len(pages)
    mark_cancellations(conversion, source)
    return pages, document.export_to_markdown()


def marked_cells(pages):
    return [
        (row[column], kind)
        for page in pages
        for _, row, marks in page["rows"]
        for column, (kind, _) in marks.items()
    ]


def assert_tags(pages, markdown, skip=()):
    expected = [mark for mark in marked_cells(pages) if mark[1] not in skip]
    for value, kind in expected:
        assert f"{value} {MARK_TAGS[kind]}" in markdown
    assert sum(markdown.count(tag) for tag in MARK_TAGS.values()) == len(expected)


def test_digital_register_tags_exactly_the_drawn_marks():
    pages, markdown = tagged_register("inventory_example_digital.pdf", False)
    assert_tags(pages, markdown)
    # Split from a native line that crosses a column rule.
    assert "Team Eta [underlined]" in markdown
    # The printed rule just below entry 3 is not an underline.
    assert "Team Iota [" not in markdown


def test_scanned_register_tags_underlines_and_strikes():
    pages, markdown = tagged_register("inventory_sample_scan.pdf", True)
    assert_tags(pages, markdown, skip={"cross"})
    assert "Team Gamma [" not in markdown


@pytest.mark.xfail(
    strict=True,
    reason="Short diagonals fragment below the Hough thresholds at 1x page images.",
)
def test_scanned_register_tags_a_short_diagonal():
    _, markdown = tagged_register("inventory_sample_scan.pdf", True)
    assert "Transport [crossed out]" in markdown
