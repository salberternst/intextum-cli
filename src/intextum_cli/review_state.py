"""Project human decisions without discarding processing warnings or audit history."""

from __future__ import annotations

import hashlib
import json


class ReviewConflict(ValueError):
    """The result changed while a reviewer or extraction was working on it."""


CLASS_ACTIONS = {"class", "automatic", "no_match"}


def class_choice(events: list[dict]) -> dict:
    return next(
        (event for event in reversed(events) if event["action"] in CLASS_ACTIONS),
        {"id": 0, "action": "automatic"},
    )


def apply_review(result: dict, events: list[dict]) -> dict:
    choice = class_choice(events)
    token = hashlib.sha256(
        json.dumps([result, choice["id"]], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    decision = next(
        (
            event
            for event in reversed(events)
            if event["action"] in {"approve", "reopen", "no_match"}
        ),
        {},
    )
    pending = choice["id"] != result.get("classification_revision", 0)
    if choice["action"] == "no_match":
        result.update(
            **{"class": {"name": None, "source": "viewer"}},
            status="unclassified" if result.get("status") != "failed" else "failed",
            fields={},
            data={},
        )
        pending = False
    reviewed = (
        decision.get("action") in {"approve", "no_match"}
        and decision.get("content_revision") == token
        and not pending
        and result.get("status") != "failed"
    )
    result["review"] = {
        "state": "reviewed" if reviewed else "open",
        "revision": hashlib.sha256(
            f"{token}:{events[-1]['id'] if events else 0}".encode()
        ).hexdigest(),
        "content_revision": token,
        "class_override": choice.get("class_name"),
        "classification_action": choice["action"],
        "classification_revision": choice["id"],
        "pending_extraction": pending,
        "at": decision.get("at") if reviewed else None,
        "note": decision.get("note", "") if reviewed else "",
        "history": events,
    }
    result["needs_review"] = (
        False if reviewed else bool(result.get("needs_review") or pending or events)
    )
    return result
