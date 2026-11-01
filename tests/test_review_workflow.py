import asyncio
import json

import pytest

from intextum_cli.classify import LlmClassifier
from intextum_cli.convert import Converter
from intextum_cli.exports import export_workspace
from intextum_cli.groups import Group
from intextum_cli.pipeline import run
from intextum_cli.processing import Options
from intextum_cli.review import document_rows, filtered_groups
from intextum_cli.review_state import ReviewConflict
from intextum_cli.schema import DocumentClass
from intextum_cli.store import WorkspaceStore
from intextum_cli.view import Library

CLASSES = [
    DocumentClass.model_validate(
        {
            "class": name,
            "fields": [{"name": "number", "required": True}],
        }
    )
    for name in ("Invoice", "Receipt")
] + [DocumentClass.model_validate({"class": "Letter"})]


@pytest.fixture
def workspace(tmp_path, fake_llm, monkeypatch):
    root = tmp_path / "inbox"
    root.mkdir()
    (root / "main.txt").write_text("Invoice INV-42 for maintenance. Total 125 EUR.")
    (root / "annex.txt").write_text("Annex listing the completed maintenance tasks.")
    (root / "other.txt").write_text("Dear Alex, thank you for your letter.")
    groups = [
        Group("bundle", root, [root / "main.txt", root / "annex.txt"]),
        Group("other", root, [root / "other.txt"], "Letter"),
    ]

    def handler(name, user, schema):
        if name == "document_class":
            return {"class": "Invoice", "reason": "invoice"}
        return {"number": {"value": "INV-42", "evidence_anchor": "INV-42"}}

    llm = fake_llm(handler)
    monkeypatch.setattr("intextum_cli.reextraction.OpenAiJsonLlm", lambda **_: llm)
    store = WorkspaceStore(tmp_path / "results.sqlite", create=True)
    options = Options(classes=CLASSES, model=llm.model, base_url="http://model/v1")

    def extract(**kwargs):
        return run(
            groups,
            converter=Converter(store),
            classifier=LlmClassifier(llm, store),
            llm=llm,
            options=Options(**{**vars(options), **kwargs}),
            store=store,
            report=lambda _: None,
        )

    extract()
    return Library(store.path), llm, extract


def act(lib, action, class_name=None, note="", slug="bundle"):
    return lib.review_action(
        slug, action, lib.result(slug)["review"]["revision"], class_name, note
    )


def test_review_accepts_warnings_keeps_provenance_and_can_reopen(workspace):
    lib, _, _ = workspace
    raw = lib.result("bundle")
    raw["review_reasons"] = ["source_truncated:main.txt", "missing_required:number"]
    raw["warnings"] = ["main.txt: text truncated"]
    raw["needs_review"] = True
    lib.store.results.save(raw, CLASSES)
    reviewed = act(lib, "approve", note="Checked against the originals")
    assert not reviewed["needs_review"]
    assert reviewed["review"]["state"] == "reviewed"
    assert reviewed["review"]["at"]
    assert reviewed["review"]["note"] == "Checked against the originals"
    assert reviewed["review_reasons"] == raw["review_reasons"]
    assert reviewed["warnings"] == raw["warnings"]
    assert (
        reviewed["fields"]["number"]["evidence"] == raw["fields"]["number"]["evidence"]
    )
    rows = lib.index()
    assert [r["slug"] for r in filtered_groups(rows, scope="reviewed")] == ["bundle"]
    assert document_rows(rows, scope="reviewed")[0]["status_label"] == "Reviewed"
    reopened = act(lib, "reopen", note="Check again")
    assert reopened["needs_review"] and reopened["review"]["state"] == "open"
    assert len(reopened["review"]["history"]) == 2


