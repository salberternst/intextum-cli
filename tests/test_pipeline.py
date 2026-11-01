import csv

import pytest

from intextum_cli.classify import NO_MATCH, LlmClassifier
from intextum_cli.convert import Converter
from intextum_cli.exports import export_workspace
from intextum_cli.groups import discover_groups
from intextum_cli.llm_types import LlmError
from intextum_cli.pipeline import run
from intextum_cli.processing import Options
from intextum_cli.schema import DocumentClass
from intextum_cli.store import WorkspaceStore

CLASSES = [
    DocumentClass.model_validate(
        {
            "class": "Invoice",
            "aliases": ["Rechnung"],
            "fields": [
                {"name": "number", "required": True, "description": "Invoice number"},
                {"name": "total", "dtype": "currency", "description": "Total"},
            ],
        }
    ),
    DocumentClass.model_validate({"class": "Letter"}),
]


def handler(name, user, schema):
    if "BOOM" in user:
        raise LlmError("model server went away")
    if name == "document_class":
        if "RE-1" in user:
            return {"class": "Invoice", "reason": "has an invoice number"}
        if "Dear" in user:
            return {"class": "Letter", "reason": "a letter"}
        return {"class": NO_MATCH, "reason": "no idea"}
    return {
        "number": {"value": "RE-1", "evidence_anchor": "Rechnung RE-1"},
        "total": {
            "value": {"amount": 10.5, "currency": "EUR"},
            "evidence_anchor": "10,50",
        },
    }


def make_inbox(tmp_path):
    inbox = tmp_path / "inbox"
    (inbox / "case-1").mkdir(parents=True)
    (inbox / "case-1" / "cover.txt").write_text("Rechnung RE-1 für die Wartung")
    (inbox / "case-1" / "table.csv.txt").write_text(
        "Summe: 10,50 EUR für Leistungen im Mai"
    )
    (inbox / "hello.txt").write_text("Dear Sir, thank you for your letter.")
    (inbox / "random.txt").write_text("lorem ipsum dolor sit amet")
    (inbox / "flaky.txt").write_text("BOOM goes the model server")
    (inbox / "image.xyz").write_text("?")  # unsupported type: never a group
    return inbox


def run_once(inbox, out, llm, **overrides):
    options = Options(
        classes=CLASSES,
        model=llm.model,
        **overrides,
    )
    store = WorkspaceStore(out, create=True)
    lines = []
    summary = run(
        discover_groups(inbox, exclude=[out]),
        converter=Converter(store),
        classifier=LlmClassifier(llm, store),
        llm=llm,
        options=options,
        store=store,
        report=lines.append,
    )
    return summary, lines


def test_end_to_end_with_fake_model(tmp_path, fake_llm):
    inbox = make_inbox(tmp_path)
    out = tmp_path / "results"
    llm = fake_llm(handler)

    summary, lines = run_once(inbox, out, llm)
    assert (summary.processed, summary.failed, summary.needs_review) == (4, 1, 2)

    case = WorkspaceStore(out).results.get("case-1")
    assert case["files"] == ["case-1/cover.txt", "case-1/table.csv.txt"]
    assert case["class"]["name"] == "Invoice"
    assert case["data"] == {
        "number": "RE-1",
        "total": {"amount": 10.5, "currency": "EUR"},
    }
    assert case["fields"]["total"]["evidence"][0]["file"] == "case-1/table.csv.txt"
    assert case["needs_review"] is False

    letter = WorkspaceStore(out).results.get("hello.txt")
    assert letter["status"] == "completed" and letter["data"] == {}

    unknown = WorkspaceStore(out).results.get("random.txt")
    assert unknown["status"] == "unclassified" and unknown["needs_review"]

    failed = WorkspaceStore(out).results.get("flaky.txt")
    assert failed["status"] == "failed" and "went away" in failed["error"]
    assert not (out / "image.xyz.json").exists()

    export_workspace(WorkspaceStore(out), tmp_path / "exports")
    with (tmp_path / "exports" / "Invoice.csv").open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {"group": "case-1", "needs_review": "no", "review_state": "open",
         "review_reasons": "", "number": "RE-1", "total": "10.5 EUR"}
    ]  # fmt: skip
    export_workspace(WorkspaceStore(out), tmp_path / "exports")
    with (tmp_path / "exports" / "_summary.csv").open(encoding="utf-8-sig") as handle:
        assert len(list(csv.DictReader(handle))) == 4

    # Second run: unchanged groups are skipped; the failed one is retried.
    calls_before = len(llm.calls)
    summary, lines = run_once(inbox, out, llm)
    assert (summary.processed, summary.unchanged) == (1, 3)
    assert len(llm.calls) == calls_before + 1  # only the failed group again
    assert (tmp_path / "exports" / "Invoice.csv").exists()

    # Changing a file reprocesses just that group.
    (inbox / "case-1" / "cover.txt").write_text(
        "Rechnung RE-1 für die Wartung (corrected)"
    )
    summary, _ = run_once(inbox, out, llm)
    assert (summary.processed, summary.unchanged) == (2, 2)


