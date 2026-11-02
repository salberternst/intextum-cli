"""Check extracted values with a decision model and flag doubtful fields.

Verification is a separate phase after extraction, so the extraction model and
the decision model never need memory at the same time: each loads once per run.
For every completed result, one decision request asks per extracted field
whether the document supports that value in that role. Records are stored apart
from the extraction payload and bound to its ``extraction_id``; a new extraction
makes them stale, and changed verifier settings re-run only verification.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .decisions import Decider, DecisionError, decisions_url, yes_probability

if TYPE_CHECKING:
    from .schema import DocumentClass
    from .store import WorkspaceStore

DEFAULT_THRESHOLD = 0.3
DEFAULT_MAX_CHARS = 60_000
REASON = "unverified"
CLASS_REASON = "class_doubtful"
# Choice option for "no class fits"; its probability is the confidence that an
# unclassified result is right.
NONE_OPTION = "none_of_these"
# Modules that shape verification answers; their code is part of the record key.
VERIFIER_MODULES = ("decisions", "verification")


@dataclass(frozen=True)
class VerifierSettings:
    model: str
    base_url: str
    api_key: str | None = field(default=None, repr=False)
    threshold: float = DEFAULT_THRESHOLD
    max_chars: int = DEFAULT_MAX_CHARS

    @property
    def key(self) -> str:
        """Identity of everything that changes answers, excluding the API key."""
        parts = [
            self.model,
            decisions_url(self.base_url),
            self.threshold,
            self.max_chars,
            _code_digest(),
        ]
        return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


# A decision client and the settings it was built from.
Verifier = tuple[Decider, VerifierSettings]


def build_verifier(settings: VerifierSettings) -> Verifier:
    from .decisions import DecisionClient

    client = DecisionClient(settings.base_url, settings.model, settings.api_key)
    return client, settings


@cache
def _code_digest() -> str:
    digest = hashlib.sha256()
    for name in VERIFIER_MODULES:
        digest.update((Path(__file__).parent / f"{name}.py").read_bytes())
    return digest.hexdigest()


def _shown(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def field_question(name: str, value: Any, description: str = "") -> dict:
    role = name.replace("_", " ") + (f" ({description})" if description else "")
    return {
        "type": "noul",
        "instructions": (
            f"An extraction system read this document and reported the {role} as: "
            f"{_shown(value)}. Is that correct according to the document?"
        ),
        "criteria": {
            "true": "The document states exactly this value for this field, "
            "in this role.",
            "false": "The value is wrong, incomplete, absent from the document, "
            "or belongs to a different field or party.",
        },
    }


def extracted_values(result: dict) -> dict[str, Any]:
    """The model's values, before corrections, that are worth checking.

    Values read from a file path are skipped: the document need not state them.
    """
    values = {}
    for name, entry in (result.get("fields") or {}).items():
        if not isinstance(entry, dict):
            continue
        if any(item.get("kind") == "path" for item in entry.get("evidence") or []):
            continue
        value = entry.get("extracted_value", entry.get("value"))
        if value not in (None, "", [], {}):
            values[name] = value
    return values


def class_checked(result: dict) -> bool:
    """Automatic classifications are checked; viewer and config choices are not."""
    return (result.get("class") or {}).get("source") == "llm"


def needs_verification(result: dict) -> bool:
    if not result.get("extraction_id"):
        return False
    if result.get("status") == "unclassified":
        return class_checked(result)
    return result.get("status") == "completed" and (
        class_checked(result)
        or (result.get("mode") != "classify" and bool(extracted_values(result)))
    )


def class_question(classes: list[DocumentClass]) -> dict:
    criteria = {}
    for document_class in classes:
        text = document_class.description or f"A {document_class.name} document."
        if document_class.aliases:
            text += f" Also called: {', '.join(document_class.aliases)}."
        criteria[document_class.name] = text
    criteria[NONE_OPTION] = "The document fits none of the other categories."
    return {
        "type": "choice",
        "instructions": "Which category does this document belong to?",
        "criteria": criteria,
    }


def document_text(store: WorkspaceStore, group: str, result: dict, limit: int) -> str:
    """The cached text extraction saw, for the result's files and field sources."""
    files = list(result.get("files") or [])
    for entry in (result.get("fields") or {}).values():
        for name in ((entry or {}).get("source") or {}).get("files") or []:
            if name not in files:
                files.append(name)
    keys = {
        source["path"]: source["conversion_key"]
        for source in store.results.sources(group)
    }
    parts = []
    for name in files:
        record = store.cache.conversion(keys[name]) if keys.get(name) else None
        if record is not None:
            parts.append(f"=== {name} ===\n" + "\n".join(record.pages))
    text = "\n\n".join(parts)
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"


