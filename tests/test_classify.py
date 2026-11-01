from pathlib import Path

import pytest

from intextum_cli.classify import NO_MATCH, LlmClassifier
from intextum_cli.convert import ConvertedFile
from intextum_cli.schema import DocumentClass, SchemaField
from intextum_cli.store import WorkspaceStore

INVOICE = DocumentClass.model_validate({"class": "Invoice", "description": "A bill"})
LETTER = DocumentClass.model_validate({"class": "Letter"})


def test_classification_is_cached_per_text_and_classes(tmp_path, fake_llm):
    llm = fake_llm(
        lambda name, user, schema: (
            {"class": "Invoice", "reason": "bill"}
            if "Rechnung" in user
            else {"class": NO_MATCH, "reason": "?"}
        )
    )
    cache = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    invoice = [ConvertedFile("a.pdf", ["Rechnung Nr. 1"])]

    first = LlmClassifier(llm, store=cache).classify(invoice, [INVOICE, LETTER])
    again = LlmClassifier(llm, store=cache).classify(invoice, [INVOICE, LETTER])
    assert (first.name, first.reason) == ("Invoice", "bill") and again == first
    assert len(llm.calls) == 1

    classifier = LlmClassifier(llm, store=cache)
    classifier.classify(invoice, [INVOICE])  # different classes
    classifier.classify([ConvertedFile("b.pdf", ["Rechnung Nr. 1"])], [INVOICE, LETTER])
    # The file name is part of what the model sees, so a renamed file is asked again.
    assert len(llm.calls) == 3


def test_failed_classifications_are_not_cached(tmp_path, fake_llm):
    llm = fake_llm(lambda name, user, schema: "not json")
    classifier = LlmClassifier(
        llm, store=WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    )
    files = [ConvertedFile("a.pdf", ["Rechnung"])]
    assert classifier.classify(files, [INVOICE]).error == "model returned invalid JSON"
    classifier.classify(files, [INVOICE])
    assert len(llm.calls) == 2


def test_field_changes_keep_cached_classifications(tmp_path, fake_llm):
    llm = fake_llm(lambda name, user, schema: {"class": "Invoice", "reason": "bill"})
    cache = WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    files = [ConvertedFile("a.pdf", ["Rechnung Nr. 1"])]
    LlmClassifier(llm, store=cache).classify(files, [INVOICE, LETTER])
    with_fields = INVOICE.model_copy(
        update={"fields": [SchemaField.model_validate({"name": "Nummer"})]}
    )
    LlmClassifier(llm, store=cache).classify(files, [with_fields, LETTER])
    assert len(llm.calls) == 1
    renamed = INVOICE.model_copy(update={"description": "A bill or invoice"})
    LlmClassifier(llm, store=cache).classify(files, [renamed, LETTER])
    assert len(llm.calls) == 2


def test_endpoint_changes_invalidate_classification_cache(tmp_path, fake_llm):
    llm = fake_llm(lambda name, user, schema: {"class": "Invoice", "reason": "bill"})
    llm.base_url = "http://first:1234/v1"
    classifier = LlmClassifier(
        llm, store=WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    )
    files = [ConvertedFile("a.pdf", ["Rechnung Nr. 1"])]
    classifier.classify(files, [INVOICE])
    llm.base_url += "/"
    classifier.classify(files, [INVOICE])
    assert len(llm.calls) == 1
    llm.base_url = "http://second:1234/v1"
    classifier.classify(files, [INVOICE])
    assert len(llm.calls) == 2


@pytest.mark.parametrize(
    "setting,initial,changed",
    [
        ("thinking", False, True),
        ("context_length", None, 8192),
        ("context_length", 8192, 16384),
        ("max_output_tokens", 4096, 8192),
    ],
)
def test_generation_changes_refresh_cached_classifications(
    tmp_path, fake_llm, setting, initial, changed
):
    llm = fake_llm(lambda name, user, schema: {"class": "Invoice", "reason": "bill"})
    setattr(llm, setting, initial)
    classifier = LlmClassifier(
        llm, store=WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    )
    files = [ConvertedFile("invoice.txt", ["Rechnung Nr. 1"])]
    classifier.classify(files, [INVOICE])
    classifier.classify(files, [INVOICE])
    assert len(llm.calls) == 1

    setattr(llm, setting, changed)
    classifier.classify(files, [INVOICE])
    classifier.classify(files, [INVOICE])
    assert len(llm.calls) == 2

    setattr(llm, setting, initial)
    classifier.classify(files, [INVOICE])
    assert len(llm.calls) == 2


@pytest.mark.parametrize("module", ["llm", "llm_types", "llm_endpoints"])
def test_llm_code_changes_refresh_classifications(
    tmp_path, monkeypatch, fake_llm, module
):
    llm = fake_llm(lambda name, user, schema: {"class": "Invoice", "reason": "bill"})
    classifier = LlmClassifier(
        llm, store=WorkspaceStore(tmp_path / "workspace.sqlite", create=True)
    )
    files = [ConvertedFile("invoice.txt", ["Rechnung Nr. 1"])]
    classifier.classify(files, [INVOICE])
    read_bytes = Path.read_bytes

    def changed_code(path):
        content = read_bytes(path)
        return (
            content + b"\n# changed model behavior"
            if path.name == f"{module}.py"
            else content
        )

    monkeypatch.setattr(Path, "read_bytes", changed_code)
    classifier.classify(files, [INVOICE])
    assert len(llm.calls) == 2