def test_group_progress_reads_committed_results_and_includes_skips(tmp_path, fake_llm):
    inbox = make_inbox(tmp_path)
    (inbox / "random-copy.txt").write_text((inbox / "random.txt").read_text())
    groups = discover_groups(inbox)
    store = WorkspaceStore(tmp_path / "results.sqlite", create=True)
    llm = fake_llm(handler)
    finished = []
    statuses = []

    def group_finished(name):
        result = store.results.get(name, by_group=True)
        assert result is not None
        finished.append(name)
        statuses.append(result["status"])

    def extract(only_groups=None):
        return run(
            groups,
            converter=Converter(store),
            classifier=LlmClassifier(llm, store),
            llm=llm,
            options=Options(classes=CLASSES, model=llm.model),
            store=store,
            report=lambda _: None,
            only_groups=only_groups,
            on_group_finished=group_finished,
        )

    first = extract()
    assert (first.processed, first.failed, first.duplicates) == (5, 1, 1)
    assert finished == [group.name for group in groups]
    assert set(statuses) == {"completed", "failed", "unclassified", "duplicate"}

    finished.clear()
    statuses.clear()
    second = extract()
    assert (second.processed, second.unchanged) == (1, 4)
    assert finished == [group.name for group in groups]

    finished.clear()
    selected = extract(only_groups={"case-1"})
    assert selected.unchanged == 1
    assert finished == ["case-1"]


def test_forced_class_skips_classification(tmp_path, fake_llm):
    inbox = make_inbox(tmp_path)
    llm = fake_llm(handler)
    run_once(inbox, tmp_path / "out", llm, forced_class="rechnung")
    assert all(call["name"] != "document_class" for call in llm.calls)
    result = WorkspaceStore(tmp_path / "out").results.get("hello.txt")
    assert result["class"] == {
        "name": "Invoice", "source": "--class",
        "reason": None, "error": None,
    }  # fmt: skip
    assert "no_evidence:number" in result["review_reasons"]


def test_endpoint_changes_reprocess_groups_with_the_same_model(tmp_path, fake_llm):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "invoice.txt").write_text(
        "Rechnung RE-1 für die Wartung. Summe: 10,50 EUR."
    )
    out = tmp_path / "out"
    llm = fake_llm(handler)

    summary, _ = run_once(inbox, out, llm, base_url="http://first:1234/v1")
    assert summary.processed == 1
    summary, _ = run_once(inbox, out, llm, base_url="http://first:1234/v1/")
    assert summary.unchanged == 1
    summary, _ = run_once(inbox, out, llm, base_url="http://second:1234/v1")
    assert summary.processed == 1 and summary.unchanged == 0


def test_classify_only_then_full_run(tmp_path, fake_llm):
    inbox = make_inbox(tmp_path)
    out = tmp_path / "results"
    llm = fake_llm(handler)

    summary, _ = run_once(inbox, out, llm, classify_only=True)
    assert {call["name"] for call in llm.calls} == {"document_class"}
    case = WorkspaceStore(out).results.get("case-1")
    assert case["mode"] == "classify"
    assert case["class"]["name"] == "Invoice" and case["data"] == {}
    assert case["status"] == "completed" and case["needs_review"] is False
    assert not (tmp_path / "exports" / "Invoice.csv").exists()
    export_workspace(WorkspaceStore(out), tmp_path / "exports")
    with (tmp_path / "exports" / "_summary.csv").open(encoding="utf-8-sig") as handle:
        rows = {row["group"]: row for row in csv.DictReader(handle)}
    assert rows["case-1"]["reason"] == "has an invoice number"
    assert rows["case-1"]["class_source"] == "llm"
    assert (
        rows["random.txt"]["class"] == ""
        and rows["random.txt"]["needs_review"] == "yes"
    )

    # Classify-only results must not make the full run skip extraction.
    summary, _ = run_once(inbox, out, llm)
    assert summary.unchanged == 0
    case = WorkspaceStore(out).results.get("case-1")
    assert case["mode"] == "extract" and case["data"]["number"] == "RE-1"
    export_workspace(WorkspaceStore(out), tmp_path / "exports")
    assert (tmp_path / "exports" / "Invoice.csv").exists()


