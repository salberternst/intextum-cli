import pytest

from intextum_cli.review import (
    display_value,
    document_rows,
    field_spec,
    filtered_groups,
    normalize_edit,
    source_html,
)
from intextum_cli.schema import SchemaField


@pytest.mark.parametrize(
    "dtype,value,expected",
    [
        ("int", "42", 42),
        ("float", "1.234,56", 1234.56),
        ("bool", "no", False),
        ("date", "31.12.2026", "2026-12-31"),
        (
            "currency",
            {"amount": "12,50", "currency": "eur"},
            {"amount": 12.5, "currency": "EUR"},
        ),
    ],
)
def test_corrections_preserve_field_types(dtype, value, expected):
    assert normalize_edit(value, SchemaField(name="value", dtype=dtype)) == expected


@pytest.mark.parametrize(
    "dtype,value",
    [
        ("int", "3.5"),
        ("date", "2026-02-30"),
        ("float", float("nan")),
        ("float", float("inf")),
    ],
)
def test_invalid_corrections_are_rejected(dtype, value):
    with pytest.raises(ValueError):
        normalize_edit(value, SchemaField(name="value", dtype=dtype))


def test_table_edits_validate_and_coerce_every_row():
    spec = SchemaField.model_validate(
        {
            "name": "positions",
            "dtype": "object_list",
            "required": True,
            "fields": [
                {"name": "sku", "required": True},
                {"name": "quantity", "dtype": "int", "required": True},
                {"name": "price", "dtype": "float"},
            ],
        }
    )
    rows = normalize_edit([{"sku": "AB-1", "quantity": "5", "price": "12,50"}], spec)
    assert rows == [{"sku": "AB-1", "quantity": 5, "price": 12.5}]
    with pytest.raises(ValueError, match="Row 1, quantity"):
        normalize_edit([{"sku": "AB-1", "quantity": "many"}], spec)
    with pytest.raises(ValueError, match="one row"):
        normalize_edit([], spec)
    with pytest.raises(ValueError, match="table of objects"):
        normalize_edit(["AB-1"], spec)


def test_enum_required_and_list_validation():
    spec = SchemaField(name="kind", required=True, enum=["service", "subscription"])
    with pytest.raises(ValueError, match="not in enum"):
        normalize_edit("other", spec)
    with pytest.raises(ValueError, match="missing required"):
        normalize_edit(None, spec)
    repeated = SchemaField(name="tags", dtype="list", enum=["a", "b"])
    assert normalize_edit(["a", "b"], repeated) == ["a", "b"]
    with pytest.raises(ValueError):
        normalize_edit(["c"], repeated)


def test_infers_fallback_types_and_honors_schema_for_empty_values():
    spec = field_spec("positions", {"value": [{"sku": "A", "count": 3}]})
    assert spec.dtype == "object_list"
    assert [(child.name, child.dtype) for child in spec.fields] == [
        ("sku", "str"),
        ("count", "int"),
    ]
    date = SchemaField(name="due", dtype="date")
    assert field_spec("due", {"value": None}, date) is date
    assert field_spec("enabled", {"value": False}).dtype == "bool"
    assert field_spec("date", {"value": "2026-12-31"}).dtype == "date"


def test_filters_combine_search_and_review_scope():
    entries = [
        {
            "slug": "a",
            "group": "ACME invoice",
            "class": "Invoice",
            "needs_review": True,
        },
        {"slug": "b", "group": "Contract", "class": "Service", "edited": True},
        {"slug": "c", "group": "Broken", "class": None, "status": "failed"},
    ]
    assert [e["slug"] for e in filtered_groups(entries, "invoice", "review")] == ["a"]
    assert [e["slug"] for e in filtered_groups(entries, "service", "edited")] == ["b"]
    assert [e["slug"] for e in filtered_groups(entries, scope="failed")] == ["c"]
    assert filtered_groups(entries, "missing") == []


def test_document_rows_preserve_shared_results_and_duplicate_filenames():
    entries = [
        {
            "slug": "bundle",
            "group": "Purchase order",
            "files": ["a/order.pdf", "b/order.pdf", "a/order.pdf"],
            "class": "Order",
        },
        {"slug": "single", "group": "Note", "files": ["note.md"]},
        {"slug": "empty", "group": "Missing files", "files": []},
    ]
    rows = document_rows(entries)
    bundle = [row for row in rows if row["slug"] == "bundle"]
    assert [row["label"] for row in bundle] == ["order.pdf", "order.pdf"]
    assert [row["file"] for row in bundle] == [
        "a/order.pdf",
        "b/order.pdf",
    ]
    assert all(row["group"] == "Purchase order" for row in bundle)
    assert all(row["file_count"] == 2 for row in bundle)
    assert len({row["id"] for row in rows}) == len(rows) == 4
    single = next(row for row in rows if row["slug"] == "single")
    empty = next(row for row in rows if row["slug"] == "empty")
    assert single["classification"] == "Unclassified"
    assert empty["file_count"] == 0 and empty["file"] is None
    assert document_rows(entries, " B/ORDER.PDF ") == [bundle[1]]
    assert document_rows(entries, "purchase order") == bundle
    assert document_rows(entries, "note.md", "review") == []


@pytest.mark.parametrize(
    "flags,expected",
    [
        ({"status": "failed", "needs_review": True, "edited": True}, "Failed"),
        ({"needs_review": True, "edited": True}, "Needs review"),
        ({"edited": True}, "Edited"),
        ({}, "Complete"),
    ],
)
def test_document_status_keeps_review_and_failures_visible(flags, expected):
    (node,) = document_rows([{"slug": "one", "group": "One", **flags}])
    assert node["status_label"] == expected


def test_evidence_markup_escapes_untrusted_document_content():
    rendered = source_html(
        ['<script>alert("unsafe")</script> Total: 12.50'], 0, "Total: 12.50"
    )
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert '<mark id="evidence-match">Total: 12.50</mark>' in rendered
    assert "<mark" not in source_html(["Total: 12.50"], 0, "Absent text")


def test_value_formatting_keeps_false_and_zero_visible():
    assert display_value(False) == "No"
    assert display_value(0) == "0"
    assert display_value(None) == "Not provided"
    assert display_value({"amount": 1234.5, "currency": "EUR"}) == "1,234.50 EUR"
