import pytest
from pydantic import ValidationError

from intextum_cli.cli import main
from intextum_cli.schema import (
    DocumentClass,
    SchemaError,
    SchemaField,
    find_class,
    load_classes,
)

INVOICE = """
class: Invoice
description: Supplier invoice
aliases: [Rechnung]
fields:
  - name: invoice_number
    required: true
    description: Invoice id
  - name: line_items
    dtype: object_list
    description: Positions
    fields:
      - {name: description, description: Item}
      - {name: amount, dtype: currency, description: Net}
"""


@pytest.mark.parametrize(
    "text, code, message",
    [(INVOICE, 0, "Invoice: 2 field(s)"), ("class: A\nbogus: 1\n", 2, "bogus")],
)
def test_check_schemas_command(tmp_path, capsys, text, code, message):
    path = tmp_path / "schema.yaml"
    path.write_text(text)
    assert main(["check-schemas", str(path)]) == code
    output = capsys.readouterr()
    assert message in (output.out if code == 0 else output.err)


def test_schema_import_command_is_unavailable(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["import-schemas"])
    assert exc.value.code == 2
    assert "invalid choice: 'import-schemas'" in capsys.readouterr().err


def test_load_folder_and_lookup_by_alias(tmp_path):
    (tmp_path / "invoice.yaml").write_text(INVOICE)
    (tmp_path / "more.yml").write_text(
        "classes:\n  - class: Letter\n  - class: Contract\n"
    )
    classes = load_classes(tmp_path)
    assert [c.name for c in classes] == ["Invoice", "Letter", "Contract"]
    assert find_class(classes, "rechnung").name == "Invoice"
    assert find_class(classes, "letter").name == "Letter"
    assert find_class(classes, "memo") is None


def test_load_field_defaults_and_nested_types(tmp_path):
    (tmp_path / "invoice.yaml").write_text(INVOICE)
    [invoice] = load_classes(tmp_path)
    number, items = invoice.fields
    assert number.dtype == "str" and number.required
    assert items.dtype == "object_list" and not items.required
    description, amount = items.fields
    assert description.dtype == "str" and amount.dtype == "currency"


def test_external_class_reference_resolves_across_folder_by_alias(tmp_path):
    (tmp_path / "invoice.yaml").write_text(
        "class: Invoice\nfields:\n  - {name: items, external: {classes: [Positions]}}\n"
    )
    (tmp_path / "items.yml").write_text("class: Item list\naliases: [Positions]\n")
    invoice, items = load_classes(tmp_path)
    assert invoice.fields[0].external.classes == ["Positions"]
    assert items.name == "Item list"


@pytest.mark.parametrize(
    "text, message",
    [
        ("class: A\nfields:\n  - {name: x, dtype: object_list}\n", "needs child"),
        ("class: A\nfields:\n  - {name: x, dtype: int, enum: [a]}\n", "enum only"),
        ("class: A\nfields:\n  - {name: x}\n  - {name: x}\n", "duplicate field"),
        ("class: A\nfields:\n  - {name: x, dtype: text}\n", "dtype"),
        ("class: A\nbogus: 1\n", "bogus"),
        (
            "class: A\nfields:\n  - {name: x, source_pages_matching: '['}\n",
            "invalid source_pages_matching",
        ),
        (
            "class: A\nfields:\n  - {name: x, dtype: object_list, fields: [{name: quote, dtype: int, verbatim: true}]}\n",
            "verbatim is only allowed on str",
        ),
        ("classes:\n  - class: A\n  - class: a\n", "already defined"),
        (
            "class: Invoice\nfields:\n"
            "  - {name: items, external: {classes: [Missing]}}\n",
            "external class 'Missing' is not defined",
        ),
        (
            "class: A\nfields:\n  - {name: x}\nscenes:\n  - text: t\n    extractions:\n      - {field: y, value: 1}\n",
            "unknown field 'y'",
        ),
    ],
)
def test_invalid_schemas(tmp_path, text, message):
    path = tmp_path / "s.yaml"
    path.write_text(text)
    with pytest.raises(SchemaError, match=message):
        load_classes(path)


def test_load_instructions_and_scenes(tmp_path):
    path = tmp_path / "contract.yaml"
    path.write_text(
        "class: Wartungsvertrag\n"
        "instructions: Nur belegte Angaben.\n"
        "fields:\n  - {name: Vertragsnummer, required: true}\n"
        "scenes:\n"
        "  - text: 'Vertragsnummer: WV-2026/0042'\n"
        "    extractions:\n"
        "      - {field: Vertragsnummer, extraction_text: 'Vertragsnummer: WV-2026/0042', value: WV-2026/0042}\n"
    )
    [contract] = load_classes(path)
    assert contract.instructions == "Nur belegte Angaben."
    [scene] = contract.scenes
    assert scene.text == "Vertragsnummer: WV-2026/0042"
    [extraction] = scene.extractions
    assert extraction.field == "Vertragsnummer"
    assert extraction.extraction_text == scene.text
    assert extraction.value == "WV-2026/0042"


def test_quote_for_requires_an_identifier_dtype():
    with pytest.raises(ValidationError, match="must be str, int or date"):
        SchemaField.model_validate(
            {
                "name": "entries",
                "dtype": "object_list",
                "fields": [
                    {"name": "weight", "dtype": "float"},
                    {"name": "note", "verbatim": True, "quote_for": ["weight"]},
                ],
            }
        )


@pytest.mark.parametrize(
    "implied_by,message",
    [
        ({"gone": {"quote": "x"}}, "not allowed"),
        ({"cancelled": {}}, "needs marks or quote"),
        ({"cancelled": {"quote": "("}}, "invalid quote pattern"),
        ({"cancelled": {"marks": ["circle"]}}, "marks"),
    ],
)
def test_invalid_implied_by(implied_by, message):
    with pytest.raises(ValidationError, match=message):
        SchemaField.model_validate(
            {
                "name": "entries",
                "dtype": "object_list",
                "fields": [
                    {
                        "name": "status",
                        "enum": ["active", "cancelled"],
                        "implied_by": implied_by,
                    }
                ],
            }
        )


def test_unique_is_only_allowed_on_identifiers():
    with pytest.raises(ValueError, match="unique is only allowed"):
        DocumentClass.model_validate(
            {
                "class": "Register",
                "fields": [
                    {
                        "name": "entries",
                        "dtype": "object_list",
                        "fields": [
                            {"name": "numbers", "dtype": "list", "unique": True}
                        ],
                    }
                ],
            }
        )
