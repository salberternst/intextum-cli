import pytest

from intextum_cli.convert import file_digest
from intextum_cli.edits import apply_edits
from intextum_cli.store import WorkspaceStore
from intextum_cli.view import Library, ViewError


def result(**overrides):
    values = {
        "group": "Sample/supplier-order.doc",
        "mode": "extract",
        "status": "completed",
        "files": ["Sample/supplier-order.doc"],
        "class": {"name": "Purchase order", "source": "llm", "reason": "order letter"},
        "needs_review": True,
        "review_reasons": ["missing_required:Order-ID"],
        "warnings": [],
        "error": None,
        "fields": {
            "Order-ID": {"value": None, "evidence": []},
            "OrderDate": {"value": "01/01/2026", "evidence": []},
        },
    }
    values.update(overrides)
    return values


def library(tmp_path, results=None):
    inbox = tmp_path / "docs"
    (inbox / "Sample").mkdir(parents=True)
    (inbox / "Sample" / "supplier-order.doc").write_bytes(b"x")
    store = WorkspaceStore(tmp_path / "results.sqlite", create=True)
    store.set_workspace(inbox)
    for slug, data in (results or {"order": result()}).items():
        sources = []
        for relative in data["files"]:
            path = inbox / relative
            if path.is_file():
                sources.append({"path": relative, "digest": file_digest(path)})
        store.results.save(data, [], sources)
        with store.connection() as db:
            db.execute(
                "UPDATE results SET slug=?,slug_fold=? WHERE group_name=?",
                (slug, slug.casefold(), data["group"]),
            )
    return Library(store.path)


def test_missing_database_is_reported(tmp_path):
    with pytest.raises(ViewError, match="database"):
        Library(tmp_path / "nope.sqlite")


def test_index_uses_database_metadata(tmp_path):
    lib = library(tmp_path)
    entries = lib.index()
    assert [entry["slug"] for entry in entries] == ["order"]
    assert entries[0]["group"] == "Sample/supplier-order.doc"
    assert entries[0]["needs_review"] and not entries[0]["edited"]


def test_paths_outside_the_folders_are_refused(tmp_path):
    lib = library(tmp_path)
    assert lib.file("../secrets.txt") is None
    assert lib.file("Sample/supplier-order.doc") is not None
    assert lib.result("../out/order") is None
    assert lib.result("_summary") is None
    assert lib.result("order") is not None


def test_text_reports_a_file_that_is_not_cached(tmp_path):
    lib = library(tmp_path)
    assert lib.text("Sample/supplier-order.doc", "order") == {
        "cached": False,
        "pages": [],
        "notes": [],
    }
    assert not lib.text("Sample/missing.doc", "order")["cached"]


def test_edit_writes_history_and_clears_the_review_reason(tmp_path):
    lib = library(tmp_path)
    updated = lib.edit(
        "order", "Order-ID", "PO-2026-0042", "verified against the order letter"
    )
    assert updated["fields"]["Order-ID"]["value"] == "PO-2026-0042"
    assert updated["fields"]["Order-ID"]["edited"] is True
    assert updated["fields"]["Order-ID"]["extracted_value"] is None
    assert updated["review_reasons"] == [] and updated["needs_review"] is False
    (edit,) = updated["edits"]
    assert edit["field"] == "Order-ID" and edit["previous"] is None
    assert edit["note"] == "verified against the order letter" and edit["at"].endswith(
        "+00:00"
    )
    stored = lib.result("order")
    assert stored == updated
    with pytest.raises(KeyError):
        lib.edit("order", "Unknown", "x")


def test_a_rerun_reapplies_edits_and_flags_a_changed_extraction(tmp_path):
    lib = library(tmp_path)
    history = lib.edit("order", "Order-ID", "PO-2026-0042")["edits"]

    same = apply_edits(result(), history)
    assert same["fields"]["Order-ID"]["value"] == "PO-2026-0042"
    assert same["review_reasons"] == []

    fresh = result()
    fresh["fields"]["Order-ID"]["value"] = "PO-2026-0043"
    fresh["review_reasons"] = []
    changed = apply_edits(fresh, history)
    assert changed["fields"]["Order-ID"]["value"] == "PO-2026-0042"
    assert changed["fields"]["Order-ID"]["extracted_value"] == "PO-2026-0043"
    assert changed["review_reasons"] == ["edit_outdated:Order-ID"]
    assert changed["needs_review"] is True


def test_the_newest_edit_per_field_wins(tmp_path):
    lib = library(tmp_path)
    lib.edit("order", "OrderDate", "02/02/2026")
    data = lib.edit("order", "OrderDate", "03/03/2026", "order confirmation")
    assert len(data["edits"]) == 2
    assert data["fields"]["OrderDate"]["value"] == "03/03/2026"
    assert data["fields"]["OrderDate"]["extracted_value"] == "01/01/2026"


