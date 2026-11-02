import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from intextum_cli.classify import LlmClassifier
from intextum_cli.config import ConfigError, load_verifier_settings
from intextum_cli.convert import Converter
from intextum_cli.decisions import (
    DecisionClient,
    DecisionError,
    decisions_url,
    yes_probability,
)
from intextum_cli.groups import Group
from intextum_cli.pipeline import run
from intextum_cli.processing import Options
from intextum_cli.schema import DocumentClass
from intextum_cli.store import WorkspaceStore
from intextum_cli.verification import VerifierSettings, verify_workspace
from intextum_cli.view import Library

CLASSES = [
    DocumentClass.model_validate(
        {
            "class": "Invoice",
            "fields": [
                {"name": "number", "required": True},
                {"name": "seller", "description": "Company issuing the invoice"},
            ],
        }
    )
]


class FakeDecider:
    """Answers noul questions from the value named in the instructions."""

    model = "fake-kev"

    def __init__(self, doubtful=(), error=None, classes=None):
        self.doubtful = set(doubtful)
        self.error = error
        self.classes = classes or {}
        self.calls = []

    def decide(self, state, questions):
        self.calls.append({"state": state, "questions": questions})
        if self.error:
            raise DecisionError(self.error)
        answers = {}
        for key, question in questions.items():
            if question["type"] == "choice":
                probabilities = {option: 0.0 for option in question["criteria"]}
                probabilities.update(self.classes)
                answers[key] = {"type": "choice", "probabilities": probabilities}
                continue
            doubtful = any(v in question["instructions"] for v in self.doubtful)
            answers[key] = {"type": "noul", "noul": 0.05 if doubtful else 0.97}
        return answers


@pytest.fixture
def workspace(tmp_path, fake_llm):
    root = tmp_path / "inbox"
    root.mkdir()
    (root / "invoice.txt").write_text(
        "Invoice INV-42 from Beispiel IT-Service GmbH to Muster Baumarkt GmbH"
    )
    groups = [Group("invoice", root, [root / "invoice.txt"], "Invoice")]

    def handler(name, user, schema):
        return {
            "number": {"value": "INV-42", "evidence_anchor": "INV-42"},
            "seller": {
                "value": "Muster Baumarkt GmbH",
                "evidence_anchor": "Muster Baumarkt",
            },
        }

    llm = fake_llm(handler)
    store = WorkspaceStore(tmp_path / "results.sqlite", create=True)

    def extract(decider=None, threshold=0.3, **kwargs):
        settings = VerifierSettings("fake-kev", "http://localhost:11434/v1", None)
        settings = VerifierSettings(
            settings.model, settings.base_url, None, threshold=threshold
        )
        return run(
            groups,
            converter=Converter(store),
            classifier=LlmClassifier(llm, store),
            llm=llm,
            options=Options(classes=CLASSES, model=llm.model, **kwargs),
            store=store,
            report=lambda _: None,
            verifier=(decider, settings) if decider else None,
        )

    return store, llm, extract


def test_verification_flags_doubtful_fields_after_extraction(workspace):
    store, _, extract = workspace
    decider = FakeDecider(doubtful={"Muster Baumarkt"})
    summary = extract(decider)
    assert summary.verified == 1 and summary.needs_review == 1
    result = store.results.get("invoice", by_group=True)
    assert result["review_reasons"] == ["unverified:seller"]
    assert result["fields"]["seller"]["verification"]["probability"] == 0.05
    assert result["fields"]["number"]["verification"]["model"] == "fake-kev"
    assert result["verification"]["threshold"] == 0.3
    # One request per result, with the document text and the schema description.
    (call,) = decider.calls
    assert "Invoice INV-42" in call["state"]
    seller = next(
        q for q in call["questions"].values() if "seller" in q["instructions"]
    )
    assert "Company issuing the invoice" in seller["instructions"]
    assert seller["type"] == "noul" and set(seller["criteria"]) == {"true", "false"}


def test_unchanged_results_skip_verification_and_settings_rerun_only_it(workspace):
    store, llm, extract = workspace
    decider = FakeDecider(doubtful={"Muster Baumarkt"})
    extract(decider)
    extract(decider)
    assert len(decider.calls) == 1
    llm_calls = len(llm.calls)
    # A different threshold re-runs verification, not extraction.
    extract(decider, threshold=0.01)
    assert len(decider.calls) == 2 and len(llm.calls) == llm_calls
    assert store.results.get("invoice", by_group=True)["review_reasons"] == []


def test_new_extraction_ignores_stale_verification(workspace):
    store, _, extract = workspace
    extract(FakeDecider(doubtful={"Muster Baumarkt"}))
    extract(force=True)  # Extraction without a verifier this time.
    result = store.results.get("invoice", by_group=True)
    assert "verification" not in result["fields"]["seller"]
    assert result["review_reasons"] == []
    settings = VerifierSettings("fake-kev", "http://localhost:11434/v1")
    assert store.results.verification_candidates(settings.key) == ["invoice"]


