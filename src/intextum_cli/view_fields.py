"""Field cards, evidence passages, and correction dialogs for review."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

from nicegui import run, ui

from .review import (
    display_value,
    field_spec,
    items_without_evidence,
    mark_missing_evidence,
)
from .schema import REPEATED_DTYPES
from .store import StorageError
from .view import Library
from .view_document import DocumentPane
from .view_editors import table_data, value_editor

ISSUE_LABELS = {"unverified": "the verifier doubts this value"}


class FieldPanel:
    def __init__(
        self,
        library: Library,
        document: DocumentPane,
        on_saved: Callable[[str, dict], None],
    ):
        self.library = library
        self.document = document
        self.on_saved = on_saved
        self.client = ui.context.client
        self.slug: str | None = None
        self.result: dict | None = None

    def build(self) -> None:
        with ui.column().classes("fields-pane w-full h-full gap-0"):
            with ui.row().classes("fields-toolbar w-full items-center no-wrap gap-2"):
                ui.label("Extracted fields").classes("panel-title")
                self.count = ui.label().classes("count-badge")
            with ui.column().classes("fields-scroll w-full gap-2"):
                # Review status for the result; filled by ReviewActions.
                self.status_box = ui.column().classes("w-full gap-2")
                self.box = ui.column().classes("w-full gap-2")
            self.footer = ui.row().classes("fields-footer w-full items-center no-wrap")

    def show(self, slug: str | None, result: dict | None) -> None:
        self.slug, self.result = slug, result
        self.render()

    def render(self) -> None:
        self.box.clear()
        fields = (self.result or {}).get("fields") or {}
        self.count.set_text(str(len(fields)))
        with self.box:
            if not fields:
                with ui.column().classes("empty-state"):
                    ui.icon("data_object", size="40px")
                    ui.label("No extracted fields").classes("empty-title")
                    ui.label(
                        "This document may be unclassified or classification-only."
                    ).classes("muted text-center")
                return
            schemas = self.library.schema_fields(self.result or {})
            for name, entry in fields.items():
                self.field_card(name, entry, schemas.get(name))

    def field_card(self, name, entry, schema):
        spec = field_spec(name, entry, schema)
        issues = [
            r.split(":", 1)[0]
            for r in self.result.get("review_reasons", [])
            if r.partition(":")[2] == name
        ]
        with ui.card().classes("field-card w-full gap-2").props("flat bordered"):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                with ui.row().classes("gap-2 items-baseline min-w-0"):
                    ui.label(name.replace("_", " ")).classes("field-title")
                    tags = spec.dtype + (" · required" if spec.required else "")
                    ui.label(tags).classes("type-tag")
                    if entry.get("edited"):
                        ui.label("Edited").classes("edited-tag")
                    verification = entry.get("verification")
                    if verification and not entry.get("edited"):
                        probability = verification["probability"]
                        doubtful = f"unverified:{name}" in (
                            self.result.get("review_reasons") or []
                        )
                        ui.label(
                            f"{'Doubtful' if doubtful else 'Verified'} "
                            f"{probability:.0%}"
                        ).classes(
                            "verify-tag " + ("doubtful" if doubtful else "verified")
                        ).tooltip(
                            f"{verification['model']}: probability that the document "
                            "supports this value in this role"
                        )
                edit_button = (
                    ui.button(
                        "Edit table" if spec.dtype in REPEATED_DTYPES else "Edit",
                        icon="edit",
                        on_click=partial(self.edit_dialog, name, entry, spec),
                    )
                    .props("flat dense no-caps")
                    .classes("edit-button")
                )
                edit_button.set_enabled(not self.result["review"]["pending_extraction"])
            if spec.description:
                ui.label(spec.description).classes("field-description")
            value = entry.get("value")
            missing = items_without_evidence(entry)
            if spec.dtype in REPEATED_DTYPES and isinstance(value, list) and value:
                rows, columns = table_data(value, spec)
                if missing:
                    mark_missing_evidence(rows, columns, missing)
                ui.table(
                    rows=rows, columns=columns, row_key="__intextum_row", pagination=5
                ).props("flat dense wrap-cells").classes("w-full result-table")
            else:
                ui.label(display_value(value)).classes(
                    "field-value " + ("empty-value" if value is None else "")
                )
            for issue in list(
                dict.fromkeys(issues + (entry.get("validation_errors") or []))
            ):
                label = ISSUE_LABELS.get(issue, issue.replace("_", " "))
                if issue == "no_evidence" and missing:
                    label = f"no evidence for {len(missing)} of {len(value)} item(s)"
                ui.label(label).classes("field-issue")
            if entry.get("edited"):
                ui.label(
                    "Model extracted: " + display_value(entry.get("extracted_value"))
                ).classes("model-value")
            if entry.get("source"):
                ui.label(
                    "Source: " + ", ".join(entry["source"].get("files") or [])
                ).classes("text-xs muted")
            evidence = list(entry.get("evidence") or [])
            for items in entry.get("item_evidence") or []:
                evidence.extend(items)
            evidence = list(
                {
                    (e.get("file"), e.get("page"), e.get("snippet")): e
                    for e in evidence
                }.values()
            )
            if evidence:
                with ui.expansion(
                    f"{len(evidence)} evidence passage(s)", icon="format_quote"
                ).classes("evidence-list w-full"):
                    for item in evidence:
                        # A path has no passage in the document to reveal.
                        if item.get("kind") == "path":
                            with ui.column().classes("gap-1 w-full"):
                                ui.label(item.get("file") or "Source").classes(
                                    "evidence-location"
                                )
                                ui.label(
                                    f"From file path: {item.get('snippet') or ''}"
                                ).classes("evidence-quote")
                            continue
                        with (
                            ui.button(on_click=partial(self.document.reveal, item))
                            .props("flat no-caps align=left")
                            .classes("evidence-button w-full")
                        ):
                            with ui.column().classes("gap-1 w-full"):
                                location = Path(item.get("file") or "Source").name
                                if item.get("page"):
                                    location += f" · page {item['page']}"
                                ui.label(location).classes("evidence-location")
                                ui.label(item.get("snippet") or "").classes(
                                    "evidence-quote"
                                )
            history = [
                e for e in self.result.get("edits") or [] if e.get("field") == name
            ]
            if history:
                with ui.expansion(
                    f"{len(history)} correction(s)", icon="history"
                ).classes("history-list w-full"):
                    for edit in reversed(history):
                        ui.label(display_value(edit.get("value"))).classes("text-sm")
                        ui.label(
                            f"{edit.get('at', '')} · {edit.get('note') or 'No note'}"
                        ).classes("text-xs muted")

    def edit_dialog(self, name, entry, spec):
        slug = self.slug
        revision = self.result["review"]["revision"]
        with (
            ui.dialog().props("persistent") as dialog,
            ui.card().classes("editor-dialog gap-4"),
        ):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Edit " + name.replace("_", " ")).classes("dialog-title")
                ui.button(icon="close", on_click=dialog.close).props(
                    "flat round dense aria-label='Cancel edit'"
                )
            if spec.description:
                ui.label(spec.description).classes("muted")
            read = value_editor(entry.get("value"), spec)
            note = (
                ui.input(
                    "Correction note", placeholder="What did you verify? (optional)"
                )
                .props("outlined")
                .classes("w-full")
            )
            error = ui.label().classes("field-issue")

            async def save():
                try:
                    value = read()
                    save_button.props("loading")
                    updated = await run.io_bound(
                        self.library.edit, slug, name, value, note.value, revision
                    )
                except (ValueError, OSError, KeyError, StorageError) as exc:
                    error.set_text(str(exc))
                    return
                finally:
                    save_button.props(remove="loading")
                dialog.close()
                # Rebuilding fields also deletes this dialog's originating card.
                # Keep subsequent updates in the surviving page context.
                with self.client:
                    self.on_saved(slug, updated)
                    ui.notify(
                        "Correction saved", type="positive", position="bottom-right"
                    )

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                save_button = ui.button(
                    "Save correction", icon="check", on_click=save
                ).props("no-caps")
        dialog.open()