def test_approval_expires_after_correction_and_even_identical_forced_extraction(
    workspace,
):
    lib, _, extract = workspace
    act(lib, "approve")
    assert extract().unchanged == 2
    assert lib.result("bundle")["review"]["state"] == "reviewed"
    edited = lib.edit("bundle", "number", "MANUAL-1")
    assert edited["review"]["state"] == "open" and edited["needs_review"]
    act(lib, "approve")
    extract(force=True)
    result = lib.result("bundle")
    assert result["review"]["state"] == "open" and result["needs_review"]
    assert result["data"]["number"] == "MANUAL-1"


def test_class_change_is_pending_then_extracts_only_selected_shared_group(workspace):
    lib, llm, extract = workspace
    lib.edit("bundle", "number", "OLD-CLASS-EDIT")
    other = lib.result("other")
    selected = act(lib, "class", "Receipt", "Wrongly classified")
    assert selected["class"]["name"] == "Invoice"
    assert selected["review"]["class_override"] == "Receipt"
    assert selected["review"]["pending_extraction"]
    with pytest.raises(ValueError, match="Re-extract"):
        act(lib, "approve")
    with pytest.raises(ValueError, match="Re-extract"):
        lib.edit("bundle", "number", "too early")
    before = len(llm.calls)
    fresh = lib.reextract("bundle", selected["review"]["revision"])
    assert fresh["class"]["name"] == "Receipt"
    assert fresh["class"]["source"] == "viewer"
    assert fresh["files"] == ["main.txt", "annex.txt"]
    assert fresh["data"]["number"] == "INV-42"
    assert not fresh["fields"]["number"].get("edited")
    assert fresh["edits"][0]["value"] == "OLD-CLASS-EDIT"
    assert not fresh["review"]["pending_extraction"]
    assert lib.result("other") == other
    assert len(llm.calls) == before + 1
    assert llm.calls[-1]["name"] != "document_class"
    assert extract().unchanged == 2
    assert lib.result("bundle")["class"]["name"] == "Receipt"
    assert act(lib, "approve")["review"]["state"] == "reviewed"


def test_returning_to_previous_class_does_not_resurrect_its_old_corrections(workspace):
    lib, _, _ = workspace
    lib.edit("bundle", "number", "OLD")
    selected = act(lib, "class", "Receipt")
    lib.reextract("bundle", selected["review"]["revision"])
    lib.edit("bundle", "number", "RECEIPT")
    selected = act(lib, "class", "Invoice")
    result = lib.reextract("bundle", selected["review"]["revision"])
    assert result["data"]["number"] == "INV-42"
    assert [e["value"] for e in result["edits"]] == ["OLD", "RECEIPT"]


def test_no_match_finishes_without_model_and_survives_reruns(workspace):
    lib, llm, extract = workspace
    calls = len(llm.calls)
    confirmed = act(lib, "no_match", note="A newsletter")
    assert len(llm.calls) == calls
    assert confirmed["review"]["state"] == "reviewed"
    assert confirmed["status"] == "unclassified"
    assert not confirmed["needs_review"]
    assert confirmed["class"]["name"] is None
    assert confirmed["fields"] == confirmed["data"] == {}
    assert lib.index()[0]["reviewed"]
    extract()
    assert len(llm.calls) == calls
    fresh = lib.result("bundle")
    assert fresh["class"]["name"] is None and fresh["needs_review"]
    assert fresh["review"]["state"] == "open"
    assert act(lib, "approve")["review"]["state"] == "reviewed"
    assert extract().unchanged == 2


def test_automatic_classification_restores_classifier_and_clears_override(workspace):
    lib, _, _ = workspace
    act(lib, "no_match")
    selected = act(lib, "automatic")
    assert selected["review"]["pending_extraction"]
    result = lib.reextract("bundle", selected["review"]["revision"])
    assert result["class"]["name"] == "Invoice"
    assert result["class"]["source"] == "llm"


def test_stale_decisions_and_correction_dialogs_cannot_overwrite_newer_work(workspace):
    lib, _, _ = workspace
    revision = lib.result("bundle")["review"]["revision"]
    act(lib, "approve")
    with pytest.raises(ReviewConflict):
        lib.review_action("bundle", "reopen", revision)
    with pytest.raises(ReviewConflict):
        lib.edit("bundle", "number", "STALE", revision=revision)
    with pytest.raises(ReviewConflict):
        lib.reextract("bundle", revision)