def verify_result(
    store: WorkspaceStore,
    group: str,
    result: dict,
    decider: Decider,
    settings: VerifierSettings,
    classes: list[DocumentClass],
) -> dict:
    """One decision request for the class and all extracted fields of a result."""
    class_name = (result.get("class") or {}).get("name")
    descriptions = {
        f.name: f.description for c in classes if c.name == class_name for f in c.fields
    }
    values = extracted_values(result) if result.get("mode") != "classify" else {}
    names = list(values)
    questions = {
        f"field_{index}": field_question(name, values[name], descriptions.get(name, ""))
        for index, name in enumerate(names)
    }
    if class_checked(result) and classes:
        questions["document_class"] = class_question(classes)
    record: dict[str, Any] = {
        "key": settings.key,
        "extraction_id": result.get("extraction_id"),
        "model": settings.model,
        "threshold": settings.threshold,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "fields": {},
        "class": None,
        "error": None,
    }
    text = document_text(store, group, result, settings.max_chars)
    if not text.strip():
        record["error"] = "no cached document text to verify against"
        return record
    try:
        answers = decider.decide(text, questions)
    except DecisionError as exc:
        record["error"] = str(exc)
        return record
    for index, name in enumerate(names):
        record["fields"][name] = yes_probability(answers.get(f"field_{index}") or {})
    probabilities = (answers.get("document_class") or {}).get("probabilities")
    if isinstance(probabilities, dict) and probabilities:
        record["class"] = {
            "probabilities": {
                str(option): float(value)
                for option, value in probabilities.items()
                if isinstance(value, int | float) and not isinstance(value, bool)
            }
        }
    return record


def class_assessment(result: dict, record: dict) -> dict | None:
    """How likely the current class (or "no class") is, and the best alternative."""
    probabilities = (record.get("class") or {}).get("probabilities") or {}
    if not probabilities:
        return None
    current = (result.get("class") or {}).get("name") or NONE_OPTION
    best = max(probabilities, key=probabilities.get)
    return {
        "probability": probabilities.get(current, 0.0),
        "suggestion": None if best == NONE_OPTION else best,
        "suggestion_probability": probabilities[best],
        "unclassified": current == NONE_OPTION,
        "probabilities": probabilities,
        "model": record["model"],
    }


def apply_verification(result: dict, record: dict | None) -> dict:
    """Attach probabilities and flag fields below the threshold.

    Records from an earlier extraction are ignored; the result then simply has
    no verification until the verifier runs again.
    """
    if not record or record.get("extraction_id") != result.get("extraction_id"):
        return result
    fields = result.get("fields") or {}
    reasons = list(result.get("review_reasons") or [])
    for name, probability in (record.get("fields") or {}).items():
        entry = fields.get(name)
        if not isinstance(entry, dict) or probability is None:
            continue
        entry["verification"] = {"probability": probability, "model": record["model"]}
        reason = f"{REASON}:{name}"
        if probability < record["threshold"] and reason not in reasons:
            reasons.append(reason)
    assessment = class_assessment(result, record)
    if assessment is not None:
        result["class_check"] = assessment
        if (
            assessment["probability"] < record["threshold"]
            and CLASS_REASON not in reasons
        ):
            reasons.append(CLASS_REASON)
    if record.get("error"):
        result["warnings"] = [
            *(result.get("warnings") or []),
            f"verification failed: {record['error']}",
        ]
    result["verification"] = {
        "model": record["model"],
        "threshold": record["threshold"],
        "at": record["at"],
        "error": record.get("error"),
    }
    result["review_reasons"] = reasons
    result["needs_review"] = result.get("status") not in {
        "completed",
        "duplicate",
    } or bool(reasons)
    return result


def verify_workspace(
    store: WorkspaceStore,
    decider: Decider,
    settings: VerifierSettings,
    *,
    groups: set[str] | None = None,
    force: bool = False,
    report: Callable[[str], None] = print,
) -> int:
    """Verify results whose record is missing or stale; returns how many ran."""
    pending = store.results.verification_candidates(settings.key, groups, force)
    for index, group in enumerate(pending, start=1):
        result = store.results.get(group, by_group=True)
        if result is None or not needs_verification(result):
            continue
        record = verify_result(
            store, group, result, decider, settings, store.results.classes(group)
        )
        updated = store.results.save_verification(group, record)
        reasons = (updated or {}).get("review_reasons") or []
        flagged = [
            reason.split(":", 1)[1]
            for reason in reasons
            if reason.startswith(f"{REASON}:")
        ]
        check = (updated or {}).get("class_check")
        if record["error"]:
            text = f"verification failed: {record['error']}"
        else:
            parts = []
            if CLASS_REASON in reasons and check:
                suggestion = check["suggestion"] or "no class"
                parts.append(
                    f"class doubtful ({suggestion} "
                    f"{check['suggestion_probability']:.0%})"
                )
            elif check:
                label = "no class fits" if check["unclassified"] else "class"
                parts.append(f"{label} {check['probability']:.0%}")
            parts.append(
                f"doubtful: {', '.join(flagged)}"
                if flagged
                else f"{len(record['fields'])} field(s) verified"
            )
            text = " · ".join(parts)
        report(f"[verify {index}/{len(pending)}] {group}: {text}")
    return len(pending)
