"""Experiment: can a decision model flag wrong extractions that rules miss?

For every corpus group, one decision request asks per extracted field whether
the document supports that value in that role (a yes/no "noul" question) and
which class the document belongs to (a "choice" question). The
answers are compared with ``expected.yaml``: a useful verifier gives wrong
values a low probability and correct ones a high probability.

intextum extract corpus/inbox -s corpus/schemas -o /tmp/corpus-results.sqlite
python corpus/decision_check.py /tmp/corpus-results.sqlite \\
    --model typesafe/jev-1.13 --out /tmp/decisions.json

Decision servers: OpenRouter (/api/alpha/decisions) and Ollama >= 0.35 or the
llama.cpp server (/v1/systemone) share one request shape:

python corpus/decision_check.py WS --base-url http://127.0.0.1:11434 --model tev1:0.8b

Chat servers without a decision endpoint (LM Studio, vLLM, older Ollama) get
the same questions as one-token chat completions; --backend chat reads p(yes)
from token logprobs, or falls back to the yes/no text when none are returned:

python corpus/decision_check.py WS --backend chat \\
    --base-url http://127.0.0.1:1234/v1 --model qwen2.5-1.5b-instruct

Without --base-url, the endpoint and API key come from corpus/inbox's .env. The
Decisions API is in alpha; this script is an experiment, not part of the CLI.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml
from score import EXPECTED, matches

from intextum_cli.config import load_llm_settings
from intextum_cli.view import Library

INBOX = Path(__file__).parent / "inbox"
NONE_CLASS = "none_of_these"
THRESHOLDS = (0.3, 0.5, 0.7, 0.9)


def decisions_url(base_url: str) -> str:
    """OpenRouter's alpha path, or the local /v1/systemone of Ollama and llama.cpp."""
    parts = urllib.parse.urlsplit(base_url)
    root = f"{parts.scheme}://{parts.netloc}"
    if "openrouter.ai" in parts.netloc:
        return f"{root}/api/alpha/decisions"
    return f"{root}/v1/systemone"


class EndpointError(Exception):
    """A server rejected a request; callers may try another endpoint."""


def post(url: str, api_key: str | None, body: dict, retries: int = 3) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=headers
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                reply = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            if exc.code in {429, 500, 502, 503, 524, 529} and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise EndpointError(f"HTTP {exc.code} from {url}: {detail}") from None
        # LM Studio answers unknown routes with HTTP 200 and an error body.
        if isinstance(reply, dict) and isinstance(reply.get("error"), str):
            raise EndpointError(f"{url}: {reply['error']}")
        return reply
    raise AssertionError("unreachable")


def yes_probability(candidates: list[dict]) -> float | None:
    """p(yes) from one token's top logprobs, over yes/no spellings only."""
    mass = {"yes": 0.0, "no": 0.0}
    for top in candidates:
        word = (top.get("token") or "").strip().lower()
        if word in mass:
            mass[word] += math.exp(top["logprob"])
    total = sum(mass.values())
    return mass["yes"] / total if total else None