def test_class_change_during_model_call_does_not_commit_stale_fields(workspace):
    lib, llm, _ = workspace
    selected = act(lib, "class", "Receipt")
    old_extraction = selected["extraction_id"]
    original_handler = llm.handler

    def handler(name, user, schema):
        act(lib, "class", "Letter")
        return original_handler(name, user, schema)

    llm.handler = handler
    with pytest.raises(ReviewConflict, match="class changed"):
        lib.reextract("bundle", selected["review"]["revision"])
    result = lib.result("bundle")
    assert result["extraction_id"] == old_extraction
    assert result["review"]["class_override"] == "Letter"
    assert result["review"]["pending_extraction"]


def test_same_class_reextraction_keeps_correction_saved_during_model_call(workspace):
    lib, llm, _ = workspace
    original_handler = llm.handler

    def handler(name, user, schema):
        lib.edit("bundle", "number", "CONCURRENT")
        return original_handler(name, user, schema)

    llm.handler = handler
    fresh = lib.reextract("bundle", lib.result("bundle")["review"]["revision"])
    assert fresh["data"]["number"] == "CONCURRENT"


def test_cli_reports_class_changed_during_extraction(workspace, monkeypatch, capsys):
    from intextum_cli.cli import main

    lib, llm, _ = workspace
    (lib.input_dir / "groups.yaml").write_text(
        "groups:\n  - name: bundle\n    files: [main.txt, annex.txt]\n"
        "  - name: other\n    files: [other.txt]\n    class: Letter\n"
    )
    schemas = lib.database.parent / "schema.yaml"
    schemas.write_text(
        json.dumps({"classes": [c.model_dump(by_alias=True) for c in CLASSES]})
    )
    original_handler = llm.handler

    def handler(name, user, schema):
        act(lib, "class", "Receipt")
        return original_handler(name, user, schema)

    llm.handler = handler
    monkeypatch.setattr("intextum_cli.llm.OpenAiJsonLlm", lambda **_: llm)
    monkeypatch.setattr(
        "intextum_cli.llm_endpoints.fetch_context_length", lambda *_: None
    )
    code = main(
        [
            "extract",
            str(lib.input_dir),
            "-s",
            str(schemas),
            "-o",
            str(lib.database),
            "--model",
            llm.model,
            "--force",
            "--quiet",
        ]
    )
    assert code == 2
    assert "class changed during extraction" in capsys.readouterr().err


def test_failed_results_cannot_be_approved_or_confirmed_out_of_scope(workspace):
    lib, _, _ = workspace
    raw = lib.result("bundle")
    raw.update(status="failed", error="conversion failed", needs_review=True)
    lib.store.results.save(raw, CLASSES)
    for action in ("approve", "no_match"):
        with pytest.raises(ValueError, match="failed result"):
            act(lib, action)


def test_portable_review_works_without_originals_but_reextraction_explains_missing_input(
    workspace,
):
    lib, _, _ = workspace
    lib.input_dir = None
    assert act(lib, "approve")["review"]["state"] == "reviewed"
    with pytest.raises(ValueError, match="Original documents are unavailable"):
        lib.reextract("bundle", lib.result("bundle")["review"]["revision"])


def test_reextraction_uses_current_env_with_recorded_settings_as_fallback(
    workspace, monkeypatch
):
    lib, llm, _ = workspace
    (lib.input_dir / ".env").write_text(
        "INTEXTUM_MODEL=new-model\nOPENAI_BASE_URL=http://new/v1\nOPENAI_API_KEY=secret\n"
    )
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return llm

    monkeypatch.setattr("intextum_cli.reextraction.OpenAiJsonLlm", factory)
    lib.reextract("bundle", lib.result("bundle")["review"]["revision"])
    assert captured["model"] == "new-model"
    assert captured["base_url"] == "http://new/v1"
    assert captured["api_key"] == "secret"
    assert "secret" not in json.dumps(lib.store.metadata())
    assert "secret" not in json.dumps(lib.result("bundle"))