def test_correction_settles_unverified_field(workspace, tmp_path):
    store, _, extract = workspace
    extract(FakeDecider(doubtful={"Muster Baumarkt"}))
    lib = Library(store.path)
    updated = lib.edit("invoice", "seller", "Beispiel IT-Service GmbH")
    assert updated["review_reasons"] == []
    assert not updated["needs_review"]


def test_decision_failure_warns_without_flagging(workspace):
    store, _, extract = workspace
    extract(FakeDecider(error="model not found"))
    result = store.results.get("invoice", by_group=True)
    assert result["review_reasons"] == []
    assert "verification failed: model not found" in result["warnings"]
    assert result["verification"]["error"] == "model not found"


def test_verify_workspace_force_and_group_filter(workspace):
    store, _, extract = workspace
    extract()
    decider = FakeDecider()
    settings = VerifierSettings("fake-kev", "http://localhost:11434/v1")
    assert verify_workspace(store, decider, settings, groups={"other"}) == 0
    assert verify_workspace(store, decider, settings, report=lambda _: None) == 1
    assert verify_workspace(store, decider, settings, report=lambda _: None) == 0
    assert (
        verify_workspace(store, decider, settings, force=True, report=lambda _: None)
        == 1
    )


def test_decision_endpoints_and_answer_normalisation():
    assert decisions_url("http://localhost:11434/v1") == (
        "http://localhost:11434/v1/systemone"
    )
    assert (
        decisions_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080/v1/systemone"
    )
    assert decisions_url("https://openrouter.ai/api/v1") == (
        "https://openrouter.ai/api/alpha/decisions"
    )
    assert yes_probability({"noul": 0.8}) == 0.8
    assert yes_probability({"probabilities": {"true": 0.3, "false": 0.7}}) == 0.3
    assert yes_probability({"noul": True}) is None
    assert yes_probability({"noul": 1.4}) == 1.0


def test_decision_client_posts_systemone_request():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["auth"] = self.headers.get("Authorization")
            seen["body"] = json.loads(
                self.rfile.read(int(self.headers["Content-Length"]))
            )
            reply = {"answers": {"q": {"type": "noul", "noul": 0.9}}}
            if seen["body"]["model"] == "missing":
                self.send_response(404)
                reply = {"error": "model not found"}
            else:
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(reply).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_port}/v1"
        question = {"type": "noul", "instructions": "?", "criteria": {}}
        answers = DecisionClient(base, "kev:0.8b").decide("text", {"q": question})
        assert answers == {"q": {"type": "noul", "noul": 0.9}}
        assert seen["path"] == "/v1/systemone" and seen["auth"] is None
        assert seen["body"] == {
            "model": "kev:0.8b",
            "state": "text",
            "questions": {"q": question},
        }
        DecisionClient(base, "kev", api_key="secret").decide("text", {})
        assert seen["auth"] == "Bearer secret"
        with pytest.raises(DecisionError, match="HTTP 404"):
            DecisionClient(base, "missing", retries=0).decide("text", {})
    finally:
        server.shutdown()


