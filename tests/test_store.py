import csv
import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from intextum_cli.cli import main
from intextum_cli.convert import Converter
from intextum_cli.exports import export_workspace
from intextum_cli.schema import DocumentClass
from intextum_cli.store import (
    APPLICATION_ID,
    FORMAT_VERSION,
    StorageError,
    WorkspaceStore,
)
from intextum_cli.view import Library


def make_result(group="invoice", value=1):
    return {
        "group": group,
        "status": "completed",
        "mode": "extract",
        "files": [],
        "class": {"name": "Invoice"},
        "needs_review": False,
        "review_reasons": [],
        "data": {"number": value},
        "fields": {"number": {"value": value}},
    }


def test_database_format_configuration_and_rollback(tmp_path):
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    with store.connection() as db:
        assert db.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
        assert db.execute("PRAGMA user_version").fetchone()[0] == FORMAT_VERSION
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    with pytest.raises(ValueError):
        with store.connection() as db:
            db.execute("INSERT INTO metadata VALUES('rollback','test')")
            raise ValueError("abort")
    assert "rollback" not in store.metadata()
    with pytest.raises(StorageError, match="FOREIGN KEY"):
        with store.connection() as db:
            db.execute(
                "INSERT INTO document_assets VALUES('missing','image','missing')"
            )


@pytest.mark.parametrize(
    "kind", ["text", "unrelated", "newer", "damaged", "incomplete"]
)
def test_rejected_databases_are_not_overwritten(tmp_path, kind):
    path = tmp_path / "workspace.sqlite"
    if kind in {"text", "damaged"}:
        path.write_bytes(
            b"not a database" if kind == "text" else b"SQLite format 3\0" + b"\0" * 4096
        )
    elif kind == "newer":
        store = WorkspaceStore(path, create=True)
        with store.connection() as db:
            db.execute(f"PRAGMA user_version={FORMAT_VERSION + 1}")
    else:
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE unrelated(value)")
            if kind == "incomplete":
                db.execute(f"PRAGMA application_id={APPLICATION_ID}")
                db.execute(f"PRAGMA user_version={FORMAT_VERSION}")
    before = path.read_bytes()
    with pytest.raises(StorageError):
        WorkspaceStore(path, create=True)
    assert path.read_bytes() == before
    with pytest.raises(StorageError):
        WorkspaceStore(tmp_path / "missing.sqlite")
    assert not (tmp_path / "missing.sqlite").exists()


def test_document_and_assets_publish_atomically(tmp_path):
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    with pytest.raises(TypeError):
        store.cache.save_conversion(
            "k",
            "digest",
            ".txt",
            ["text"],
            False,
            [],
            {"assets": ["good.png", "bad.png"]},
            {"doc": True},
            {"good.png": b"image", "bad.png": object()},
        )
    assert store.cache.conversion("k") is None
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM assets").fetchone()[0] == 0
    store.cache.save_conversion(
        "k",
        "digest",
        ".txt",
        ["text"],
        False,
        [],
        {"assets": ["image.png"]},
        {"doc": True},
        {"image.png": b"image"},
    )
    assert store.cache.asset("k", "image.png") == b"image"
    assert store.cache.asset("other", "image.png") is None


def test_slugs_are_stable_across_runs_and_case_collisions(tmp_path):
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    for name in ("a/b", "a b", "A_B", "Ä", "ä", "ß", "ss"):
        store.results.save(make_result(name), [])
    before = {r["group"]: r["slug"] for r in store.results.index()}
    assert len({s.casefold() for s in before.values()}) == 7
    store.results.save(make_result("a/b", 2), [])
    assert {r["group"]: r["slug"] for r in store.results.index()} == before
    assert store.results.get("a/b", by_group=True)["data"]["number"] == 2


def test_concurrent_corrections_keep_all_history_and_raw_result(tmp_path):
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    store.results.save(make_result(), [])
    libraries = [Library(store.path) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda item: item[1].edit("invoice", "number", item[0] + 10),
                enumerate(libraries),
            )
        )
    result = store.results.get("invoice")
    assert len(result["edits"]) == 8
    assert {edit["value"] for edit in result["edits"]} == set(range(10, 18))
    with store.connection() as db:
        raw = json.loads(db.execute("SELECT payload FROM results").fetchone()[0])
    assert raw["fields"]["number"]["value"] == 1 and "edits" not in raw
    assert store.results.index()[0]["edited"]