def test_reextraction_retains_recorded_ocr_settings(workspace, monkeypatch):
    lib, _, extract = workspace
    extract(
        ocr_engine="tesseract",
        ocr_languages=["deu"],
        table_mode="predicted",
        detect_marks=True,
    )
    original = Converter.convert
    seen = []

    def capture(self, *args, **kwargs):
        seen.append(
            (self.ocr_engine, self.ocr_languages, self.table_mode, self.detect_marks)
        )
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Converter, "convert", capture)
    lib.reextract("bundle", lib.result("bundle")["review"]["revision"])
    assert seen and all(
        value == ("tesseract", ("deu",), "predicted", True) for value in seen
    )


def test_export_replaces_previous_class_csv_after_reclassification(workspace, tmp_path):
    lib, _, _ = workspace
    destination = tmp_path / "exports"
    export_workspace(lib.store, destination)
    assert (destination / "Invoice.csv").is_file()
    selected = act(lib, "class", "Receipt")
    lib.reextract("bundle", selected["review"]["revision"])
    export_workspace(lib.store, destination)
    assert not (destination / "Invoice.csv").exists()
    assert (destination / "Receipt.csv").is_file()
    act(lib, "no_match")
    export_workspace(lib.store, destination)
    assert not (destination / "Receipt.csv").exists()


def test_review_and_reextraction_api_validate_changes(workspace):
    pytest.importorskip("nicegui")
    from fastapi.testclient import TestClient

    from intextum_cli.view_api import create_api

    lib, _, _ = workspace
    with TestClient(create_api(lib)) as client:
        revision = lib.result("bundle")["review"]["revision"]
        response = client.post(
            "/api/review/bundle",
            json={"action": "class", "class_name": "Missing", "revision": revision},
        )
        assert response.status_code == 422
        assert (
            client.post("/api/review/bundle", json={"action": "approve"}).status_code
            == 422
        )
        response = client.post(
            "/api/review/bundle",
            json={"action": "class", "class_name": "Receipt", "revision": revision},
        )
        assert response.status_code == 200
        assert (
            client.post(
                "/api/review/bundle", json={"action": "approve", "revision": revision}
            ).status_code
            == 409
        )
        revision = response.json()["review"]["revision"]
        response = client.post("/api/reextract/bundle", json={"revision": revision})
        assert response.status_code == 200
        assert response.json()["class"]["name"] == "Receipt"
        assert (
            client.post(
                "/api/reextract/missing", json={"revision": revision}
            ).status_code
            == 404
        )
        revision = response.json()["review"]["revision"]
        response = client.post(
            "/api/review/bundle", json={"action": "approve", "revision": revision}
        )
        assert response.json()["review"]["state"] == "reviewed"
        assert client.get("/api/export/bundle").json()["review"]["state"] == "reviewed"


def test_viewer_class_extraction_and_review_controls(workspace):
    pytest.importorskip("nicegui")
    from nicegui import ui
    from nicegui.testing import user_simulation
    from nicegui.testing.general import nicegui_reset_globals
    from nicegui.testing.user_interaction import UserInteraction

    from intextum_cli.review_ui import ReviewWorkspace

    lib, _, _ = workspace

    async def scenario():
        async def page():
            await ReviewWorkspace(lib).build()

        async with user_simulation(page) as user:
            await user.open("/")
            user.find(marker="result-menu").click()
            user.find(marker="change-class").click()
            await user.should_see("Document class")
            with user:
                select = next(
                    el
                    for el in user.find(ui.select).elements
                    if el.props.get("label") == "Document class"
                )
                select.set_value("Receipt")
            user.find("Save class").click()
            await user.should_see("Class changed to Receipt.", retries=30)
            with user:
                # The banner's button, not the header menu's "Re-extract group".
                extract = {
                    el
                    for el in user.find(ui.button).elements
                    if el.text == "Re-extract"
                }
            UserInteraction(user, extract, None).click()
            await user.should_see("Group re-extracted.", retries=30)
            assert lib.result("bundle")["class"]["name"] == "Receipt"
            user.find("Mark reviewed").click()
            await user.should_see("Reopen review", retries=30)
            assert lib.result("bundle")["review"]["state"] == "reviewed"

    try:
        asyncio.run(scenario())
    finally:
        with nicegui_reset_globals():
            pass


