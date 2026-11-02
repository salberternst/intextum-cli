"""Review, export, and standalone document conversion commands."""

from __future__ import annotations

import argparse

from ..store import WorkspaceStore
from . import CommandError


def cmd_view(args: argparse.Namespace) -> int:
    from ..view import ViewError, serve

    try:
        serve(
            args.database,
            input_dir=args.input,
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            schemas=args.schemas,
        )
    except ViewError as exc:
        raise CommandError(str(exc)) from exc
    except OSError as exc:
        raise CommandError(f"cannot serve on {args.host}:{args.port}: {exc}") from exc
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    import sys
    from pathlib import Path

    from ..config import ConfigError, load_verifier_settings
    from ..verification import build_verifier, verify_workspace

    store = WorkspaceStore(args.database)
    recorded = store.metadata().get("input")
    folder = Path(recorded) if recorded and Path(recorded).is_dir() else Path.cwd()
    try:
        settings = load_verifier_settings(
            folder,
            env_file=args.env_file,
            model=args.verifier_model,
            base_url=args.verifier_base_url,
            api_key=args.verifier_api_key,
            threshold=args.verifier_threshold,
        )
    except ConfigError as exc:
        raise CommandError(str(exc)) from exc
    if settings is None:
        raise CommandError(
            "set --verifier-model or INTEXTUM_VERIFIER_MODEL in the environment or .env"
        )
    print(
        f"verifier {settings.model} @ {settings.base_url} · "
        f"flag below {settings.threshold:g}",
        file=sys.stderr,
    )
    decider, _ = build_verifier(settings)
    with store.lock("extract"):
        count = verify_workspace(
            store,
            decider,
            settings,
            force=args.force,
            report=lambda line: print(line, file=sys.stderr),
        )
    flagged = sum(
        any(
            r.startswith("unverified:") or r == "class_doubtful"
            for r in entry["review_reasons"]
        )
        for entry in store.results.index()
    )
    print(
        f"done: {count} verified, {flagged} result(s) with doubtful values or class",
        file=sys.stderr,
    )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from ..exports import export_workspace

    count = export_workspace(
        WorkspaceStore(args.database), args.out, args.format, args.state
    )
    scope = "" if args.state == "all" else f" {args.state}"
    print(f"exported {count}{scope} result(s) as {args.format} to {args.out}")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    from ..config import ConfigError, load_recognition_settings
    from ..convert import Converter

    if not args.file.is_file():
        raise CommandError(f"file not found: {args.file}")
    try:
        recognition = load_recognition_settings(
            args.file.resolve().parent,
            env_file=args.env_file,
            ocr_engine=args.ocr_engine,
            ocr_languages=args.ocr_languages,
            table_mode=args.table_mode,
            detect_marks=args.detect_marks,
            document_timeout=args.document_timeout,
        )
    except ConfigError as exc:
        raise CommandError(str(exc)) from exc
    converted = Converter(
        force_ocr=args.force_ocr,
        ocr_engine=recognition.ocr_engine,
        ocr_languages=recognition.ocr_languages,
        table_mode=recognition.table_mode,
        detect_marks=recognition.detect_marks,
        document_timeout=recognition.document_timeout,
    ).convert(args.file)
    if converted.error:
        raise CommandError(converted.error)
    for number, page in enumerate(converted.pages, start=1):
        if converted.paged:
            print(f"--- page {number} ---")
        print(page)
    return 0