class ChatDecider:
    """Decision questions for chat-only servers (LM Studio, vLLM, older Ollama).

    Prefers the Responses API (LM Studio returns logprobs there), then chat
    completions with logprobs, then the bare yes/no text.
    """

    def __init__(self, base_url: str, api_key: str | None, model: str):
        base = base_url.rstrip("/")
        base = base if base.endswith("/v1") else base + "/v1"
        self.api_key, self.model = api_key, model
        self.endpoints = [base + "/responses", base + "/chat/completions"]

    def ask(self, prompt: str, system: str, max_tokens: int) -> tuple[str, list]:
        while self.endpoints:
            url = self.endpoints[0]
            try:
                if url.endswith("/responses"):
                    reply = post(url, self.api_key, {
                        "model": self.model,
                        "instructions": system,
                        "input": prompt,
                        "temperature": 0,
                        "max_output_tokens": max_tokens,
                        "top_logprobs": 10,
                        "include": ["message.output_text.logprobs"],
                        "store": False,
                    })  # fmt: skip
                    content = next(
                        (c for item in reply.get("output") or []
                         if item.get("type") == "message"
                         for c in item.get("content") or []),
                        {},
                    )  # fmt: skip
                    tokens = content.get("logprobs") or []
                    return content.get("text") or "", tokens
                reply = post(url, self.api_key, {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": max_tokens,
                    "logprobs": True,
                    "top_logprobs": 10,
                })  # fmt: skip
                choice = (reply.get("choices") or [{}])[0]
                tokens = (choice.get("logprobs") or {}).get("content") or []
                return (choice.get("message") or {}).get("content") or "", tokens
            except EndpointError as exc:
                print(f"  {exc}; trying the next endpoint", file=sys.stderr)
                self.endpoints.pop(0)
        raise SystemExit("no chat endpoint answered")

    def decide(self, state: dict, questions: dict) -> dict:
        answers = {}
        for key, question in questions.items():
            criteria = question["criteria"]
            if question["type"] == "noul":
                options = f"yes: {criteria['true']}\nno: {criteria['false']}"
                rule = "Answer with one word: yes or no."
            else:
                options = "\n".join(f"{n}: {text}" for n, text in criteria.items())
                rule = "Answer with exactly one option name from the list."
            prompt = (
                f"Document:\n{state['document']}\n\n"
                f"Question: {question['instructions']}\n{options}\n\n{rule}"
            )
            noul = question["type"] == "noul"
            text, tokens = self.ask(
                prompt, "You check documents. " + rule, 3 if noul else 20
            )
            text = text.strip().lower()
            if not noul:
                picked = next((n for n in criteria if text.startswith(n.lower())), None)
                answers[key] = {"type": "choice", "choice": picked, "source": "text"}
                continue
            # Skip leading whitespace tokens to reach the answer word.
            first = next((t for t in tokens if (t.get("token") or "").strip()), {})
            p = yes_probability(first.get("top_logprobs") or [])
            if p is not None:
                answers[key] = {"type": "noul", "noul": p, "source": "logprobs"}
            else:
                p = (
                    1.0
                    if text.startswith("yes")
                    else 0.0
                    if text.startswith("no")
                    else None
                )
                answers[key] = {"type": "noul", "noul": p, "source": "text"}
        return {"answers": answers}


def document_text(library: Library, slug: str, result: dict, limit: int) -> str:
    """The cached text extraction saw, for the group's files and field sources."""
    files = list(result.get("files") or [])
    for entry in (result.get("fields") or {}).values():
        for name in ((entry or {}).get("source") or {}).get("files") or []:
            if name not in files:
                files.append(name)
    parts = []
    for name in files:
        pages = library.text(name, slug).get("pages") or []
        parts.append(f"=== {name} ===\n" + "\n".join(pages))
    text = "\n\n".join(parts)
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"


def field_question(name: str, value: Any, description: str) -> dict:
    shown = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    role = f"{name.replace('_', ' ')}" + (f" ({description})" if description else "")
    return {
        "type": "noul",
        "instructions": (
            f"An extraction system read this document and reported the {role} as: "
            f"{shown}. Is that correct according to the document?"
        ),
        "criteria": {
            "true": "The document states exactly this value for this field, "
            "in this role.",
            "false": "The value is wrong, incomplete, absent from the document, "
            "or belongs to a different field or party.",
        },
    }


def class_question(classes: list) -> dict:
    criteria = {
        cls.name: cls.description or f"A {cls.name} document." for cls in classes
    }
    criteria[NONE_CLASS] = "The document fits none of the other categories."
    return {
        "type": "choice",
        "instructions": "Which category does this document belong to?",
        "criteria": criteria,
    }


def swapped(name: str, value: Any, data: dict) -> tuple[str, Any] | None:
    """A value from another field of the same document: right text, wrong role."""
    for other, candidate in data.items():
        if other != name and candidate != value and type(candidate) is type(value):
            if isinstance(value, str) and (
                bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
                != bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate))
            ):
                continue  # A date for a name is too easy.
            if isinstance(value, list):
                continue
            return f"same document's {other}", candidate
    return None


def corrupt(value: Any, peers: list[Any]) -> tuple[str, Any] | None:
    """A plausible wrong variant of a correct value, labelled with its kind."""
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        day = datetime.date.fromisoformat(value) + datetime.timedelta(days=3)
        return "shifted date", day.isoformat()
    if isinstance(value, dict) and isinstance(value.get("amount"), int | float):
        return "amount +10%", {**value, "amount": round(value["amount"] * 1.1, 2)}
    if isinstance(value, list) and len(value) > 1:
        return "list item dropped", value[:-1]
    if isinstance(value, str):
        other = next((p for p in peers if isinstance(p, str) and p != value), None)
        if other is not None:
            return "other document's value", other
        if re.search(r"\d", value):
            digits = [i for i, c in enumerate(value) if c.isdigit()]
            i = digits[-1]
            return "changed digit", value[:i] + str((int(value[i]) + 1) % 10) + value[
                i + 1 :
            ]
    return None