def test_review_queue_advances_to_next_document_and_keeps_note(workspace):
    pytest.importorskip("nicegui")
    from nicegui import ui
    from nicegui.testing import user_simulation
    from nicegui.testing.general import nicegui_reset_globals

    from intextum_cli.review_ui import ReviewWorkspace

    lib, _, _ = workspace
    for slug in ("bundle", "other"):
        act(lib, "reopen", slug=slug)
    workspace_ui = None

    async def scenario():
        nonlocal workspace_ui

        async def page():
            nonlocal workspace_ui
            workspace_ui = ReviewWorkspace(lib)
            await workspace_ui.build()

        async with user_simulation(page) as user:
            await user.open("/")
            await user.should_see("2 to review →")
            assert workspace_ui.slug == "bundle"
            with user:
                note = next(
                    el
                    for el in user.find(ui.input).elements
                    if el.props.get("placeholder") == "Review note (optional)"
                )
                note.set_value("Totals match")
            user.find("Mark reviewed").click()
            await user.should_see("Marked reviewed", retries=30)
            assert workspace_ui.slug == "other"
            assert lib.result("bundle")["review"]["note"] == "Totals match"
            await user.should_see("1 to review →")
            # The last open document completes the queue and stays selected.
            with user:
                await workspace_ui.actions.approve()
            await user.should_see("nothing left to review", retries=30)
            assert workspace_ui.slug == "other"
            assert lib.result("other")["review"]["state"] == "reviewed"
            await user.should_see("All reviewed")

    try:
        asyncio.run(scenario())
    finally:
        with nicegui_reset_globals():
            pass


def test_next_to_review_keeps_position_when_filter_hides_reviewed_row(workspace):
    from intextum_cli.review_ui import ReviewWorkspace

    lib, _, _ = workspace
    rows = [
        {"slug": "a", "file": "a.txt"},
        {"slug": "b", "file": "b1.txt"},
        {"slug": "b", "file": "b2.txt"},
        {"slug": "c", "file": "c.txt"},
    ]
    queue = ReviewWorkspace.__new__(ReviewWorkspace)
    queue.entries = [
        {"slug": "a", "needs_review": True},
        {"slug": "b", "needs_review": False},
        {"slug": "c", "needs_review": True},
    ]
    # Shared results are skipped once reviewed; the queue wraps around.
    assert ReviewWorkspace.next_to_review(queue, rows, "a", "a.txt")["slug"] == "c"
    assert ReviewWorkspace.next_to_review(queue, rows, "c", "c.txt")["slug"] == "a"
    queue.entries[0]["needs_review"] = False
    assert ReviewWorkspace.next_to_review(queue, rows, "c", "c.txt") is None


def test_export_filters_by_review_state_and_removes_excluded_json(workspace, tmp_path):
    import csv

    lib, _, _ = workspace
    destination = tmp_path / "exports"
    assert export_workspace(lib.store, destination) == 2
    assert (destination / "other.json").is_file()
    act(lib, "approve", slug="bundle")

    assert export_workspace(lib.store, destination, state="reviewed") == 1
    assert (destination / "bundle.json").is_file()
    # The earlier full export's open result must not linger in a reviewed export.
    assert not (destination / "other.json").exists()
    with (destination / "_summary.csv").open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert [(r["group"], r["review_state"]) for r in rows] == [("bundle", "reviewed")]
    with (destination / "Invoice.csv").open(encoding="utf-8-sig") as handle:
        assert next(csv.DictReader(handle))["review_state"] == "reviewed"

    assert export_workspace(lib.store, destination, state="open") == 1
    assert (destination / "other.json").is_file()
    assert not (destination / "bundle.json").exists()
    assert not (destination / "Invoice.csv").exists()
    with pytest.raises(ValueError, match="unknown review state"):
        export_workspace(lib.store, destination, state="done")


