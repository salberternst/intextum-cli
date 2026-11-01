"""Console output about model calls: tokens, speed and context use."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from typing import TextIO

from .llm_types import CHARS_PER_TOKEN, CallProgress, CallStats

# Warn when a request uses more than this share of the context window.
CONTEXT_WARNING_SHARE = 0.9
# Without a terminal (log file, pipe) progress is a new line this often.
PROGRESS_LOG_INTERVAL_S = 30.0


def _tokens(value: int, estimated: bool) -> str:
    return f"{'~' if estimated else ''}{value:,}"


def _duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(round(seconds), 60)
    return f"{minutes}m{rest:02d}s"


def format_call(stats: CallStats) -> str:
    """One line per model call, e.g. for ``extract contract.pdf [line_items]``."""
    estimated = stats.estimated
    parts = [
        f"in {_tokens(stats.input_tokens, stats.prompt_tokens is None)} tok",
        f"out {_tokens(stats.output_tokens, stats.completion_tokens is None)} tok",
    ]
    if stats.reasoning_tokens:
        parts.append(f"thinking {stats.reasoning_tokens:,} tok")
    if stats.first_token_s is not None:
        parts.append(f"first token {_duration(stats.first_token_s)}")
    parts.append(f"total {_duration(stats.total_s)}")
    if stats.tokens_per_second is not None:
        parts.append(f"{stats.tokens_per_second:.1f} tok/s")

    warnings = []
    if stats.context_length:
        used = stats.input_tokens + stats.output_tokens
        parts.append(
            f"context {used:,}/{stats.context_length:,} "
            f"({used / stats.context_length:.0%})"
        )
        if stats.input_tokens + stats.max_tokens > stats.context_length:
            warnings.append(
                f"input + max output ({stats.max_tokens:,}) exceeds the context window"
            )
        elif used > stats.context_length * CONTEXT_WARNING_SHARE:
            warnings.append("context nearly full")
    if stats.finish_reason == "length":
        warnings.append("reply cut off at max output tokens")
    if stats.response_format and stats.response_format != "json_schema":
        parts.append(f"format {stats.response_format}")

    line = f"    llm {stats.label or 'call'} · " + " · ".join(parts)
    if estimated:
        line += " (~ = estimated, server sent no usage)"
    for warning in warnings:
        line += f"\n    ⚠ {warning}"
    return line


def format_progress(progress: CallProgress, width: int | None = None) -> str:
    """Running line for a reply still streaming; the label is cut to fit width."""
    tokens = f"~{progress.tokens:,}/{progress.max_tokens:,} tok"
    if progress.thinking_tokens:
        tokens += f" (thinking ~{progress.thinking_tokens:,})"
    parts = [tokens, _duration(progress.elapsed_s)]
    if progress.attempt > 1:
        parts.append(f"attempt {progress.attempt}, earlier reply was cut off")
    prefix = "    … " + " · ".join(parts) + " · "
    label = progress.label or "call"
    if width is not None and len(prefix) + len(label) > width - 1:
        label = label[: max(width - 2 - len(prefix), 0)] + "…"
    return prefix + label


@dataclass
class CallPrinter:
    """Prints each call (unless quiet) and keeps totals for the end of the run.

    While a reply streams, a terminal gets one progress line that is rewritten
    in place; other streams get a line each 30 seconds a reply keeps streaming.
    """

    stream: TextIO = sys.stderr
    quiet: bool = False
    calls: list[CallStats] = field(default_factory=list)
    _live_line: bool = field(default=False, repr=False)
    _last_logged: tuple[str, int, int] | None = field(default=None, repr=False)

    def __call__(self, stats: CallStats) -> None:
        self.calls.append(stats)
        if not self.quiet:
            self.clear()
            print(format_call(stats), file=self.stream, flush=True)

    def progress(self, progress: CallProgress) -> None:
        if self.quiet:
            return
        if self._is_terminal():
            width = shutil.get_terminal_size().columns
            line = format_progress(progress, width)
            self.stream.write(f"\r\033[K{line}")
            self.stream.flush()
            self._live_line = True
            return
        step = int(progress.elapsed_s // PROGRESS_LOG_INTERVAL_S)
        key = (progress.label, progress.attempt, step)
        if step and key != self._last_logged:
            self._last_logged = key
            print(format_progress(progress), file=self.stream, flush=True)

    def clear(self) -> None:
        """Remove the live progress line before other output is printed."""
        if self._live_line:
            self.stream.write("\r\033[K")
            self.stream.flush()
            self._live_line = False

    def _is_terminal(self) -> bool:
        isatty = getattr(self.stream, "isatty", None)
        return bool(isatty and isatty())

    def summary(self) -> str | None:
        if not self.calls:
            return None
        input_tokens = sum(c.input_tokens for c in self.calls)
        output_tokens = sum(c.output_tokens for c in self.calls)
        total = sum(c.total_s for c in self.calls)
        generating = sum(c.total_s - (c.first_token_s or 0.0) for c in self.calls)
        largest = max(c.input_tokens + c.output_tokens for c in self.calls)
        estimated = any(c.estimated for c in self.calls)
        line = (
            f"llm: {len(self.calls)} call(s) · in {input_tokens:,} tok · "
            f"out {output_tokens:,} tok · {_duration(total)}"
        )
        if generating > 0.05:
            line += f" · {output_tokens / generating:.1f} tok/s"
        line += f" · largest request {largest:,} tok"
        context = next((c.context_length for c in self.calls if c.context_length), None)
        if context:
            line += f" of {context:,}"
        if estimated:
            line += " (partly estimated)"
        return line


def context_warning(
    context_length: int | None, max_chars: int, max_output_tokens: int
) -> str | None:
    """Warn up front when --max-chars cannot fit the model's context window."""
    if not context_length:
        return None
    source_tokens = round(max_chars / CHARS_PER_TOKEN)
    if source_tokens + max_output_tokens <= context_length:
        return None
    return (
        f"⚠ --max-chars {max_chars:,} (~{source_tokens:,} tokens) plus "
        f"--max-output-tokens {max_output_tokens:,} can exceed the model's context of "
        f"{context_length:,} tokens. Large documents may be cut off or return "
        "nothing: load the model with a larger context or lower --max-chars."
    )
