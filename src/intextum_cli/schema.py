"""Document classes and their extraction fields, loaded from YAML."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

ChildDtype = Literal["str", "int", "float", "bool", "list", "date", "currency"]
FieldDtype = Literal[
    "str", "int", "float", "bool", "list", "date", "currency", "object_list"
]
REPEATED_DTYPES = frozenset({"list", "object_list"})


class SchemaError(ValueError):
    """Raised when a schema file cannot be loaded or is invalid."""


class Example(BaseModel):
    """One few-shot example: a source excerpt and the value it yields."""

    model_config = ConfigDict(extra="forbid")

    text: str
    value: Any = None
    extraction_text: str | None = None


class ImpliedBy(BaseModel):
    """What in an entry's source row or quotes goes with one enum value."""

    model_config = ConfigDict(extra="forbid")

    marks: list[Literal["underline", "strike", "cross"]] = Field(default_factory=list)
    quote: str | None = None

    @field_validator("quote")
    @classmethod
    def _check_quote(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"invalid quote pattern: {exc}") from exc
        return value

    @model_validator(mode="after")
    def _check_signal(self) -> ImpliedBy:
        if not self.marks and not self.quote:
            raise ValueError("implied_by needs marks or quote")
        return self


class ChildField(BaseModel):
    """One key inside each item of an ``object_list`` field."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    dtype: ChildDtype = "str"
    description: str = ""
    required: bool = False
    enum: list[str] = Field(default_factory=list)
    # Values that mean "no value", e.g. ["0"] where a table writes 0 for "none".
    empty_values: list[str] = Field(default_factory=list)
    # Items must not repeat this value; numbers that identify rows, for example.
    unique: bool = False
    verbatim: bool = False
    quote_for: list[str] = Field(default_factory=list)
    implied_by: dict[str, ImpliedBy] = Field(default_factory=dict)

    @field_validator("implied_by", mode="before")
    @classmethod
    def _bool_keys(cls, value: Any) -> Any:
        # YAML reads an unquoted ``true`` key as a boolean.
        if isinstance(value, dict):
            return {
                str(key).lower() if isinstance(key, bool) else key: signal
                for key, signal in value.items()
            }
        return value

    @model_validator(mode="after")
    def _check_verbatim(self) -> ChildField:
        allowed = {"true", "false"} if self.dtype == "bool" else set(self.enum)
        unknown = set(self.implied_by) - allowed
        if unknown:
            raise ValueError(
                f"{self.name}: implied_by values not allowed {sorted(unknown)}"
            )
        if self.unique and self.dtype not in {"str", "int", "date"}:
            raise ValueError(f"{self.name}: unique is only allowed on str, int or date")
        if self.verbatim and self.dtype != "str":
            raise ValueError(f"{self.name}: verbatim is only allowed on str")
        if self.quote_for and not self.verbatim:
            raise ValueError(f"{self.name}: quote_for requires verbatim")
        return self


class ExternalSource(BaseModel):
    """Where to look when a field's values may live in a separate file."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Classes of files that may hold the values; empty means any other file.
    classes: list[str] = Field(default_factory=list)
    # auto: look outside if the field is empty or the document refers to an
    #       attachment for it; missing: only if empty; always: every time.
    when: Literal["auto", "missing", "always"] = "auto"


