"""Explicit viewer extraction using the recorded scope and current model settings."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING

from .classify import LlmClassifier
from .config import DEFAULT_BASE_URL, load_llm_settings, load_verifier_settings
from .convert import Converter
from .groups import Group
from .llm import OpenAiJsonLlm
from .pipeline import run
from .processing import Options
from .schema import find_class
from .sources import load_overrides
from .verification import build_verifier

if TYPE_CHECKING:
    from .view import Library


def availability(library: Library) -> str | None:
    if library.input_dir is None:
        return "Original documents are unavailable. Start view with --input FOLDER."
    if "extraction_plan" not in library.store.metadata():
        return "Run CLI extraction once to record the processing settings."
    return None


def reextract(library: Library, slug: str, revision: str) -> dict:
    from .review_state import ReviewConflict

    # Coordinate with CLI runs and class changes without holding a SQLite write
    # transaction across model calls. Field corrections may still be saved.
    with library.store.lock("extract"):
        result = library.result(slug)
        if result is None:
            raise KeyError(slug)
        if result["review"]["revision"] != revision:
            raise ReviewConflict("This result changed. Refresh before extracting.")
        _run_groups(library, [result])
        return library.result(slug)


def reextract_many(
    library: Library, slugs: list[str], progress: Callable[[int], None] | None = None
) -> list[dict]:
    """Re-extract several results in one pipeline run.

    ``progress`` receives the number of finished groups after each one.
    """
    with library.store.lock("extract"):
        slugs = list(dict.fromkeys(slugs))
        results = []
        for slug in slugs:
            result = library.result(slug)
            if result is None:
                raise KeyError(slug)
            results.append(result)
        if not results:
            return []
        finished = 0

        def group_finished(_name: str) -> None:
            nonlocal finished
            finished += 1
            if progress is not None:
                progress(finished)

        _run_groups(library, results, group_finished)
        return [library.result(slug) for slug in slugs]


def _run_groups(
    library: Library,
    results: list[dict],
    on_group_finished: Callable[[str], None] | None = None,
) -> None:
    if error := availability(library):
        raise ValueError(error)
    root = library.input_dir
    plan = json.loads(library.store.metadata()["extraction_plan"])
    groups = []
    for spec in plan["groups"]:
        files = []
        for relative in spec["files"]:
            path = (root / relative).resolve()
            if root not in path.parents or any(
                part.startswith(".") for part in path.relative_to(root).parts
            ):
                raise ValueError("The recorded input contains an invalid path.")
            if not path.is_file():
                raise ValueError(f"Original document is unavailable: {relative}")
            files.append(path)
        groups.append(Group(spec["name"], root, files, spec.get("class")))
    by_name = {group.name: group for group in groups}
    for result in results:
        if result["group"] not in by_name:
            raise ValueError(
                f"{result['group']} is absent from the latest CLI extraction scope."
            )
    saved = plan["options"]
    verifier = load_verifier_settings(root, max_chars=saved.get("max_chars"))
    settings = load_llm_settings(
        root,
        default_model=saved.get("model") or results[0].get("model"),
        default_base_url=saved.get("base_url") or DEFAULT_BASE_URL,
    )
    classes = (
        library.classes
        if library.classes is not None
        else library.store.results.classes(results[0]["group"])
    )
    options = Options(
        **{
            **saved,
            "classes": classes,
            "model": settings.model or "",
            "base_url": settings.base_url,
            "classify_only": False,
            "force": True,
            "overrides": load_overrides(root),
        }
    )
    if not settings.model and any(
        _needs_model(library, by_name[r["group"]], classes, options) for r in results
    ):
        raise ValueError(
            "Set INTEXTUM_MODEL in the input folder's .env or environment."
        )
    llm = (
        OpenAiJsonLlm(
            base_url=settings.base_url,
            model=settings.model,
            api_key=settings.api_key,
            max_output_tokens=options.max_output_tokens,
            context_length=options.context_length,
            thinking=options.thinking,
        )
        if settings.model
        else None
    )
    run(
        groups,
        converter=Converter(
            library.store,
            force_ocr=options.force_ocr,
            ocr_engine=options.ocr_engine,
            ocr_languages=options.ocr_languages,
            table_mode=options.table_mode,
            detect_marks=options.detect_marks,
        ),
        classifier=LlmClassifier(llm, library.store) if llm else None,
        llm=llm,
        options=options,
        store=library.store,
        only_groups={result["group"] for result in results},
        report=lambda _: None,
        verifier=build_verifier(verifier) if verifier else None,
        on_group_finished=on_group_finished,
    )


def _needs_model(library: Library, group: Group, classes, options: Options) -> bool:
    choice = library.store.results.choice(group.name)
    if choice["action"] == "no_match":
        return False
    forced = choice.get("class_name") or group.document_class or options.forced_class
    if not forced:
        return True
    selected = find_class(classes, forced)
    return bool(selected and selected.fields)
