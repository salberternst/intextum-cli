"""Validate schema files."""

from __future__ import annotations

import argparse

from ..schema import SchemaError, load_classes
from . import CommandError


def cmd_check_schemas(args: argparse.Namespace) -> int:
    try:
        classes = load_classes(args.schemas)
    except SchemaError as exc:
        raise CommandError(str(exc)) from exc
    for document_class in classes:
        extras = []
        if document_class.instructions:
            extras.append("instructions")
        if document_class.scenes:
            extras.append(f"{len(document_class.scenes)} scene(s)")
        suffix = f", {', '.join(extras)}" if extras else ""
        print(f"{document_class.name}: {len(document_class.fields)} field(s){suffix}")
        for field in document_class.fields:
            flags = " required" if field.required else ""
            print(f"  - {field.name} ({field.dtype}){flags}")
    return 0