def run(args: argparse.Namespace) -> dict:
    expected_groups = yaml.safe_load(EXPECTED.read_text(encoding="utf-8"))
    library = Library(args.workspace)
    snapshot = {
        r["group"]: (slug, r, s) for slug, r, s in library.store.results.snapshot()
    }
    settings = load_llm_settings(INBOX)
    base_url = args.base_url or settings.base_url
    # Only send the configured key to the configured endpoint.
    api_key = settings.api_key if base_url == settings.base_url else None
    url = decisions_url(base_url)
    chat = {m: ChatDecider(base_url, api_key, m) for m in args.model}
    # Values per (class, field) across groups, for "wrong party" corruptions.
    peers: dict[tuple[str, str], list[Any]] = {}
    for _, result, _ in snapshot.values():
        name = (result.get("class") or {}).get("name")
        for field, value in (result.get("data") or {}).items():
            peers.setdefault((name, field), []).append(value)

    rows: list[dict] = []
    classes_seen: list[dict] = []
    cost = 0.0
    for group, expected in expected_groups.items():
        if group not in snapshot:
            print(f"- {group}: no result, skipped")
            continue
        slug, result, schemas = snapshot[group]
        actual_class = (result.get("class") or {}).get("name")
        descriptions = {
            f.name: f.description
            for cls in schemas
            if cls.name == actual_class
            for f in cls.fields
        }
        questions: dict[str, dict] = {"document_class": class_question(schemas)}
        checked = []
        for name, want in (expected.get("data") or {}).items():
            got = (result.get("data") or {}).get(name)
            if got in (None, "", []):
                # Rules already flag missing values; nothing to verify.
                rows.append({"group": group, "field": name, "skipped": "missing"})
                continue
            questions[f"field_{name}"] = field_question(
                name, got, descriptions.get(name, "")
            )
            checked.append((f"field_{name}", name, got, matches(want, got), None))
            if args.corrupt and matches(want, got):
                variants = (
                    ("fake", corrupt(got, peers.get((actual_class, name), []))),
                    ("swap", swapped(name, got, result.get("data") or {})),
                )
                for prefix, wrong in variants:
                    if wrong and not matches(want, wrong[1]):
                        key = f"{prefix}_{name}"
                        questions[key] = field_question(
                            name, wrong[1], descriptions.get(name, "")
                        )
                        checked.append((key, name, wrong[1], False, wrong[0]))
        state = {"document": document_text(library, slug, result, args.max_chars)}
        for model in args.model:
            if args.backend == "chat":
                reply = chat[model].decide(state, questions)
            else:
                try:
                    reply = post(url, api_key, {
                        "model": model,
                        "state": state,
                        "questions": questions,
                    })  # fmt: skip
                except EndpointError as exc:
                    raise SystemExit(str(exc)) from None
            cost += (reply.get("usage") or {}).get("cost") or 0.0
            answers = reply.get("answers") or {}
            choice = answers.get("document_class") or {}
            picked = choice.get("choice")
            picked = None if picked == NONE_CLASS else picked
            classes_seen.append({
                "model": model,
                "group": group,
                "expected": expected.get("class"),
                "extracted": actual_class,
                "decision": picked,
                "confidence": choice.get("confidence"),
                "probabilities": choice.get("probabilities"),
            })  # fmt: skip
            for key, name, got, correct, fake in checked:
                answer = answers.get(key) or {}
                rows.append({
                    "model": model,
                    "group": group,
                    "field": name,
                    "value": got,
                    "correct": correct,
                    "corruption": fake,
                    # A stored verification's own flags are not rule flags.
                    "flagged_by_rules": any(
                        reason.endswith(f":{name}")
                        and not reason.startswith("unverified:")
                        for reason in result.get("review_reasons") or []
                    ),
                    "p_yes": answer.get("noul"),
                    "source": answer.get("source", "decision"),
                })  # fmt: skip
        print(f"✓ {group}: {len(checked)} value(s) checked", file=sys.stderr)
    return {"fields": rows, "classes": classes_seen, "cost": cost}


