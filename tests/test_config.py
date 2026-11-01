import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from intextum_cli.cli import main
from intextum_cli.config import (
    DEFAULT_BASE_URL,
    ConfigError,
    load_llm_settings,
    load_recognition_settings,
)

ENV_NAMES = (
    "OPENAI_BASE_URL",
    "INTEXTUM_MODEL",
    "OPENAI_API_KEY",
    "INTEXTUM_OCR_ENGINE",
    "INTEXTUM_OCR_LANGUAGES",
    "INTEXTUM_TABLE_MODE",
    "INTEXTUM_DETECT_MARKS",
)


@pytest.fixture(autouse=True)
def clear_model_environment(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def write_settings(path, label):
    path.write_text(
        f"OPENAI_BASE_URL=http://{label}:1234/v1\n"
        f"INTEXTUM_MODEL={label}-model\n"
        f"OPENAI_API_KEY={label}-key\n",
        encoding="utf-8",
    )


def test_discovers_settings_from_input_parents_independent_of_cwd(
    tmp_path, monkeypatch
):
    project = tmp_path / "project"
    inbox = project / "documents" / "inbox"
    inbox.mkdir(parents=True)
    write_settings(project / ".env", "project")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    write_settings(unrelated / ".env", "unrelated")
    monkeypatch.chdir(unrelated)

    settings = load_llm_settings(inbox)
    assert settings.base_url == "http://project:1234/v1"
    assert settings.model == "project-model"
    assert settings.api_key == "project-key"
    assert settings.env_file == project / ".env"


def test_nearest_file_replaces_parent_settings(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write_settings(tmp_path / ".env", "parent")
    (inbox / ".env").write_text("INTEXTUM_MODEL=inbox-model\n")

    settings = load_llm_settings(inbox)
    assert settings.model == "inbox-model"
    assert settings.base_url == DEFAULT_BASE_URL
    assert settings.api_key is None
    assert settings.env_file == inbox / ".env"


@pytest.mark.parametrize("source", ["file", "environment", "flags"])
def test_setting_precedence(tmp_path, monkeypatch, source):
    write_settings(tmp_path / ".env", "file")
    if source in {"environment", "flags"}:
        monkeypatch.setenv("OPENAI_BASE_URL", "http://environment:1234/v1")
        monkeypatch.setenv("INTEXTUM_MODEL", "environment-model")
        monkeypatch.setenv("OPENAI_API_KEY", "environment-key")
    overrides = (
        {
            "base_url": "http://flags:1234/v1",
            "model": "flags-model",
            "api_key": "flags-key",
        }
        if source == "flags"
        else {}
    )

    settings = load_llm_settings(tmp_path, **overrides)
    assert settings.base_url == f"http://{source}:1234/v1"
    assert settings.model == f"{source}-model"
    assert settings.api_key == f"{source}-key"


def test_explicit_file_replaces_discovery_and_is_relative_to_cwd(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write_settings(inbox / ".env", "automatic")
    write_settings(tmp_path / ".env.selected", "selected")
    monkeypatch.chdir(tmp_path)

    settings = load_llm_settings(inbox, env_file=Path(".env.selected"))
    assert settings.model == "selected-model"
    assert settings.env_file == tmp_path / ".env.selected"


def test_missing_explicit_file_does_not_fall_back(tmp_path):
    write_settings(tmp_path / ".env", "automatic")
    with pytest.raises(ConfigError, match="settings file not found"):
        load_llm_settings(tmp_path, env_file=tmp_path / ".env.missing")


def test_unreadable_encoding_is_a_configuration_error(tmp_path):
    path = tmp_path / ".env"
    path.write_bytes(b"\xff")
    with pytest.raises(ConfigError, match="cannot read settings file"):
        load_llm_settings(tmp_path)


def test_quotes_comments_bom_and_literal_variable_syntax(tmp_path, monkeypatch):
    monkeypatch.setenv("VALUE", "must-not-be-substituted")
    (tmp_path / ".env").write_text(
        '\ufeffexport INTEXTUM_MODEL="quoted/model" # a comment\n'
        "OPENAI_API_KEY='literal#${VALUE}' # another comment\n",
        encoding="utf-8",
    )
    settings = load_llm_settings(tmp_path)
    assert settings.model == "quoted/model"
    assert settings.api_key == "literal#${VALUE}"


def test_empty_settings_use_defaults(tmp_path):
    (tmp_path / ".env").write_text(
        "OPENAI_BASE_URL=\nINTEXTUM_MODEL\nOPENAI_API_KEY=\n"
    )
    settings = load_llm_settings(tmp_path)
    assert settings.base_url == DEFAULT_BASE_URL
    assert settings.model is None
    assert settings.api_key is None


def test_projects_do_not_leak_settings_into_each_other_or_environment(tmp_path):
    for label in ("first", "second"):
        project = tmp_path / label
        project.mkdir()
        write_settings(project / ".env", label)
        assert load_llm_settings(project).model == f"{label}-model"
    assert all(name not in os.environ for name in ENV_NAMES)


def test_recognition_settings_use_defaults_file_environment_and_flags(
    tmp_path, monkeypatch
):
    defaults = load_recognition_settings(tmp_path)
    assert (defaults.ocr_engine, defaults.ocr_languages, defaults.table_mode) == (
        "auto",
        [],
        "ruled",
    )
    assert defaults.detect_marks is False
    (tmp_path / ".env").write_text(
        "INTEXTUM_OCR_ENGINE=tesseract\n"
        "INTEXTUM_OCR_LANGUAGES=deu, eng\n"
        "INTEXTUM_TABLE_MODE=predicted\n"
        "INTEXTUM_DETECT_MARKS=yes\n"
    )
    settings = load_recognition_settings(tmp_path)
    assert settings.ocr_engine == "tesseract"
    assert settings.ocr_languages == ["deu", "eng"]
    assert settings.table_mode == "predicted"
    assert settings.detect_marks is True
    monkeypatch.setenv("INTEXTUM_TABLE_MODE", "docling")
    assert load_recognition_settings(tmp_path).table_mode == "docling"
    settings = load_recognition_settings(
        tmp_path,
        ocr_engine="auto",
        ocr_languages=["fra"],
        table_mode="ruled",
        detect_marks=False,
    )
    assert settings.ocr_engine == "auto"
    assert settings.ocr_languages == ["fra"]
    assert settings.table_mode == "ruled"
    assert settings.detect_marks is False


@pytest.mark.parametrize(
    "line",
    [
        "INTEXTUM_OCR_ENGINE=easyocr",
        "INTEXTUM_TABLE_MODE=guess",
        "INTEXTUM_DETECT_MARKS=maybe",
    ],
)
def test_invalid_recognition_settings_are_configuration_errors(tmp_path, line):
    (tmp_path / ".env").write_text(line + "\n")
    with pytest.raises(ConfigError, match=line.split("=")[0]):
        load_recognition_settings(tmp_path)


def test_convert_command_reads_recognition_settings_from_env(
    tmp_path, monkeypatch, capsys
):
    from intextum_cli.convert import ConvertedFile, Converter

    (tmp_path / ".env").write_text(
        "INTEXTUM_OCR_LANGUAGES=deu\nINTEXTUM_TABLE_MODE=docling\n"
    )
    path = tmp_path / "notes.txt"
    path.write_text("Readable source text")
    seen = []

    def convert(self, path, name=None):
        seen.append((self.ocr_engine, self.ocr_languages, self.table_mode))
        return ConvertedFile(path.name, ["Readable source text"])

    monkeypatch.setattr(Converter, "convert", convert)
    assert main(["convert", str(path)]) == 0
    assert seen == [("auto", ("deu",), "docling")]
    (tmp_path / ".env").write_text("INTEXTUM_TABLE_MODE=guess\n")
    assert main(["convert", str(path)]) != 0
    assert "INTEXTUM_TABLE_MODE" in capsys.readouterr().err


def make_project(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "note.txt").write_text("A sample business letter with enough text.")
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    (schemas / "letter.yaml").write_text("class: Letter\n")
    write_settings(tmp_path / ".env", "project")
    return inbox, schemas


@pytest.mark.parametrize(
    "discovered_context,explicit_context", [(8192, None), (8192, 16384), (None, None)]
)
def test_extract_passes_project_settings_to_client_and_pipeline(
    tmp_path, monkeypatch, capsys, discovered_context, explicit_context
):
    from intextum_cli import llm, llm_endpoints, pipeline
    from intextum_cli.processing import Summary

    inbox, schemas = make_project(tmp_path)
    captured = {}

    def make_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(model=kwargs["model"], base_url=kwargs["base_url"])

    def run(groups, **kwargs):
        captured["options"] = kwargs["options"]
        captured["ocr_engine"] = kwargs["converter"].ocr_engine
        captured["ocr_languages"] = kwargs["converter"].ocr_languages
        captured["table_mode"] = kwargs["converter"].table_mode
        return Summary()

    monkeypatch.setattr(llm, "OpenAiJsonLlm", make_client)
    monkeypatch.setattr(
        llm_endpoints, "fetch_context_length", lambda *args: discovered_context
    )
    monkeypatch.setattr(pipeline, "run", run)
    args = [
        "extract",
        str(inbox),
        "-s",
        str(schemas),
        "--thinking",
        "--max-output-tokens",
        "8192",
        "--ocr-engine",
        "tesseract",
        "--ocr-language",
        "deu",
        "--table-mode",
        "docling",
    ]
    if explicit_context is not None:
        args += ["--context-length", str(explicit_context)]
    assert main(args) == 0
    assert captured["base_url"] == "http://project:1234/v1"
    assert captured["model"] == "project-model"
    assert captured["api_key"] == "project-key"
    assert captured["options"].base_url == "http://project:1234/v1"
    assert captured["options"].model == "project-model"
    assert captured["options"].thinking == captured["thinking"] is True
    assert captured["options"].ocr_engine == captured["ocr_engine"] == "tesseract"
    assert captured["options"].ocr_languages == ["deu"]
    assert captured["ocr_languages"] == ("deu",)
    assert captured["options"].table_mode == captured["table_mode"] == "docling"
    assert (
        captured["options"].max_output_tokens == captured["max_output_tokens"] == 8192
    )
    assert (
        captured["options"].context_length
        == captured["context_length"]
        == (explicit_context or discovered_context)
    )
    stderr = capsys.readouterr().err
    assert f"settings from {tmp_path / '.env'}" in stderr
    assert "project-key" not in stderr


def test_dry_run_accepts_explicit_env_file_and_cli_override(tmp_path, capsys):
    inbox, schemas = make_project(tmp_path)
    selected = tmp_path / ".env.selected"
    write_settings(selected, "selected")
    assert (
        main(
            [
                "extract",
                str(inbox),
                "-s",
                str(schemas),
                "--dry-run",
                "--env-file",
                str(selected),
                "--base-url",
                "http://override:1234/v1",
                "--context-length",
                "8192",
            ]
        )
        == 0
    )
    output = capsys.readouterr()
    assert "model selected-model @ http://override:1234/v1" in output.err
    assert "note.txt" in output.out
    assert ".env" not in output.out
    assert not (tmp_path / "inbox-results").exists()


def test_schemas_inside_the_input_folder_are_not_documents(tmp_path, capsys):
    inbox, _ = make_project(tmp_path)
    schemas = inbox / "schemas"
    schemas.mkdir()
    (schemas / "letter.yaml").write_text("class: Letter\n")
    assert main(["extract", str(inbox), "-s", str(schemas), "--dry-run"]) == 0
    output = capsys.readouterr()
    assert "note.txt" in output.out
    assert "letter.yaml" not in output.out
    assert "unsupported" not in output.err + output.out


def test_cli_reports_missing_env_file(tmp_path, capsys):
    inbox, schemas = make_project(tmp_path)
    assert (
        main(
            [
                "extract",
                str(inbox),
                "-s",
                str(schemas),
                "--dry-run",
                "--env-file",
                str(tmp_path / ".env.missing"),
            ]
        )
        == 2
    )
    assert "settings file not found" in capsys.readouterr().err


@pytest.mark.parametrize("target", ["inbox", "parent"])
def test_schema_path_containing_the_input_keeps_its_documents(tmp_path, capsys, target):
    inbox, _ = make_project(tmp_path)
    schemas = inbox if target == "inbox" else tmp_path
    (schemas / "letter.yaml").write_text("class: Letter\n")
    assert main(["extract", str(inbox), "-s", str(schemas), "--dry-run"]) == 0
    assert "note.txt" in capsys.readouterr().out
