"""Run extraction with folder configuration, model setup, and progress output."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from ..config import (
    ConfigError,
    load_llm_settings,
    load_recognition_settings,
    load_verifier_settings,
)
from ..groups import GroupsError, discover_groups
from ..schema import SchemaError, load_classes
from ..store import WorkspaceStore
from . import CommandError


def cmd_extract(args: argparse.Namespace) -> int:
    from ..classify import LlmClassifier
    from ..convert import Converter
    from ..llm import OpenAiJsonLlm
    from ..llm_endpoints import fetch_context_length
    from ..pipeline import run
    from ..processing import Options
    from ..schema import find_class
    from ..sources import SourcesError, load_overrides
    from ..stats import CallPrinter, context_warning
    from ..verification import build_verifier

    input_dir = args.input.resolve()
    database = (
        args.out or input_dir.parent / f"{input_dir.name}-results.sqlite"
    ).resolve()
    if database.is_dir():
        raise CommandError(f"database path is a directory: {database}")
    try:
        settings = load_llm_settings(
            input_dir,
            env_file=args.env_file,
            base_url=args.base_url,
            model=args.model,
            api_key=args.api_key,
        )
        recognition = load_recognition_settings(
            input_dir,
            env_file=args.env_file,
            ocr_engine=args.ocr_engine,
            ocr_languages=args.ocr_languages,
            table_mode=args.table_mode,
            detect_marks=args.detect_marks,
            document_timeout=args.document_timeout,
        )
        verifier_settings = (
            None
            if args.no_verify
            else load_verifier_settings(
                input_dir,
                env_file=args.env_file,
                model=args.verifier_model,
                base_url=args.verifier_base_url,
                api_key=args.verifier_api_key,
                threshold=args.verifier_threshold,
                max_chars=args.max_chars,
            )
        )
        classes = load_classes(args.schemas)
        overrides = load_overrides(input_dir)
        unsupported: list[Path] = []
        excluded: list[Path] = []
        schemas = args.schemas.resolve()
        groups = discover_groups(
            input_dir,
            exclude=[
                database,
                # Schemas may live inside the input folder; they are not documents.
                # A schema path that contains the input folder must not exclude it.
                *([] if input_dir.is_relative_to(schemas) else [schemas]),
                *(
                    Path(str(database) + suffix)
                    for suffix in ("-wal", "-shm", "-journal")
                ),
            ],
            group_by=args.group_by,
            unsupported=unsupported,
            exclude_patterns=args.exclude,
            excluded_files=excluded,
        )
    except (ConfigError, SchemaError, GroupsError, SourcesError) as exc:
        raise CommandError(str(exc)) from exc
    if args.forced_class and find_class(classes, args.forced_class) is None:
        raise CommandError(f"unknown class '{args.forced_class}'")
    if excluded:
        print(
            f"excluded {len(excluded)} file(s) matching {', '.join(args.exclude)}",
            file=sys.stderr,
        )
    if unsupported:
        counts = Counter(path.suffix.lower() or "(none)" for path in unsupported)
        listed = ", ".join(
            f"{suffix} {count}" for suffix, count in counts.most_common()
        )
        print(
            f"skipped {len(unsupported)} unsupported file(s): {listed}", file=sys.stderr
        )
    if not groups:
        raise CommandError(f"no supported files found in {input_dir}")

    print(
        f"{len(groups)} group(s), {len(classes)} class(es) → {database}",
        file=sys.stderr,
    )
    if settings.env_file is not None:
        print(f"settings from {settings.env_file}", file=sys.stderr)
    context_length = None
    if settings.model:
        context_length = args.context_length or fetch_context_length(
            settings.base_url, settings.model
        )
    context = f"{context_length:,} tokens" if context_length else "unknown"
    print(
        f"model {settings.model} @ {settings.base_url} · context {context} · "
        f"max output {args.max_output_tokens:,} tokens · "
        f"max source {args.max_chars:,} chars · "
        f"thinking {'on' if args.thinking else 'off'}",
        file=sys.stderr,
    )
    if verifier_settings is not None:
        print(
            f"verifier {verifier_settings.model} @ {verifier_settings.base_url} · "
            f"flag below {verifier_settings.threshold:g}",
            file=sys.stderr,
        )
    warning = context_warning(context_length, args.max_chars, args.max_output_tokens)
    if warning:
        print(warning, file=sys.stderr)
    if args.dry_run:
        for group in groups:
            label = group.document_class or args.forced_class or "classify"
            print(f"- {group.name} [{label}]")
            for name in group.relative_files:
                print(f"    {name}")
        return 0

    needs_classifier = any(
        not (group.document_class or args.forced_class) for group in groups
    )
    needs_llm = needs_classifier or (
        not args.classify_only and any(c.fields for c in classes)
    )
    if needs_llm and not settings.model:
        raise CommandError("set --model or INTEXTUM_MODEL in the environment or .env")
    printer = CallPrinter(quiet=args.quiet)
    llm = None
    if settings.model:
        llm = OpenAiJsonLlm(
            base_url=settings.base_url,
            model=settings.model,
            api_key=settings.api_key,
            max_output_tokens=args.max_output_tokens,
            context_length=context_length,
            on_call=printer,
            on_progress=printer.progress,
            thinking=args.thinking,
        )
    has_external = not args.classify_only and any(
        field.external for c in classes for field in c.fields
    )
    # Choosing a separate source file classifies its candidates, so external
    # fields need the classifier even when every group has a fixed class.
    store = WorkspaceStore(database, create=True)
    classifier = (
        LlmClassifier(llm, store)
        if (needs_classifier or has_external) and llm
        else None
    )
    options = Options(
        classes=classes,
        model=settings.model or "",
        base_url=settings.base_url,
        forced_class=args.forced_class,
        max_chars=args.max_chars,
        retries=args.retries,
        force=args.force,
        classify_only=args.classify_only,
        force_ocr=args.force_ocr,
        ocr_engine=recognition.ocr_engine,
        ocr_languages=recognition.ocr_languages,
        table_mode=recognition.table_mode,
        detect_marks=recognition.detect_marks,
        document_timeout=recognition.document_timeout,
        max_output_tokens=args.max_output_tokens,
        thinking=args.thinking,
        context_length=context_length,
        keep_duplicates=args.keep_duplicates,
        overrides=overrides,
    )
    converter = Converter(
        store,
        force_ocr=options.force_ocr,
        ocr_engine=options.ocr_engine,
        ocr_languages=options.ocr_languages,
        table_mode=options.table_mode,
        detect_marks=options.detect_marks,
        document_timeout=options.document_timeout,
    )
    summary = run(
        groups,
        converter=converter,
        classifier=classifier,
        llm=llm,
        options=options,
        store=store,
        report=lambda line: (printer.clear(), print(line, file=sys.stderr)),
        verifier=build_verifier(verifier_settings) if verifier_settings else None,
    )
    verified = f", {summary.verified} verified" if verifier_settings else ""
    print(
        f"done: {summary.processed} processed, "
        f"{summary.unchanged} unchanged{verified}, "
        f"{summary.needs_review} need review, {summary.duplicates} duplicate(s), "
        f"{summary.failed} failed → {database}",
        file=sys.stderr,
    )
    if printer.summary():
        print(printer.summary(), file=sys.stderr)
    return 1 if summary.failed else 0