def test_ocr_and_token_settings_reprocess_groups(tmp_path, fake_llm):
    inbox = make_inbox(tmp_path)
    out = tmp_path / "results"
    llm = fake_llm(handler)
    run_once(inbox, out, llm)
    assert run_once(inbox, out, llm)[0].unchanged == 3
    assert run_once(inbox, out, llm, force_ocr=True)[0].unchanged == 0
    assert run_once(inbox, out, llm, force_ocr=True)[0].unchanged == 3
    assert (
        run_once(inbox, out, llm, force_ocr=True, max_output_tokens=8192)[0].unchanged
        == 0
    )


@pytest.mark.parametrize(
    "setting,initial,changed",
    [
        ("thinking", False, True),
        ("context_length", None, 8192),
        ("context_length", 8192, 16384),
        ("max_output_tokens", 4096, 8192),
    ],
)
def test_generation_changes_refresh_results_and_classifications(
    tmp_path, fake_llm, setting, initial, changed
):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "invoice.txt").write_text(
        "Rechnung RE-1 für die Wartung. Summe: 10,50 EUR."
    )
    out = tmp_path / "results.sqlite"
    llm = fake_llm(handler)
    setattr(llm, setting, initial)

    def run_with(value):
        setattr(llm, setting, value)
        return run_once(inbox, out, llm, **{setting: value})[0]

    assert run_with(initial).processed == 1
    assert len(llm.calls) == 2
    assert llm.calls[0]["name"] == "document_class"
    assert run_with(initial).unchanged == 1
    assert len(llm.calls) == 2

    summary = run_with(changed)
    assert (summary.processed, summary.unchanged) == (1, 0)
    assert len(llm.calls) == 4
    assert llm.calls[-2]["name"] == "document_class"
    assert run_with(changed).unchanged == 1
    assert len(llm.calls) == 4


def make_customer_folder(tmp_path):
    inbox = tmp_path / "inbox"
    long_invoice = (
        "Rechnung RE-1 über Wartung. "
        + "Leistungsbeschreibung Wartung Kasse. " * 20
        + "Summe: 10,50 EUR"
    )
    (inbox / "customer").mkdir(parents=True)
    (inbox / "customer" / "rechnung.txt").write_text(long_invoice)
    (inbox / "customer" / "rechnung_unterschrieben.txt").write_text(
        long_invoice + " Unterschrift"
    )
    (inbox / "customer" / "karte.shp").write_text("binary")
    return inbox


def test_file_mode_marks_duplicates_and_skips_them(tmp_path, fake_llm):
    inbox = make_customer_folder(tmp_path)
    out = tmp_path / "results"
    llm = fake_llm(handler)
    unsupported = []
    groups = discover_groups(
        inbox, exclude=[out], group_by="file", unsupported=unsupported
    )
    assert [g.name for g in groups] == [
        "customer/rechnung.txt",
        "customer/rechnung_unterschrieben.txt",
    ]
    store = WorkspaceStore(out, create=True)
    summary = run(
        groups,
        converter=Converter(store),
        classifier=LlmClassifier(llm, store),
        llm=llm,
        options=Options(classes=CLASSES, model="m"),
        store=store,
        report=lambda line: None,
    )
    assert (summary.processed, summary.duplicates, summary.needs_review) == (2, 1, 0)
    duplicate = WorkspaceStore(out).results.get("customer_rechnung.txt")
    assert duplicate["status"] == "duplicate" and duplicate["needs_review"] is False
    assert (
        duplicate["duplicates"]["customer/rechnung.txt"]["primary"]
        == "customer/rechnung_unterschrieben.txt"
    )
    assert sum(1 for call in llm.calls if call["name"] == "document_class") == 1
    export_workspace(WorkspaceStore(out), tmp_path / "exports")
    with (tmp_path / "exports" / "_summary.csv").open(encoding="utf-8-sig") as handle:
        rows = {row["group"]: row for row in csv.DictReader(handle)}
    assert (
        rows["customer/rechnung.txt"]["duplicates"]
        == "customer/rechnung.txt = customer/rechnung_unterschrieben.txt"
    )