def test_export_command_reports_filtered_count(workspace, tmp_path, capsys):
    from intextum_cli.cli import main

    lib, _, _ = workspace
    act(lib, "approve", slug="bundle")
    out = tmp_path / "reviewed"
    assert (
        main(["export", str(lib.database), "-o", str(out), "--state", "reviewed"]) == 0
    )
    assert "exported 1 reviewed result(s) as all" in capsys.readouterr().out


def test_reextract_many_runs_selected_groups_once_with_progress(workspace):
    lib, llm, _ = workspace
    act(lib, "class", "Receipt")
    before = len(llm.calls)
    seen = []
    results = lib.reextract_many(["bundle", "other", "bundle"], seen.append)
    assert [r["group"] for r in results] == ["bundle", "other"]
    assert seen == [1, 2]
    assert results[0]["class"]["name"] == "Receipt"
    assert not results[0]["review"]["pending_extraction"]
    assert results[1]["class"]["name"] == "Letter"
    assert len(llm.calls) > before
    assert lib.reextract_many([]) == []
    with pytest.raises(KeyError):
        lib.reextract_many(["missing"])


def test_reextract_many_progress_does_not_count_verification(workspace, monkeypatch):
    lib, _, _ = workspace
    verified = []

    def decide(self, state, questions):
        verified.append(questions)
        return {"field_0": {"noul": 0.99}}

    monkeypatch.setenv("INTEXTUM_VERIFIER_MODEL", "test-verifier")
    monkeypatch.setattr("intextum_cli.decisions.DecisionClient.decide", decide)
    seen = []
    results = lib.reextract_many(["bundle", "other"], seen.append)

    assert len(verified) == 1
    assert results[0]["verification"]["model"] == "test-verifier"
    assert seen == [1, 2]


def test_viewer_reextracts_current_list_skipping_reviewed(workspace):
    pytest.importorskip("nicegui")
    from nicegui import ui
    from nicegui.testing import user_simulation
    from nicegui.testing.general import nicegui_reset_globals
    from nicegui.testing.user_interaction import UserInteraction

    from intextum_cli.review_ui import ReviewWorkspace

    lib, _, _ = workspace
    act(lib, "approve", slug="other")
    calls = []
    original = lib.reextract_many

    def record(slugs, progress=None):
        calls.append(list(slugs))
        return original(slugs, progress)

    lib.reextract_many = record

    async def scenario():
        async def page():
            await ReviewWorkspace(lib).build()

        async with user_simulation(page) as user:
            await user.open("/")
            user.find(marker="list-menu").click()
            user.find(marker="reextract-list").click()
            await user.should_see("1 result(s) from 3 listed document(s).")
            user.find("Skip reviewed results").click()
            await user.should_see("2 result(s) from 3 listed document(s).")
            user.find("Skip reviewed results").click()
            with user:
                start = {
                    el
                    for el in user.find(ui.button).elements
                    if el.text == "Re-extract"
                }
            UserInteraction(user, start, None).click()
            for _ in range(60):
                if calls and user.notify.contains("Re-extracted 1 result(s)"):
                    break
                await asyncio.sleep(0.05)
            assert user.notify.contains(
                "Re-extracted 1 result(s): 0 need review, 0 failed."
            )

    try:
        asyncio.run(scenario())
    finally:
        with nicegui_reset_globals():
            pass
    assert calls == [["bundle"]]
    assert lib.result("other")["review"]["state"] == "reviewed"
