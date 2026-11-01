from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from intextum_cli.llm import parse_json_object
from intextum_cli.llm_types import JsonReply


class FakeLlm:
    """Replies with a handler's JSON and records every prompt it was sent."""

    model = "fake-model"

    def __init__(self, handler: Callable[[str, str, dict[str, Any]], Any]):
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, *, system, user, name, schema, label=""):
        self.calls.append(
            {
                "system": system,
                "user": user,
                "name": name,
                "schema": schema,
                "label": label,
            }
        )
        reply = self.handler(name, user, schema)
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return JsonReply(
            data=parse_json_object(content), content=content, finish_reason="stop"
        )


@pytest.fixture
def fake_llm():
    return FakeLlm
