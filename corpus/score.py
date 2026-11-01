"""Score a workspace or exported JSON folder against ``corpus/expected.yaml``.

intextum extract corpus/inbox -s corpus/schemas -o /tmp/corpus-results.sqlite \
    --force --detect-marks
python corpus/score.py /tmp/corpus-results.sqlite
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from intextum_cli.convert import has_libreoffice

EXPECTED = Path(__file__).parent / "expected.yaml"


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    return value


def matches(expected: Any, actual: Any) -> bool:
    """Compare only what ``expected`` specifies; lists must have the same length."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            matches(value, actual.get(key)) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(expected) == len(actual)
            and all(matches(e, a) for e, a in zip(expected, actual, strict=True))
        )
    if isinstance(expected, int | float) and not isinstance(expected, bool):
        return (
            isinstance(actual, int | float)
            and not isinstance(actual, bool)
            and abs(expected - actual) <= 0.01
        )
    if expected is None:
        return actual in (None, [], "")
    return _norm(expected) == _norm(actual)


def score(results_dir: Path) -> tuple[int, int, list[str]]:
    expected_groups = yaml.safe_load(EXPECTED.read_text(encoding="utf-8"))
    results = {}
    if results_dir.is_file():
        from intextum_cli.store import WorkspaceStore

        results = {
            result["group"]: result
            for _, result, _ in WorkspaceStore(results_dir).results.snapshot()
        }
    else:
        for path in results_dir.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "group" in data:
                results[data["group"]] = data

    passed = total = 0
    lines: list[str] = []
    libreoffice = has_libreoffice()
    for group, expected in expected_groups.items():
        if expected.get("requires") == "libreoffice" and not libreoffice:
            lines.append(f"- {group}: skipped (LibreOffice not installed)")
            continue
        result = results.get(group)
        if result is None:
            lines.append(f"✗ {group}: no result")
            total += 1 + len(expected.get("data") or {})
            continue
        checks: list[tuple[str, bool, Any, Any]] = []
        actual_class = (result.get("class") or {}).get("name")
        checks.append(("class", matches(expected["class"], actual_class),
                       expected["class"], actual_class))  # fmt: skip
        fields = [
            (field, value, (result.get("data") or {}).get(field))
            for field, value in (expected.get("data") or {}).items()
        ]
        if "needs_review" in expected:
            review = result.get("needs_review")
            # A wrong value should be flagged even where a correct result
            # would not need review.
            wanted = expected["needs_review"] or any(
                not matches(value, actual) for _, value, actual in fields
            )
            checks.append(("needs_review", wanted == review, wanted, review))
        for field, value, actual in fields:
            checks.append((field, matches(value, actual), value, actual))

        ok = sum(1 for _, good, _, _ in checks if good)
        passed += ok
        total += len(checks)
        mark = "✓" if ok == len(checks) else "✗"
        lines.append(f"{mark} {group}: {ok}/{len(checks)}")
        for name, good, want, got in checks:
            if not good:
                lines.append(
                    f"    {name}: expected {json.dumps(want, ensure_ascii=False)}, "
                    f"got {json.dumps(got, ensure_ascii=False)}"
                )
        if result.get("review_reasons"):
            lines.append(f"    review: {', '.join(result['review_reasons'])}")
    return passed, total, lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "results", type=Path, help="SQLite workspace or exported JSON folder"
    )
    args = parser.parse_args()
    passed, total, lines = score(args.results)
    print("\n".join(lines))
    print(f"\nscore: {passed}/{total} checks ({passed / total:.0%})")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