def test_folder_mode_drops_duplicate_files_unless_kept(tmp_path, fake_llm):
    inbox = make_customer_folder(tmp_path)
    out = tmp_path / "results"
    llm = fake_llm(handler)
    run_once(inbox, out, llm)
    result = WorkspaceStore(out).results.get("customer")
    assert result["files"] == ["customer/rechnung_unterschrieben.txt"]
    assert "customer/rechnung.txt" in result["duplicates"]
    assert any("skipped, same text" in warning for warning in result["warnings"])

    run_once(inbox, out, llm, keep_duplicates=True)
    result = WorkspaceStore(out).results.get("customer")
    assert result["files"] == [
        "customer/rechnung.txt",
        "customer/rechnung_unterschrieben.txt",
    ]
    assert "duplicates" not in result


def test_empty_file_error_is_shown_as_the_group_error(tmp_path, fake_llm):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "leer.pdf").write_bytes(b"")
    llm = fake_llm(handler)
    out = tmp_path / "out"
    store = WorkspaceStore(out, create=True)
    run(
        discover_groups(inbox, exclude=[out], group_by="file"),
        converter=Converter(store),
        classifier=LlmClassifier(llm, store),
        llm=llm,
        options=Options(classes=CLASSES, model="m"),
        store=store,
        report=lambda line: None,
    )
    result = WorkspaceStore(out).results.get("leer.pdf")
    assert result["status"] == "failed" and result["error"] == "empty file (0 bytes)"
    assert llm.calls == []


def test_edit_made_during_model_call_survives_result_commit(tmp_path, fake_llm):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from intextum_cli.view import Library

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "invoice.txt").write_text("Rechnung RE-1 für die Wartung. Summe 10,50 EUR")
    database = tmp_path / "results.sqlite"
    run_once(inbox, database, fake_llm(handler), forced_class="Invoice")
    library = Library(database)
    entered, release = Event(), Event()

    def slow_handler(name, user, schema):
        entered.set()
        assert release.wait(5)
        return handler(name, user, schema)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            run_once,
            inbox,
            database,
            fake_llm(slow_handler),
            forced_class="Invoice",
            force=True,
        )
        try:
            assert entered.wait(5)
            library.edit(
                "invoice.txt", "number", "CORRECTED", "verified during extraction"
            )
        finally:
            release.set()
        future.result(timeout=10)
    result = library.result("invoice.txt")
    assert result["data"]["number"] == "CORRECTED"
    assert result["fields"]["number"]["extracted_value"] == "RE-1"
    assert len(result["edits"]) == 1


def test_result_uses_text_captured_before_source_changes(tmp_path, fake_llm):
    from intextum_cli.view import Library

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    path = inbox / "invoice.txt"
    original = "Rechnung RE-1 für die Wartung. Summe 10,50 EUR"
    path.write_text(original)
    database = tmp_path / "results.sqlite"

    def changing_handler(name, user, schema):
        path.write_text("Completely different source after model started")
        return handler(name, user, schema)

    run_once(
        inbox,
        database,
        fake_llm(changing_handler),
        forced_class="Invoice",
        keep_duplicates=True,
    )
    library = Library(database)
    assert library.text("invoice.txt", "invoice.txt")["pages"] == [original]
    assert library.result("invoice.txt")["data"]["number"] == "RE-1"
    assert (
        "changed since extraction"
        in library.build_document("invoice.txt", "invoice.txt")["error"]
    )


def test_pipeline_rejects_different_workspaces_without_retargeting_services(
    tmp_path, fake_llm
):
    import pytest

    first = WorkspaceStore(tmp_path / "first.sqlite", create=True)
    second = WorkspaceStore(tmp_path / "second.sqlite", create=True)
    llm = fake_llm(handler)
    converter = Converter(first)
    classifier = LlmClassifier(llm, second)
    with pytest.raises(ValueError, match="classifier and results"):
        run(
            [],
            converter=converter,
            classifier=classifier,
            llm=llm,
            options=Options(classes=CLASSES, model="test"),
            store=first,
        )
    assert converter.store is first and classifier.store is second
    assert first.metadata() == second.metadata() == {}
    assert llm.calls == []