@pytest.mark.parametrize("legacy_preview", [False, True])
def test_database_copy_supports_views_edits_and_embedded_schemas_without_originals(
    tmp_path,
    legacy_preview,
):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    path = inbox / "invoice.txt"
    path.write_text("Invoice number RE-1. Date: 31 December 2026.")
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    store.set_workspace(inbox)
    converter = Converter(store)
    converted = converter.convert(path, "invoice.txt")
    schema = DocumentClass.model_validate(
        {"class": "Invoice", "fields": [{"name": "number", "dtype": "date"}]}
    )
    result = make_result(value="2026-12-31")
    result["files"] = ["invoice.txt"]
    store.results.save(result, [schema], [converted.source_reference])
    if legacy_preview:
        # Workspaces from before preview removal can contain cached Office PDFs.
        with store.connection() as db:
            db.execute(
                "INSERT INTO assets VALUES(?,?,?)",
                ("legacy-preview", "application/pdf", b"%PDF-1.4 cached preview"),
            )
            db.execute(
                "INSERT INTO previews VALUES(?,?)",
                (converted.digest, "legacy-preview"),
            )
    copied = tmp_path / "copy.sqlite"
    shutil.copy2(store.path, copied)
    shutil.rmtree(inbox)
    lib = Library(copied)
    assert lib.input_dir is None
    assert lib.text("invoice.txt", "invoice")["pages"] == [
        "Invoice number RE-1. Date: 31 December 2026."
    ]
    state = lib.document_status("invoice.txt", "invoice")
    assert state["status"] == "ready" and not state["can_build"]
    assert (
        lib.document_json("invoice.txt", state["key"], "invoice")["schema_name"]
        == "DoclingDocument"
    )
    with pytest.raises(ValueError, match="invalid date"):
        lib.edit("invoice", "number", "tomorrow")
    assert lib.edit("invoice", "number", "31.01.2027")["data"]["number"] == "2027-01-31"
    assert "unavailable" in lib.build_document("invoice.txt", "invoice")["error"]
    export_workspace(lib.store, tmp_path / "exports")
    assert (
        json.loads((tmp_path / "exports" / "invoice.json").read_text())["data"][
            "number"
        ]
        == "2027-01-31"
    )


def test_group_context_pins_different_versions_of_same_filename(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    path = inbox / "shared.txt"
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    converter = Converter(store)
    for group, text in (
        ("first", "First version of this document"),
        ("second", "Second version of this document"),
    ):
        path.write_text(text)
        converted = converter.convert(path, "shared.txt")
        store.results.save(make_result(group), [], [converted.source_reference])
    lib = Library(store.path)
    assert lib.text("shared.txt", "first")["pages"] == [
        "First version of this document"
    ]
    assert lib.text("shared.txt", "second")["pages"] == [
        "Second version of this document"
    ]
    first = lib.document_status("shared.txt", "first")["key"]
    second = lib.document_status("shared.txt", "second")["key"]
    assert first != second
    assert lib.document_json("shared.txt", second, "first") is None


def test_exports_use_consistent_snapshot_and_union_of_schema_columns(
    tmp_path, monkeypatch
):
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    schema_a = DocumentClass.model_validate(
        {"class": "Invoice", "fields": [{"name": "number", "dtype": "int"}]}
    )
    schema_b = DocumentClass.model_validate(
        {"class": "Invoice", "fields": [{"name": "extra", "dtype": "str"}]}
    )
    store.results.save(make_result("a"), [schema_a])
    second = make_result("b")
    second["data"]["extra"] = "additional"
    store.results.save(second, [schema_b])
    library = Library(store.path)
    original = store.results._decode_result
    edited = False

    def during_snapshot(db, row):
        nonlocal edited
        if not edited:
            edited = True
            library.edit("a", "number", 99)
        return original(db, row)

    monkeypatch.setattr(store.results, "_decode_result", during_snapshot)
    out = tmp_path / "exports"
    export_workspace(store, out)
    assert json.loads((out / "a.json").read_text())["data"]["number"] == 1
    assert library.result("a")["data"]["number"] == 99
    assert (out / "Invoice.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    with (out / "Invoice.csv").open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["number"] == "1" and rows[1]["extra"] == "additional"


def test_cli_defaults_dry_run_exports_and_errors(tmp_path, monkeypatch, capsys):
    from intextum_cli import llm_endpoints

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "letter.txt").write_text("A letter with some readable source content.")
    schema = tmp_path / "schema.yaml"
    schema.write_text("class: Letter\n")
    monkeypatch.setattr(llm_endpoints, "fetch_context_length", lambda *args: None)
    monkeypatch.delenv("INTEXTUM_MODEL", raising=False)
    args = ["extract", str(inbox), "-s", str(schema), "--class", "Letter"]
    assert main([*args, "--dry-run"]) == 0
    path = tmp_path / "inbox-results.sqlite"
    assert not path.exists() and not (inbox / ".intextum").exists()
    assert main(args) == 0
    assert path.is_file() and not (tmp_path / "inbox-results").exists()
    assert not list(tmp_path.glob("*.csv")) and not list(tmp_path.glob("*.json"))
    out = tmp_path / "export"
    assert main(["export", str(path), "-o", str(out), "--format", "json"]) == 0
    assert (out / "letter.txt.json").exists() and not (out / "_summary.csv").exists()
    assert main(["export", str(path), "-o", str(out), "--format", "csv"]) == 0
    assert (out / "_summary.csv").exists()
    assert main([*args, "-o", str(inbox)]) == 2
    assert "database" in capsys.readouterr().err


def test_rebuild_does_not_rebind_a_result_committed_during_recognition(tmp_path):
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    for key in ("old", "new"):
        store.cache.save_conversion(key, "same-source", ".txt", [key], False, [])
    for key in ("old", "new"):
        store.results.save(
            make_result(),
            [],
            [{"path": "invoice.txt", "digest": "same-source", "key": key}],
        )
    store.results.bind_view("invoice", "invoice.txt", "old", "same-source", "old")
    assert store.results.source("invoice", "invoice.txt")["view_key"] == "new"


def test_saving_a_result_does_not_mutate_the_model_reply(tmp_path):
    store = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    reply = make_result()
    store.results.save(reply, [])
    Library(store.path).edit("invoice", "number", 99)
    corrected = store.results.save(reply, [])
    assert corrected["data"]["number"] == 99
    assert reply["data"]["number"] == 1
    assert reply["fields"]["number"] == {"value": 1}
    assert "edits" not in reply