@pytest.fixture
def client(tmp_path):
    pytest.importorskip("nicegui")
    from fastapi.testclient import TestClient

    from intextum_cli.view_api import create_api

    with TestClient(create_api(library(tmp_path))) as client:
        yield client


def test_api_serves_index_raw_file_and_edits(client):
    index = client.get("/api/index").json()
    assert set(index) == {"input", "database", "groups"}
    assert [entry["slug"] for entry in index["groups"]] == ["order"]
    assert client.get("/api/group/order").json()["group"] == "Sample/supplier-order.doc"
    response = client.get(
        "/api/raw", params={"file": "Sample/supplier-order.doc", "group": "order"}
    )
    assert response.status_code == 200 and response.content == b"x"
    assert "attachment" in response.headers["Content-Disposition"]
    updated = client.post(
        "/api/edit/order", json={"field": "OrderDate", "value": "05/05/2026"}
    ).json()
    assert updated["fields"]["OrderDate"]["value"] == "05/05/2026"
    assert updated["data"]["OrderDate"] == "05/05/2026"
    assert client.get("/api/group/order").json()["edits"][0]["value"] == "05/05/2026"
    exported = client.get("/api/export/order")
    assert exported.status_code == 200
    assert exported.json()["data"]["OrderDate"] == "05/05/2026"
    assert "attachment" in exported.headers["Content-Disposition"]


def test_api_refuses_bad_requests_and_escaping_paths(client):
    for url in (
        "/api/group/../_summary",
        "/api/raw?file=../../etc/hosts",
        "/api/preview?file=Sample/supplier-order.doc&group=order",
        "/nope",
    ):
        assert client.get(url).status_code == 404
    assert (
        client.post(
            "/api/open", json={"file": "Sample/supplier-order.doc", "group": "order"}
        ).status_code
        == 404
    )
    assert client.post("/api/edit/order", json={"value": "x"}).status_code == 422
    assert client.post("/api/edit/order", content="{").status_code == 422
    assert (
        client.post(
            "/api/edit/order", json={"field": "Unknown", "value": "x"}
        ).status_code
        == 404
    )


def test_hidden_files_are_not_served(tmp_path):
    lib = library(tmp_path)
    (lib.input_dir / ".env").write_text("OPENAI_API_KEY=private")
    assert lib.file(".env") is None
    cache = lib.input_dir / ".intextum"
    cache.mkdir()
    (cache / "private.txt").write_text("private")
    assert lib.file(".intextum/private.txt") is None


def test_schema_controls_types_and_invalid_edits_are_not_saved(tmp_path):
    lib = library(tmp_path)
    schemas = lib.input_dir.parent / "schemas"
    schemas.mkdir()
    (schemas / "order.yaml").write_text(
        "class: Purchase order\nfields:\n"
        "  - {name: OrderDate, dtype: date, required: true}\n"
        "  - {name: Order-ID, dtype: str}\n"
    )
    lib = Library(lib.database, schemas=schemas)
    before = lib.result("order")
    with pytest.raises(ValueError, match="invalid date"):
        lib.edit("order", "OrderDate", "tomorrow")
    assert lib.result("order") == before
    updated = lib.edit("order", "OrderDate", "31.12.2026")
    assert updated["fields"]["OrderDate"]["value"] == "2026-12-31"
    assert updated["data"]["OrderDate"] == "2026-12-31"
    assert lib.store.results.classes("Sample/supplier-order.doc") == []


def test_nicegui_page_and_stylesheet_are_served(tmp_path):
    pytest.importorskip("nicegui")
    from fastapi.testclient import TestClient

    from intextum_cli.view import build_app

    with TestClient(build_app(library(tmp_path))) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "review.css" in response.text
        assert "Document review" in response.text
        assert "Extracted fields" in response.text
        stylesheet = client.get("/review.css")
        assert stylesheet.status_code == 200
        assert ".review-app" in stylesheet.text


def test_nicegui_correction_and_search_clear(tmp_path, monkeypatch):
    pytest.importorskip("nicegui")
    import asyncio

    from nicegui import ui
    from nicegui.testing import user_simulation

    from intextum_cli.review_ui import ReviewWorkspace

    lib = library(tmp_path)

    async def scenario():
        async def page():
            await ReviewWorkspace(lib).build()

        async with user_simulation(page) as user:
            await user.open("/")
            await user.should_see("Order-ID")
            user.find("Edit").click()
            await user.should_see("Edit Order-ID")
            user.find(ui.textarea).type("REVIEW-42")
            from intextum_cli.store import StorageError

            original_edit = lib.edit

            def fail_save(*args):
                raise StorageError("The database is busy; retry saving.")

            monkeypatch.setattr(lib, "edit", fail_save)
            user.find("Save correction").click()
            await user.should_see("The database is busy; retry saving.")
            monkeypatch.setattr(lib, "edit", original_edit)
            user.find("Save correction").click()
            await user.should_see("Correction saved")
            await user.should_see("REVIEW-42")
            assert user.notify.contains("Correction saved")
            assert lib.result("order")["data"]["Order-ID"] == "REVIEW-42"
            with user:
                search = next(
                    el
                    for el in user.find(ui.input).elements
                    if el.props.get("placeholder") == "Search documents…"
                )
                search.set_value("no matching document")
            await user.should_see("No matching documents")
            with user:
                search.set_value(None)
            await user.should_not_see("No matching documents")

    asyncio.run(scenario())


