import io
from types import SimpleNamespace

from intextum_cli.llm import OpenAiJsonLlm
from intextum_cli.llm_types import CallProgress, CallStats
from intextum_cli.stats import (
    CallPrinter,
    context_warning,
    format_call,
    format_progress,
)


def stats(**overrides):
    values = dict(
        label="extract contract.doc [line_items]",
        prompt_chars=14_000,
        output_chars=3_500,
        prompt_tokens=4_000,
        completion_tokens=1_000,
        reasoning_tokens=None,
        first_token_s=20.0,
        total_s=120.0,
        finish_reason="stop",
        max_tokens=4_096,
        context_length=16_384,
        response_format="json_schema",
    )
    values.update(overrides)
    return CallStats(**values)


def test_format_call_with_usage():
    line = format_call(stats())
    assert line == (
        "    llm extract contract.doc [line_items] · in 4,000 tok · out 1,000 tok · "
        "first token 20.0s · total 2m00s · 10.0 tok/s · context 5,000/16,384 (31%)"
    )


def test_format_call_estimates_and_warnings():
    line = format_call(
        stats(prompt_tokens=None, completion_tokens=None, context_length=6_000,
              finish_reason="length", response_format="json_object")
    )  # fmt: skip
    assert "in ~4,000 tok" in line and "out ~1,000 tok" in line
    assert "(~ = estimated, server sent no usage)" in line
    assert "⚠ input + max output (4,096) exceeds the context window" in line
    assert "⚠ reply cut off at max output tokens" in line
    assert "format json_object" in line


def test_printer_quiet_still_sums_up():
    out = io.StringIO()
    printer = CallPrinter(stream=out, quiet=True)
    printer(stats())
    printer(
        stats(
            prompt_tokens=2_000, completion_tokens=500, total_s=60.0, first_token_s=10.0
        )
    )
    assert out.getvalue() == ""
    assert printer.summary() == (
        "llm: 2 call(s) · in 6,000 tok · out 1,500 tok · 3m00s · 10.0 tok/s · "
        "largest request 5,000 tok of 16,384"
    )
    assert CallPrinter(stream=out).summary() is None


def test_context_warning():
    assert context_warning(None, 60_000, 4_096) is None
    assert context_warning(32_768, 60_000, 4_096) is None
    warning = context_warning(8_192, 60_000, 4_096)
    assert "~17,143 tokens" in warning and "context of 8,192 tokens" in warning


def chunk(content=None, finish_reason=None, usage=None):
    choices = [] if content is None and finish_reason is None else [
        SimpleNamespace(delta=SimpleNamespace(content=content, model_extra={}), finish_reason=finish_reason)
    ]  # fmt: skip
    return SimpleNamespace(choices=choices, usage=usage)


class Completions:
    def __init__(self, behaviours):
        self.behaviours, self.requests = list(behaviours), []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        behaviour = self.behaviours.pop(0)
        if isinstance(behaviour, Exception):
            raise behaviour
        return iter(behaviour)


def make_llm(behaviours, calls):
    completions = Completions(behaviours)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    llm = OpenAiJsonLlm(base_url="x", model="m", client=client, context_length=8192,
                        on_call=calls.append)  # fmt: skip
    return llm, completions


def test_client_reports_usage_and_label():
    calls = []
    usage = SimpleNamespace(prompt_tokens=120, completion_tokens=7,
                            completion_tokens_details=SimpleNamespace(reasoning_tokens=3))  # fmt: skip
    llm, completions = make_llm(
        [[chunk('{"a": 1}', "stop"), chunk(usage=usage)]], calls
    )
    reply = llm.complete_json(
        system="s", user="u" * 100, name="n", schema={}, label="classify a.pdf"
    )
    assert reply.data == {"a": 1}
    assert completions.requests[0]["stream_options"] == {"include_usage": True}
    [call] = calls
    assert (call.label, call.prompt_tokens, call.completion_tokens, call.reasoning_tokens) == (
        "classify a.pdf", 120, 7, 3
    )  # fmt: skip
    assert call.prompt_chars == 101 and call.context_length == 8192
    assert call.first_token_s is not None and not call.estimated


def test_client_drops_stream_options_when_rejected():
    calls = []
    llm, completions = make_llm(
        [RuntimeError("unknown field: stream_options"), [chunk('{"a": 1}', "stop")]],
        calls,
    )
    llm.complete_json(system="s", user="u", name="n", schema={})
    assert "stream_options" not in completions.requests[1]
    assert calls[0].estimated


def test_first_token_counts_thinking_in_either_field(monkeypatch):
    import intextum_cli.llm as llm_module

    clock = iter([0.0, 2.0, 10.0])  # request sent, thinking starts, reply done
    monkeypatch.setattr(llm_module.time, "monotonic", lambda: next(clock))
    thinking = SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=None, model_extra={"reasoning": "hm"}),
                finish_reason=None,
            )
        ],
        usage=None,
    )
    calls = []
    llm, _ = make_llm([[thinking, chunk('{"a": 1}', "stop")]], calls)
    llm.complete_json(system="s", user="u", name="n", schema={})
    assert calls[0].first_token_s == 2.0 and calls[0].total_s == 10.0


def progress(**overrides):
    values = dict(
        label="extract contract.doc [line_items]",
        tokens=1_234,
        thinking_tokens=0,
        elapsed_s=45.0,
        max_tokens=8_192,
        attempt=1,
    )
    values.update(overrides)
    return CallProgress(**values)  # fmt: skip


def test_format_progress():
    assert format_progress(progress()) == (
        "    … ~1,234/8,192 tok · 45.0s · extract contract.doc [line_items]"
    )
    line = format_progress(progress(thinking_tokens=900, attempt=2), width=100)
    assert line.startswith(
        "    … ~1,234/8,192 tok (thinking ~900) · 45.0s · "
        "attempt 2, earlier reply was cut off · "
    )
    assert len(line) == 99 and line.endswith("…")


class Terminal(io.StringIO):
    def isatty(self):
        return True


def test_printer_rewrites_progress_line_on_terminal():
    out = Terminal()
    printer = CallPrinter(stream=out)
    printer.progress(progress(tokens=10))
    printer.progress(progress(tokens=20))
    printer(stats())
    text = out.getvalue()
    assert text.count("\r\033[K") == 3 and "~20/8,192 tok" in text
    assert text.endswith(format_call(stats()) + "\n")


def test_printer_logs_progress_sparsely_without_terminal():
    out = io.StringIO()
    printer = CallPrinter(stream=out)
    for elapsed in (5.0, 31.0, 32.0, 61.0):
        printer.progress(progress(elapsed_s=elapsed))
    printer.progress(progress(elapsed_s=33.0, attempt=2))
    lines = out.getvalue().splitlines()
    assert lines == [
        format_progress(progress(elapsed_s=31.0)),
        format_progress(progress(elapsed_s=61.0)),
        format_progress(progress(elapsed_s=33.0, attempt=2)),
    ]
    quiet = CallPrinter(stream=out, quiet=True)
    quiet.progress(progress(elapsed_s=60.0))
    assert len(out.getvalue().splitlines()) == 3
