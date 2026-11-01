"""Argument definitions for the intextum commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .config import OCR_ENGINES, TABLE_MODES


def _add_ocr_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("recognition")
    group.add_argument("--force-ocr", action="store_true", help="OCR every page")
    group.add_argument(
        "--ocr-engine",
        choices=OCR_ENGINES,
        help="OCR engine (INTEXTUM_OCR_ENGINE in environment or .env; "
        "default: Docling automatic selection)",
    )
    group.add_argument(
        "--ocr-language",
        dest="ocr_languages",
        action="append",
        metavar="LANGUAGE",
        help="OCR language code; repeat for multiple languages "
        "(INTEXTUM_OCR_LANGUAGES, comma-separated, in environment or .env)",
    )
    group.add_argument(
        "--table-mode",
        choices=TABLE_MODES,
        help="table recognition (INTEXTUM_TABLE_MODE in environment or .env): "
        "Docling with ruled-form reconstruction (default), Docling cells matched "
        "to PDF text, or Docling-predicted cells",
    )
    group.add_argument(
        "--detect-marks",
        action=argparse.BooleanOptionalAction,
        help="tag text in ruled forms that lines underline, strike or cross "
        "(INTEXTUM_DETECT_MARKS in environment or .env; default: off)",
    )


def _add_llm_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("model")
    group.add_argument(
        "--env-file",
        type=Path,
        help="settings file (default: nearest .env in the input folder or a parent)",
    )
    group.add_argument(
        "--base-url",
        help="OpenAI-compatible endpoint (OPENAI_BASE_URL in environment or .env; "
        "default: local Ollama)",
    )
    group.add_argument(
        "--model",
        help="model name (INTEXTUM_MODEL in environment or .env)",
    )
    group.add_argument(
        "--api-key",
        help="API key if needed (OPENAI_API_KEY in environment or .env)",
    )
    group.add_argument("--max-output-tokens", type=int, default=4096)
    group.add_argument(
        "--thinking",
        action="store_true",
        help="let reasoning models think before answering "
        "(slower, uses output tokens; off by default)",
    )
    group.add_argument(
        "--context-length",
        type=int,
        help="the model's context window in tokens (default: ask LM Studio)",
    )
    group.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="no line per model call (the totals are still printed)",
    )


def _add_verifier_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group(
        "verification",
        "Check extracted values with a decision model after extraction "
        "(Ollama/llama.cpp /v1/systemone or OpenRouter decisions).",
    )
    group.add_argument(
        "--verifier-model",
        help="decision model, e.g. kev (INTEXTUM_VERIFIER_MODEL; unset: no checks)",
    )
    group.add_argument(
        "--verifier-base-url",
        help="decision endpoint (INTEXTUM_VERIFIER_BASE_URL; "
        "default: the extraction endpoint)",
    )
    group.add_argument(
        "--verifier-api-key",
        help="API key for a different decision endpoint (INTEXTUM_VERIFIER_API_KEY)",
    )
    group.add_argument(
        "--verifier-threshold",
        type=float,
        help="flag fields whose probability is below this "
        "(INTEXTUM_VERIFIER_THRESHOLD; default 0.3)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="intextum",
        description="Classify documents and extract schema fields, folder by folder.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("-v", "--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "extract",
        help="classify and extract every group in a folder",
        description=(
            "Each top-level subfolder is one group, each loose file is its own group, "
            "and groups.yaml in the folder can combine files explicitly."
        ),
    )
    run.add_argument("input", type=Path, help="folder with documents")
    run.add_argument(
        "-s", "--schemas", type=Path, required=True, help="schema YAML file or folder"
    )
    run.add_argument(
        "-o",
        "--out",
        type=Path,
        help="SQLite database (default: <input>-results.sqlite)",
    )
    run.add_argument(
        "--class", dest="forced_class", help="skip classification, use this class"
    )
    run.add_argument(
        "--classify-only",
        action="store_true",
        help="classify groups but skip field extraction",
    )
    run.add_argument(
        "--group-by",
        choices=["folder", "file"],
        default="folder",
        help="one group per top-level subfolder (default) or per file",
    )
    run.add_argument(
        "--exclude",
        action="append",
        metavar="REGEX",
        default=[],
        help="ignore files whose path matches this regular expression "
        "(case-insensitive, repeatable), e.g. --exclude entwurf",
    )
    run.add_argument(
        "--keep-duplicates",
        action="store_true",
        help="process copies and versions of the same document separately",
    )
    run.add_argument(
        "--max-chars",
        type=int,
        default=60_000,
        help="max source characters per group sent to the model (default 60000)",
    )
    run.add_argument(
        "--retries", type=int, default=1, help="re-asks for missing required fields"
    )
    _add_ocr_args(run)
    run.add_argument("--force", action="store_true", help="reprocess unchanged groups")
    run.add_argument(
        "--dry-run", action="store_true", help="only show groups and classes"
    )
    run.add_argument(
        "--no-verify",
        action="store_true",
        help="skip verification even when a verifier model is configured",
    )
    _add_llm_args(run)
    _add_verifier_args(run)

    verify = commands.add_parser(
        "verify",
        help="check a workspace's extracted values with a decision model",
        description=(
            "Verify completed results whose verification is missing or outdated, "
            "using the cached document text. Originals are not needed."
        ),
    )
    verify.add_argument("database", type=Path, help="workspace SQLite database")
    verify.add_argument(
        "--env-file",
        type=Path,
        help="settings file (default: nearest .env of the recorded input folder "
        "or the current folder)",
    )
    verify.add_argument(
        "--force", action="store_true", help="verify every result again"
    )
    _add_verifier_args(verify)

    view = commands.add_parser(
        "view",
        help="review a SQLite workspace in the browser",
        description="Review cached documents and correct fields in a SQLite workspace.",
    )
    view.add_argument("database", type=Path, help="workspace SQLite database")
    view.add_argument("--input", type=Path, help="optional folder containing originals")
    view.add_argument(
        "-s",
        "--schemas",
        type=Path,
        help="override embedded schemas for this review session",
    )
    view.add_argument("--port", type=int, default=8765)
    view.add_argument("--host", default="127.0.0.1")
    view.add_argument(
        "--no-browser", action="store_true", help="do not open a browser window"
    )

    exporter = commands.add_parser(
        "export", help="export current results as JSON and CSV"
    )
    exporter.add_argument("database", type=Path)
    exporter.add_argument(
        "-o", "--out", type=Path, required=True, help="export directory"
    )
    exporter.add_argument("--format", choices=["json", "csv", "all"], default="all")
    exporter.add_argument(
        "--state",
        choices=["all", "reviewed", "open"],
        default="all",
        help="export only results in this review state (default: all)",
    )

    convert = commands.add_parser("convert", help="print the text Docling extracts")
    convert.add_argument("file", type=Path)
    convert.add_argument(
        "--env-file",
        type=Path,
        help="settings file (default: nearest .env in the file's folder or a parent)",
    )
    _add_ocr_args(convert)

    check = commands.add_parser("check-schemas", help="validate schema YAML")
    check.add_argument("schemas", type=Path)

    return parser
