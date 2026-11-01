"""End-to-end: a field whose values live in a separate table file."""

import csv

from intextum_cli.classify import LlmClassifier
from intextum_cli.convert import Converter
from intextum_cli.exports import export_workspace
from intextum_cli.extraction_prompt import REFERENCES_KEY
from intextum_cli.groups import discover_groups
from intextum_cli.pipeline import run
from intextum_cli.processing import Options
from intextum_cli.schema import DocumentClass
from intextum_cli.sources import load_overrides
from intextum_cli.store import WorkspaceStore

REFERENCE = "see the table in Annex 1"
ITEMS = {
    "name": "line_items",
    "dtype": "object_list",
    "required": True,
    "description": "Items covered by the order",
    "fields": [{"name": "code"}, {"name": "item"}],
    "external": {"classes": ["Item list"]},
}


def classes(**external):
    items = {**ITEMS, "external": {**ITEMS["external"], **external}}
    return [
        DocumentClass.model_validate(
            {
                "class": "Service order",
                "fields": [
                    {"name": "order_number", "required": True},
                    {"name": "order_total"},
                    items,
                ],
            }
        ),
        DocumentClass.model_validate(
            {"class": "Item list", "description": "Table of items"}
        ),
        DocumentClass.model_validate(
            {"class": "Letter", "description": "Cover letter"}
        ),
    ]


def handler(name, user, schema):
    if name == "document_class":
        if "Service order No." in user.split("FILES:")[-1]:
            return {"class": "Service order", "reason": "order"}
        if "Code |" in user:
            return {"class": "Item list", "reason": "table"}
        return {"class": "Letter", "reason": "letter"}
    properties = schema["properties"]
    if "order_number" in properties:
        return {
            "order_number": {
                "value": "SC-7",
                "evidence_anchor": "Service order No. SC-7",
            },
            "order_total": {"value": "753,24", "evidence_anchor": "753,24"},
        }
    if REFERENCES_KEY in properties:  # the order's own line_items request
        inline = [{"value": {"code": "1", "item": "1/1"}, "evidence_anchor": "Code 1"}]
        return {
            "line_items": inline if "Code 1 item 1/1" in user else [],
            REFERENCES_KEY: {"line_items": REFERENCE},
        }
    table = user.split("SOURCE TEXT:")[-1]
    rows = [line.split("|") for line in table.splitlines() if line.count("|") >= 3]
    return {
        "line_items": [
            {
                "value": {"code": r[1].strip(), "item": r[2].strip()},
                "evidence_anchor": r[2].strip(),
            }
            for r in rows
            if r[1].strip().isdigit()
        ]
    }


def make_folder(tmp_path, order_extra=""):
    inbox = tmp_path / "inbox"
    folder = inbox / "acme"
    folder.mkdir(parents=True)
    (folder / "order_maintenance.txt").write_text(
        "Service order No. SC-7 for the SampleDepot site. The order total is "
        f"753,24 EUR. Covered items: {REFERENCE}. {order_extra}"
    )
    (folder / "items_final.txt").write_text(
        "Site | Code | Item | Qty\nSampleDepot | 5 | 46/2 | 80\nSampleDepot | 5 | 47 | 20\nTotal 753.24"
    )
    (folder / "items_draft.txt").write_text(
        "Site | Code | Item | Qty\nSampleDepot | 5 | 99/1 | 50\nTotal 610.00"
    )
    (folder / "letter.txt").write_text(
        "Enclosed is the order for the SampleDepot site."
    )
    return inbox


def extract_all(inbox, out, llm, document_classes, exclude_patterns=None):
    groups = discover_groups(
        inbox, exclude=[out], group_by="file", exclude_patterns=exclude_patterns
    )
    store = WorkspaceStore(out, create=True)
    summary = run(
        groups,
        converter=Converter(store),
        classifier=LlmClassifier(llm, store),
        llm=llm,
        options=Options(
            classes=document_classes,
            model="m",
            overrides=load_overrides(inbox),
        ),
        store=store,
        report=lambda line: None,
    )
    return summary, WorkspaceStore(out).results.get("acme_order_maintenance.txt")


