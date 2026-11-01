from types import SimpleNamespace

import pytest

from intextum_cli import llm as llm_module
from intextum_cli.llm import OpenAiJsonLlm, parse_json_object
from intextum_cli.llm_types import LlmError


def chunk(content=None, finish_reason=None, reasoning=None):
    delta = SimpleNamespace(content=content, reasoning=reasoning)
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)]
    )


class FakeCompletions:
    def __init__(self, behaviours):
        self.behaviours = list(behaviours)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        behaviour = self.behaviours.pop(0)
        if isinstance(behaviour, Exception):
            raise behaviour
        return iter(behaviour)


def make_llm(behaviours):
    completions = FakeCompletions(behaviours)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    llm = OpenAiJsonLlm(base_url="x", model="m", max_output_tokens=100, client=client)
    return llm, completions


def test_parse_json_object_tolerates_wrappers():
    assert parse_json_object('<think>hmm</think>\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Here you go: {"a": 1} done') == {"a": 1}
    assert parse_json_object("[1, 2]") is None
    assert parse_json_object("") is None


def test_falls_back_through_response_formats_when_unsupported():
    llm, completions = make_llm(
        [
            RuntimeError("response_format type json_schema is not supported"),
            RuntimeError("'response_format.type' must be 'json_schema' or 'text'"),
            [chunk('{"ok"'), chunk(": true}", "stop")],
            [chunk('{"again": 1}', "stop")],
        ]
    )
    reply = llm.complete_json(system="s", user="u", name="n", schema={"type": "object"})
    assert reply.data == {"ok": True}
    assert completions.requests[0]["response_format"]["type"] == "json_schema"
    assert completions.requests[1]["response_format"] == {"type": "json_object"}
    assert "response_format" not in completions.requests[2]
    llm.complete_json(system="s", user="u", name="n", schema={})
    assert "response_format" not in completions.requests[3]


def test_doubles_token_budget_when_truncated():
    llm, completions = make_llm(
        [
            [chunk('{"a": ', "length")],
            [chunk('{"a": 1', "length")],
            [chunk('{"a": 1}', "stop")],
        ]
    )
    reply = llm.complete_json(system="s", user="u", name="n", schema={})
    assert [r["max_tokens"] for r in completions.requests] == [100, 200, 400]
    assert reply.data == {"a": 1} and reply.finish_reason == "stop"


def test_other_errors_raise_llm_error():
    llm, _ = make_llm([ConnectionError("refused")])
    with pytest.raises(LlmError, match="refused"):
        llm.complete_json(system="s", user="u", name="n", schema={})


def test_thinking_is_switched_off_by_default():
    llm, completions = make_llm([[chunk("{}", "stop")]])
    llm.complete_json(system="s", user="u", name="n", schema={})
    kwargs = completions.requests[0]["extra_body"]["chat_template_kwargs"]
    assert kwargs == {"enable_thinking": False}


def test_drops_thinking_switch_when_server_rejects_it():
    llm, completions = make_llm(
        [
            RuntimeError(
                "Unrecognized request argument supplied: chat_template_kwargs"
            ),
            [chunk("{}", "stop")],
            [chunk("{}", "stop")],
        ]
    )
    llm.complete_json(system="s", user="u", name="n", schema={})
    llm.complete_json(system="s", user="u", name="n", schema={})
    assert "extra_body" in completions.requests[0]
    assert "extra_body" not in completions.requests[1]
    assert "extra_body" not in completions.requests[2]


def test_reports_progress_while_streaming(monkeypatch):
    monkeypatch.setattr(llm_module, "PROGRESS_INTERVAL_S", 0.0)
    llm, _ = make_llm(
        [
            [chunk(reasoning="hm"), chunk('{"a": ', "length")],
            [chunk('{"a": '), chunk("1}", "stop")],
        ]
    )
    seen = []
    llm.on_progress = seen.append
    llm.complete_json(system="s", user="u", name="n", schema={}, label="extract x")
    assert [(p.tokens, p.thinking_tokens, p.max_tokens, p.attempt) for p in seen] == [
        (1, 1, 100, 1),
        (2, 1, 100, 1),
        (1, 0, 200, 2),
        (2, 0, 200, 2),
    ]
    assert seen[0].label == "extract x"


def test_retries_never_ask_for_more_than_the_context_allows():
    usage = SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=700))
    llm, completions = make_llm([[chunk("{", "length"), usage]] * 3)
    llm.context_length = 1_000
    reply = llm.complete_json(system="s", user="u" * 500, name="n", schema={})
    # Room after the counted prompt: 1,000 - 700 - 64 template tokens = 236.
    assert [r["max_tokens"] for r in completions.requests] == [100, 200, 236]
    assert reply.finish_reason == "length"


def test_first_request_fits_an_estimated_long_prompt():
    llm, completions = make_llm([[chunk("{}", "stop")]])
    llm.context_length = 1_000
    llm.max_output_tokens = 900
    llm.complete_json(system="", user="u" * 1_500, name="n", schema={})
    # 1,500 chars / 2.5 = 600 tokens estimated; 1,000 - 600 - 64 = 336.
    assert completions.requests[0]["max_tokens"] == 336


def test_ollama_gets_reasoning_effort_none_unless_thinking():
    llm, completions = make_llm([[chunk("{}", "stop")], [chunk("{}", "stop")]])
    llm.ollama = True
    llm.complete_json(system="s", user="u", name="n", schema={})
    assert completions.requests[0]["reasoning_effort"] == "none"
    llm.thinking = True
    llm.complete_json(system="s", user="u", name="n", schema={})
    assert "reasoning_effort" not in completions.requests[1]


def test_other_servers_get_no_reasoning_effort():
    llm, completions = make_llm([[chunk("{}", "stop")]])
    assert llm.ollama is False
    llm.complete_json(system="s", user="u", name="n", schema={})
    assert "reasoning_effort" not in completions.requests[0]