def test_verifier_settings_resolution(tmp_path, monkeypatch):
    for name in (
        "INTEXTUM_VERIFIER_MODEL",
        "INTEXTUM_VERIFIER_BASE_URL",
        "INTEXTUM_VERIFIER_API_KEY",
        "INTEXTUM_VERIFIER_THRESHOLD",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    assert load_verifier_settings(tmp_path) is None
    (tmp_path / ".env").write_text(
        "OPENAI_BASE_URL=https://openrouter.ai/api/v1\n"
        "OPENAI_API_KEY=router-key\n"
        "INTEXTUM_VERIFIER_MODEL=typesafe/jev-1.13\n"
    )
    settings = load_verifier_settings(tmp_path)
    assert settings.base_url == "https://openrouter.ai/api/v1"
    assert settings.api_key == "router-key" and settings.threshold == 0.3
    # Another endpoint never receives the extraction key.
    local = load_verifier_settings(
        tmp_path, model="kev", base_url="http://127.0.0.1:11434"
    )
    assert local.api_key is None and local.model == "kev"
    assert local.key != settings.key
    assert load_verifier_settings(tmp_path, threshold=0.5).threshold == 0.5
    with pytest.raises(ConfigError, match="between 0 and 1"):
        load_verifier_settings(tmp_path, threshold=1.5)


def test_verify_command_uses_cached_text(workspace, monkeypatch, capsys):
    from intextum_cli.cli import main

    store, _, extract = workspace
    extract()
    for name in ("INTEXTUM_VERIFIER_MODEL", "INTEXTUM_VERIFIER_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    decider = FakeDecider(doubtful={"INV-42"})
    monkeypatch.setattr(
        "intextum_cli.verification.build_verifier",
        lambda settings: (decider, settings),
    )
    assert main(["verify", str(store.path)]) == 2  # No verifier configured.
    assert "INTEXTUM_VERIFIER_MODEL" in capsys.readouterr().err
    assert main(["verify", str(store.path), "--verifier-model", "kev"]) == 0
    assert "1 verified, 1 result(s) with doubtful values or class" in (
        capsys.readouterr().err
    )
    result = store.results.get("invoice", by_group=True)
    assert result["review_reasons"] == ["unverified:number"]


@pytest.fixture
def classified(tmp_path, fake_llm):
    """Automatic classification: the classifier answers with ``reply['class']``."""
    root = tmp_path / "inbox"
    root.mkdir()
    (root / "letter.txt").write_text("Payment reminder about invoice INV-42.")
    groups = [Group("letter", root, [root / "letter.txt"])]
    reply = {"class": None}

    def handler(name, user, schema):
        if name == "document_class":
            return {"class": reply["class"], "reason": "test"}
        return {"number": {"value": "INV-42", "evidence_anchor": "INV-42"}}

    llm = fake_llm(handler)
    store = WorkspaceStore(tmp_path / "results.sqlite", create=True)

    def extract(decider, **kwargs):
        settings = VerifierSettings("fake-kev", "http://localhost:11434/v1")
        run(
            groups,
            converter=Converter(store),
            classifier=LlmClassifier(llm, store),
            llm=llm,
            options=Options(classes=CLASSES, model=llm.model, **kwargs),
            store=store,
            report=lambda _: None,
            verifier=(decider, settings),
        )
        return store.results.get("letter", by_group=True)

    return reply, extract


def test_unclassified_result_gets_confidence_that_no_class_fits(classified):
    _, extract = classified
    decider = FakeDecider(classes={"none_of_these": 0.97, "Invoice": 0.03})
    result = extract(decider)
    assert result["status"] == "unclassified"
    (call,) = decider.calls
    question = call["questions"]["document_class"]
    assert set(question["criteria"]) == {"Invoice", "none_of_these"}
    check = result["class_check"]
    assert check["unclassified"] and check["probability"] == 0.97
    assert check["suggestion"] is None
    assert "class_doubtful" not in result["review_reasons"]


def test_unclassified_result_suggests_a_likely_class(classified):
    _, extract = classified
    result = extract(FakeDecider(classes={"none_of_these": 0.2, "Invoice": 0.8}))
    check = result["class_check"]
    assert check["suggestion"] == "Invoice"
    assert check["suggestion_probability"] == 0.8
    assert "class_doubtful" in result["review_reasons"]


def test_automatic_class_is_doubted_when_another_option_wins(classified):
    reply, extract = classified
    reply["class"] = "Invoice"
    result = extract(FakeDecider(classes={"none_of_these": 0.9, "Invoice": 0.1}))
    assert result["class"]["name"] == "Invoice"
    assert result["class_check"]["suggestion"] is None
    assert result["review_reasons"][-1] == "class_doubtful"
    assert result["needs_review"]


def test_configured_class_is_not_doubted(workspace):
    store, _, extract = workspace
    decider = FakeDecider(classes={"none_of_these": 1.0})
    extract(decider)
    # groups.yaml/--class choices are deliberate; only fields are checked.
    assert "document_class" not in decider.calls[0]["questions"]
    assert "class_check" not in store.results.get("invoice", by_group=True)


def test_path_values_are_not_checked_against_the_document(tmp_path, fake_llm):
    root = tmp_path / "P-77 Example" / "inbox"
    root.mkdir(parents=True)
    (root / "invoice.txt").write_text("Invoice INV-42 from Example Ltd")
    classes = [
        DocumentClass.model_validate(
            {
                "class": "Invoice",
                "fields": [
                    {"name": "project", "from_path": {"pattern": r"/(P-\d+)[^/]*/"}},
                    {"name": "number"},
                ],
            }
        )
    ]
    llm = fake_llm(
        lambda *_: {"number": {"value": "INV-42", "evidence_anchor": "INV-42"}}
    )
    store = WorkspaceStore(tmp_path / "results.sqlite", create=True)
    decider = FakeDecider(doubtful={"P-77"})
    summary = run(
        [Group("invoice", root, [root / "invoice.txt"], "Invoice")],
        converter=Converter(store),
        classifier=LlmClassifier(llm, store),
        llm=llm,
        options=Options(classes=classes, model=llm.model),
        store=store,
        report=lambda _: None,
        verifier=(decider, VerifierSettings("fake-kev", "http://localhost:1/v1", None)),
    )
    assert summary.needs_review == 0
    result = store.results.get("invoice", by_group=True)
    assert result["data"]["project"] == "P-77"
    assert "verification" not in result["fields"]["project"]
    assert result["fields"]["number"]["verification"]["probability"] == 0.97
    (call,) = decider.calls
    assert all("P-77" not in q["instructions"] for q in call["questions"].values())