def test_items_come_from_the_matching_table(tmp_path, fake_llm):
    inbox = make_folder(tmp_path)
    out = tmp_path / "out"
    llm = fake_llm(handler)
    _, result = extract_all(inbox, out, llm, classes())

    assert result["data"]["order_number"] == "SC-7"
    assert result["data"]["line_items"] == [
        {"code": "5", "item": "46/2"},
        {"code": "5", "item": "47"},
    ]
    field = result["fields"]["line_items"]
    assert field["source"]["files"] == ["acme/items_final.txt"]
    table_prompt = next(
        call["user"]
        for call in llm.calls
        if "=== FILE: acme/items_final.txt" in call["user"]
        and "CONTEXT:" in call["user"]
    )
    assert (
        "This file is the attachment of the document 'acme/order_maintenance.txt'"
        in table_prompt
    )
    assert f'The document itself says: "{REFERENCE}".' in table_prompt
    assert "extract all of them" in table_prompt
    assert field["source"]["runner_up"]["file"] == "acme/items_draft.txt"
    assert field["source"]["score"] >= field["source"]["runner_up"]["score"] + 0.15
    assert field["attachment_reference"]["quote"] == REFERENCE
    assert field["item_evidence"][0][0]["file"] == "acme/items_final.txt"
    assert result["review_reasons"] == [] and result["needs_review"] is False

    export_workspace(WorkspaceStore(out), tmp_path / "exports")
    with (tmp_path / "exports" / "_summary.csv").open(encoding="utf-8-sig") as handle:
        rows = {row["group"]: row for row in csv.DictReader(handle)}
    assert rows["acme/order_maintenance.txt"]["sources"].startswith(
        "line_items ← acme/items_final.txt ("
    )


def test_sources_yaml_overrides_the_choice(tmp_path, fake_llm):
    inbox = make_folder(tmp_path)
    (inbox / "sources.yaml").write_text(
        "sources:\n  acme/order_maintenance.txt:\n    line_items: acme/items_draft.txt\n"
    )
    _, result = extract_all(inbox, tmp_path / "out", fake_llm(handler), classes())
    assert result["data"]["line_items"] == [{"code": "5", "item": "99/1"}]
    assert result["fields"]["line_items"]["source"] == {
        "files": ["acme/items_draft.txt"],
        "set_in": "sources.yaml",
    }
    assert not (tmp_path / "out" / "sources.yaml.json").exists()


def test_sources_yaml_none_keeps_the_field_in_the_document(tmp_path, fake_llm):
    inbox = make_folder(tmp_path)
    (inbox / "sources.yaml").write_text(
        "sources:\n  acme/order_maintenance.txt:\n    line_items: none\n"
    )
    _, result = extract_all(inbox, tmp_path / "out", fake_llm(handler), classes())
    assert result["data"]["line_items"] == []
    assert result["fields"]["line_items"]["source"] == {
        "file": None,
        "set_in": "sources.yaml",
    }
    assert result["review_reasons"] == ["missing_required:line_items"]


def test_when_missing_skips_lookup_if_the_document_has_values(tmp_path, fake_llm):
    inbox = make_folder(tmp_path, order_extra="Code 1 item 1/1")
    _, result = extract_all(
        inbox, tmp_path / "out", fake_llm(handler), classes(when="missing")
    )
    assert result["data"]["line_items"] == [{"code": "1", "item": "1/1"}]
    assert "source" not in result["fields"]["line_items"]

    # With the default "auto", the reference to the annex makes the table win.
    _, result = extract_all(inbox, tmp_path / "out2", fake_llm(handler), classes())
    assert result["fields"]["line_items"]["source"]["files"] == ["acme/items_final.txt"]
    assert result["fields"]["line_items"]["document_value"] == [
        {"code": "1", "item": "1/1"}
    ]


