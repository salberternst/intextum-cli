"""Consistent filesystem-safe names for results and schema exports."""

import re

_SLUG_RE = re.compile(r"[^\w.-]+")


def slugify(name: str) -> str:
    return _SLUG_RE.sub("_", name).strip("._") or "group"
