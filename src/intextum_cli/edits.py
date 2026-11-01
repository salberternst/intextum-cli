"""Apply manual corrections to the public result representation.

An edit is recorded separately in SQLite, exposed as ``edits``, and applied to
its field. The history survives reruns; edits from the current class selection
are applied again on top of fresh extraction. When the model returns something else
than it did when the correction was made, the field is flagged for review
instead of hiding the difference.
"""

from __future__ import annotations

from typing import Any

# Review reasons about a field's value; a correction settles them.
_SETTLED_REASONS = (
    "missing_required",
    "no_evidence",
    "invalid",
    "empty",
    "unverified",
)


def correction_applies(result: dict, edit: dict) -> bool:
    name = (result.get("class") or {}).get("name")
    return (
        edit.get("correction_scope", 0) == result.get("classification_revision", 0)
        and edit.get("class_name") == name
    )


def apply_edits(
    result: dict[str, Any], history: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """Apply the newest edit per field to a freshly extracted result."""
    history = [edit for edit in (history or []) if edit.get("field")]
    if not history:
        return result
    result["edits"] = history
    fields = result.get("fields") or {}
    reasons: list[str] = result.get("review_reasons") or []
    newest: dict[str, dict[str, Any]] = {}
    for edit in history:
        if not correction_applies(result, edit):
            continue
        newest[edit["field"]] = edit
    for name, edit in newest.items():
        field = fields.get(name)
        if field is None:
            continue
        extracted = field.get("extracted_value", field.get("value"))
        field["extracted_value"] = extracted
        field["value"] = edit["value"]
        field["edited"] = True
        field.pop("validation_errors", None)
        result.setdefault("data", {})[name] = edit["value"]
        reasons = [
            reason
            for reason in reasons
            if reason.split(":", 1)[0] not in _SETTLED_REASONS
            or reason.split(":", 1)[-1] != name
        ]
        # The correction was made against a different extraction; say so.
        if extracted != edit.get("previous"):
            reason = f"edit_outdated:{name}"
            if reason not in reasons:
                reasons.append(reason)
    result["review_reasons"] = reasons
    result["needs_review"] = result.get("status") not in {
        "completed",
        "duplicate",
    } or bool(reasons)
    return result