def test_no_matching_source_is_flagged(tmp_path, fake_llm):
    inbox = make_folder(tmp_path)
    for name in ("items_final.txt", "items_draft.txt"):
        (inbox / "acme" / name).unlink()
    _, result = extract_all(inbox, tmp_path / "out", fake_llm(handler), classes())
    assert result["data"]["line_items"] == []
    assert result["review_reasons"] == [
        "external_source_not_found:line_items",
        "missing_required:line_items",
    ]


def test_excluded_files_are_never_candidates(tmp_path, fake_llm):
    inbox = make_folder(tmp_path)
    llm = fake_llm(handler)
    _, result = extract_all(
        inbox, tmp_path / "out", llm, classes(), exclude_patterns=["draft"]
    )
    source = result["fields"]["line_items"]["source"]
    assert source["files"] == ["acme/items_final.txt"]
    assert "runner_up" not in source
    assert all("items_draft" not in call["user"] for call in llm.calls)


def test_model_calls_are_labelled(tmp_path, fake_llm):
    inbox = make_folder(tmp_path)
    llm = fake_llm(handler)
    extract_all(inbox, tmp_path / "out", llm, classes())
    labels = [call["label"] for call in llm.calls]
    assert "classify acme/order_maintenance.txt" in labels
    assert "extract acme/order_maintenance.txt [line_items]" in labels
    assert "extract acme/order_maintenance.txt [order_number +1 fields]" in labels
    assert (
        "source acme/order_maintenance.txt ← acme/items_final.txt [line_items]"
        in labels
    )


def test_attachment_source_is_retained_when_no_values_or_evidence_are_extracted(
    tmp_path, fake_llm
):
    from intextum_cli.view import Library

    inbox = make_folder(tmp_path)
    database = tmp_path / "results.sqlite"

    def empty_attachment(name, user, schema):
        if "CONTEXT:" in user and "line_items" in schema["properties"]:
            return {"line_items": []}
        return handler(name, user, schema)

    _, result = extract_all(inbox, database, fake_llm(empty_attachment), classes())
    field = result["fields"]["line_items"]
    assert field["value"] == [] and not field.get("item_evidence")
    assert field["source"]["files"] == ["acme/items_final.txt"]
    store = WorkspaceStore(database)
    source = store.results.source("acme_order_maintenance.txt", "acme/items_final.txt")
    assert source["conversion_key"]
    (inbox / "acme" / "items_final.txt").unlink()
    lib = Library(database)
    assert (
        "46/2"
        in lib.text("acme/items_final.txt", "acme_order_maintenance.txt")["pages"][0]
    )


def test_attachment_pages_are_selected_before_fitting_max_chars(tmp_path, fake_llm):
    inbox = make_folder(tmp_path)
    final = inbox / "acme" / "items_final.txt"
    rows = "SampleDepot | 5 | 46/2 | 80\n" * 50
    final.write_text(f"Site | Code | Item | Qty\n{rows}Total 753.24\nCovered items end")
    (inbox / "acme" / "items_draft.txt").unlink()
    document_classes = classes()
    items = document_classes[0].fields[-1]
    items.source_pages_matching = "Covered items"
    out = tmp_path / "out"
    groups = discover_groups(inbox, exclude=[out], group_by="file")
    store = WorkspaceStore(out, create=True)
    llm = fake_llm(handler)
    run(
        groups,
        converter=Converter(store),
        classifier=LlmClassifier(llm, store),
        llm=llm,
        options=Options(
            classes=document_classes,
            model="m",
            overrides=load_overrides(inbox),
            max_chars=300,
        ),
        store=store,
        report=lambda line: None,
    )
    result = WorkspaceStore(out).results.get("acme_order_maintenance.txt")
    assert "no_matching_source_pages:line_items" not in result["review_reasons"]
    assert "source_truncated:acme/items_final.txt" in result["review_reasons"]
    assert any("--max-chars 300" in warning for warning in result["warnings"])
    assert not any("--max-chars None" in warning for warning in result["warnings"])