def report(data: dict, models: list[str]) -> None:
    for model in models:
        fields = [r for r in data["fields"] if r.get("model") == model]
        valid = [r for r in fields if r["p_yes"] is not None]
        wrong = [r for r in valid if not r["correct"]]
        right = [r for r in valid if r["correct"]]
        print(f"\n## {model}")
        fakes = sum(bool(r["corruption"]) for r in valid)
        print(
            f"values checked: {len(valid)}; wrong: {len(wrong)} "
            f"({len(wrong) - fakes} from extraction, {fakes} injected)"
        )
        if len(valid) < len(fields):
            print(f"no answer for {len(fields) - len(valid)} field(s)")
        sources: dict[str, int] = {}
        for r in valid:
            sources[r.get("source", "decision")] = (
                sources.get(r.get("source", "decision"), 0) + 1
            )
        print(
            "probability source: " + ", ".join(f"{k} {v}" for k, v in sources.items())
        )
        for r in sorted(valid, key=lambda r: r["p_yes"]):
            mark = "ok   " if r["correct"] else "FAKE " if r["corruption"] else "WRONG"
            rules = " (rules flagged)" if r["flagged_by_rules"] else ""
            if r["corruption"]:
                rules += f" [{r['corruption']}]"
            value = json.dumps(r["value"], ensure_ascii=False)
            if len(value) > 60:
                value = value[:57] + "..."
            print(
                f"  {r['p_yes']:.2f} {mark} {r['group']}.{r['field']} = {value}{rules}"
            )
        print("\n  flag if p_yes < t   caught wrong   false alarms (of correct)")
        for t in THRESHOLDS:
            caught = sum(r["p_yes"] < t for r in wrong)
            alarms = sum(r["p_yes"] < t for r in right)
            print(f"  t = {t:.1f}            {caught}/{len(wrong)}"
                  f"            {alarms}/{len(right)}")  # fmt: skip
        kinds: dict[str, list[float]] = {}
        for r in wrong:
            kind = r["corruption"] or "extraction error"
            kind = (
                "same document's other field" if kind.startswith("same doc") else kind
            )
            kinds.setdefault(kind, []).append(r["p_yes"])
        print("\n  wrong values by kind      count   max p_yes")
        for kind, values in sorted(kinds.items()):
            print(f"  {kind:<26}{len(values):>5}   {max(values):.2f}")
        classes = [c for c in data["classes"] if c["model"] == model]
        agree = sum(c["decision"] == c["expected"] for c in classes)
        print(f"\n  class decisions matching expected.yaml: {agree}/{len(classes)}")
        print("  probability of the expected class (none_of_these for null):")
        for c in sorted(
            classes,
            key=lambda c: (c["probabilities"] or {}).get(
                c["expected"] or NONE_CLASS, 0
            ),
        ):
            p = (c["probabilities"] or {}).get(c["expected"] or NONE_CLASS)
            shown = f"{p:.2f}" if isinstance(p, int | float) else " n/a"
            mark = (
                "" if c["extracted"] == c["expected"] else "  ← extraction class wrong"
            )
            print(f"    {shown} {c['group']}: {c['expected'] or 'no class'}{mark}")
        for c in classes:
            if c["decision"] != c["expected"] or c["extracted"] != c["expected"]:
                print(f"    {c['group']}: expected {c['expected']}, "
                      f"extraction {c['extracted']}, decision {c['decision']} "
                      f"(confidence {c['confidence']})")  # fmt: skip
    print(f"\ntotal cost: ${data['cost']:.4f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("workspace", type=Path, help="SQLite workspace of the corpus")
    parser.add_argument(
        "--model",
        action="append",
        help="decision model slug; repeat to compare (default typesafe/jev-1.13)",
    )
    parser.add_argument(
        "--backend",
        choices=["decisions", "chat"],
        default="decisions",
        help="decision endpoint, or one-token chat completions with logprobs",
    )
    parser.add_argument(
        "--base-url",
        help="decision server, e.g. http://127.0.0.1:11434 (default: corpus .env)",
    )
    parser.add_argument("--max-chars", type=int, default=20000)
    parser.add_argument(
        "--no-corrupt",
        dest="corrupt",
        action="store_false",
        help="skip injected wrong values (by default each correct value gets one)",
    )
    parser.add_argument("--out", type=Path, help="write raw rows as JSON")
    args = parser.parse_args()
    args.model = args.model or ["typesafe/jev-1.13"]
    data = run(args)
    if args.out:
        args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    report(data, args.model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