def test_document_selection_search_and_navigation_preserve_shared_results(
    tmp_path, monkeypatch
):
    pytest.importorskip("nicegui")
    import asyncio

    from nicegui.testing import user_simulation
    from nicegui.testing.general import nicegui_reset_globals
    from nicegui.testing.user_interaction import UserInteraction

    from intextum_cli.review_ui import ReviewWorkspace

    lib = library(
        tmp_path,
        {
            "order": result(),
            "annex": result(
                group="Annex",
                files=["annex/scan.pdf", "annex/details.txt"],
                needs_review=False,
            ),
        },
    )
    reads = []

    def text(name, convert=False):
        reads.append(name)
        return {"cached": True, "pages": [f"Content of {name}"]}

    monkeypatch.setattr(lib, "text", text)
    monkeypatch.setattr(lib, "document_status", lambda *args: {"status": "missing"})

    async def scenario():
        workspace = None

        async def page():
            nonlocal workspace
            workspace = ReviewWorkspace(lib)
            await workspace.build()

        async with user_simulation(page) as user:
            await user.open("/")
            await user.should_see("Content of Sample/supplier-order.doc")
            assert len(workspace.visible()) == 3
            button = next(
                element
                for element in workspace.sidebar.rows_box.descendants()
                if element.props.get("aria-label") == "Open annex/details.txt"
            )
            UserInteraction(user, {button}, None).click()
            await user.should_see("Content of annex/details.txt")
            assert workspace.slug == "annex"
            assert workspace.file == workspace.document.file == "annex/details.txt"
            assert workspace.result["group"] == "Annex"
            assert workspace.result["fields"] == lib.result("annex")["fields"]
            assert "annex/scan.pdf" not in reads

            with user:
                workspace.filter(query="annex/details.txt")
            assert [row["file"] for row in workspace.visible()] == ["annex/details.txt"]
            with user:
                workspace.filter(query="")
                await workspace.refresh()
            assert workspace.document.file == "annex/details.txt"
            # Navigation visits the next file, retaining the group's fields.
            with user:
                await workspace.move(1)
            assert workspace.document.file == "annex/scan.pdf"
            assert workspace.slug == "annex"
            assert workspace.result["fields"] == lib.result("annex")["fields"]
            # The preview dropdown and sidebar keep the same file selected.
            with user:
                workspace.document.picker.set_value("annex/details.txt")
            await user.should_see("Content of annex/details.txt")
            selected = [
                element
                for element in workspace.sidebar.rows_box.descendants()
                if element.props.get("aria-current") == "page"
            ]
            assert len(selected) == 1
            assert selected[0].props["aria-label"] == "Open annex/details.txt"

    try:
        asyncio.run(scenario())
    finally:
        with nicegui_reset_globals():
            pass


@pytest.mark.parametrize("package", ["nicegui", "nh3"])
def test_missing_ui_dependency_has_actionable_error(tmp_path, monkeypatch, package):
    import sys

    from intextum_cli.view import build_app

    monkeypatch.setitem(sys.modules, package, None)
    with pytest.raises(ViewError, match="pip install"):
        build_app(library(tmp_path))


def test_empty_workspace_renders_without_a_result_schema(tmp_path):
    pytest.importorskip("nicegui")
    from fastapi.testclient import TestClient

    from intextum_cli.view import build_app

    store = WorkspaceStore(tmp_path / "empty.sqlite", create=True)
    with TestClient(build_app(Library(store.path))) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Your review workspace" in response.text
        assert "No extracted fields" in response.text


def test_path_evidence_is_shown_without_a_document_link(tmp_path):
    pytest.importorskip("nicegui")
    import asyncio

    from nicegui import ui
    from nicegui.testing import user_simulation

    from intextum_cli.review_ui import ReviewWorkspace

    evidence = {
        "kind": "path",
        "file": "Sample/supplier-order.doc",
        "page": None,
        "snippet": "P-1234",
    }
    lib = library(
        tmp_path,
        {
            "order": result(
                needs_review=False,
                review_reasons=[],
                fields={"Project": {"value": "P-1234", "evidence": [evidence]}},
            )
        },
    )

    async def scenario():
        async def page():
            await ReviewWorkspace(lib).build()

        async with user_simulation(page) as user:
            await user.open("/")
            await user.should_see("From file path: P-1234")
            with user:
                buttons = [
                    el
                    for el in user.find(ui.button).elements
                    if "evidence-button" in el.classes
                ]
            assert not buttons

    asyncio.run(scenario())