class SchemaField(BaseModel):
    """One value to extract."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    dtype: FieldDtype = "str"
    description: str = ""
    required: bool = False
    enum: list[str] = Field(default_factory=list)
    empty_values: list[str] = Field(default_factory=list)
    fields: list[ChildField] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)
    external: ExternalSource | None = None
    source_pages_matching: str | None = None

    @field_validator("source_pages_matching")
    @classmethod
    def _check_page_pattern(cls, value: str | None) -> str | None:
        if value is not None:
            if not value:
                raise ValueError("source_pages_matching must not be empty")
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"invalid source_pages_matching: {exc}") from exc
        return value

    @model_validator(mode="after")
    def _check_shape(self) -> SchemaField:
        if self.dtype == "object_list" and not self.fields:
            raise ValueError(f"{self.name}: object_list needs child 'fields'")
        if self.dtype != "object_list" and self.fields:
            raise ValueError(f"{self.name}: child 'fields' only allowed on object_list")
        if self.enum and self.dtype not in {"str", "list"}:
            raise ValueError(f"{self.name}: enum only allowed on str or list")
        names = {child.name for child in self.fields}
        for child in self.fields:
            unknown = set(child.quote_for) - (names - {child.name})
            if unknown:
                raise ValueError(
                    f"{child.name}: unknown quote_for field {sorted(unknown)}"
                )
            for sibling in self.fields:
                if sibling.name in child.quote_for and sibling.dtype not in {
                    "str",
                    "int",
                    "date",
                }:
                    raise ValueError(
                        f"{child.name}: quote_for field {sibling.name} "
                        "must be str, int or date"
                    )
        return self


class SceneExtraction(BaseModel):
    """One value a scene's passage yields, with the text it comes from."""

    model_config = ConfigDict(extra="forbid")

    field: str
    extraction_text: str = ""
    value: Any = None


class Scene(BaseModel):
    """A shared example passage showing several extractions at once."""

    model_config = ConfigDict(extra="forbid")

    text: str
    extractions: list[SceneExtraction] = Field(default_factory=list)


class DocumentClass(BaseModel):
    """A document class: how to recognise it and which fields to extract."""

    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, str_strip_whitespace=True
    )

    name: str = Field(alias="class", min_length=1)
    description: str = ""
    aliases: list[str] = Field(default_factory=list)
    instructions: str = ""
    fields: list[SchemaField] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_field_names(self) -> DocumentClass:
        seen: set[str] = set()
        for field in self.fields:
            if field.name in seen:
                raise ValueError(f"duplicate field name '{field.name}'")
            seen.add(field.name)
        for scene in self.scenes:
            for extraction in scene.extractions:
                if extraction.field not in seen:
                    raise ValueError(
                        f"scene refers to unknown field '{extraction.field}'"
                    )
        return self


def _class_entries(data: Any) -> list[Any]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "classes" in data:
        return list(data["classes"] or [])
    return [data]


def load_classes(path: Path) -> list[DocumentClass]:
    """Load classes from one YAML file or every ``*.yaml``/``*.yml`` in a folder.

    A file holds a single class mapping, a list of classes, or ``classes: [...]``.
    Classes named in ``external`` must exist in the loaded schemas.
    """
    if path.is_dir():
        files = sorted([*path.glob("*.yaml"), *path.glob("*.yml")])
        if not files:
            raise SchemaError(f"no .yaml files in {path}")
    elif path.is_file():
        files = [path]
    else:
        raise SchemaError(f"schema path not found: {path}")

    classes: list[DocumentClass] = []
    seen: dict[str, Path] = {}
    for file in files:
        try:
            entries = _class_entries(yaml.safe_load(file.read_text(encoding="utf-8")))
        except yaml.YAMLError as exc:
            raise SchemaError(f"{file}: invalid YAML: {exc}") from exc
        for entry in entries:
            try:
                document_class = DocumentClass.model_validate(entry)
            except ValidationError as exc:
                raise SchemaError(f"{file}: {exc}") from exc
            key = document_class.name.casefold()
            if key in seen:
                raise SchemaError(
                    f"{file}: class '{document_class.name}' already defined in "
                    f"{seen[key]}"
                )
            seen[key] = file
            classes.append(document_class)
    for document_class in classes:
        for field in document_class.fields:
            for name in field.external.classes if field.external else []:
                if find_class(classes, name) is None:
                    raise SchemaError(
                        f"{document_class.name}.{field.name}: external class "
                        f"'{name}' is not defined"
                    )
    return classes


def find_class(classes: list[DocumentClass], name: str) -> DocumentClass | None:
    """Look up a class by name or alias, case-insensitively."""
    key = name.strip().casefold()
    for document_class in classes:
        if document_class.name.casefold() == key:
            return document_class
    for document_class in classes:
        if any(alias.casefold() == key for alias in document_class.aliases):
            return document_class
    return None
