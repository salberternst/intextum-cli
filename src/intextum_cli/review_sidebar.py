"""Document search, filtering controls, and source-file list rendering."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path
from typing import Any

from nicegui import ui


class ReviewSidebar:
    def __init__(
        self,
        on_filter: Callable[..., None],
        on_open: Callable[[dict[str, Any]], Awaitable[None]],
        on_reextract: Callable[[], None],
    ):
        self.on_filter = on_filter
        self.on_open = on_open
        self.on_reextract = on_reextract
        self.rendered_rows: list[dict[str, Any]] | None = None
        self.row_buttons: list[tuple[dict[str, Any], ui.element]] = []

    def build(self) -> None:
        with ui.column().classes("sidebar w-full h-full gap-0"):
            with ui.column().classes("sidebar-top w-full gap-2"):
                search = (
                    ui.input(
                        placeholder="Search documents…",
                        on_change=lambda e: self.on_filter(query=e.value or ""),
                    )
                    .props(
                        "outlined dense clearable debounce=180 "
                        "aria-label='Search documents'"
                    )
                    .classes("w-full")
                )
                with search.add_slot("prepend"):
                    ui.icon("search", size="18px")
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    ui.select(
                        {
                            "all": "All documents",
                            "review": "Needs review",
                            "reviewed": "Reviewed",
                            "edited": "Edited",
                            "failed": "Failed",
                        },
                        value="all",
                        on_change=lambda e: self.on_filter(scope=e.value),
                    ).props(
                        "outlined dense options-dense aria-label='Filter documents'"
                    ).classes("grow")
                    self.group_count = ui.label().classes("group-count")
                    with (
                        ui.button(icon="more_vert")
                        .props("flat round dense aria-label='List actions'")
                        .mark("list-menu")
                    ):
                        with ui.menu().props("auto-close"):
                            ui.menu_item(
                                "Re-extract this list…", on_click=self.on_reextract
                            ).mark("reextract-list")
            self.list_box = ui.column().classes("groups-list w-full gap-0")
            with self.list_box:
                with ui.column().classes("empty-state compact") as self.empty_list:
                    ui.icon("search_off", size="28px")
                    ui.label("No matching documents").classes("muted")
                self.rows_box = (
                    ui.column()
                    .classes("document-list w-full gap-0")
                    .props("role=navigation aria-label='Processed documents'")
                )

    def render(
        self, entries: list[dict[str, Any]], slug: str | None, file: str | None
    ) -> None:
        self.group_count.set_text(str(len(entries)))
        self.empty_list.set_visibility(not entries)
        if entries == self.rendered_rows:
            self.highlight_selection(slug, file)
            return
        self.rendered_rows = entries
        self.row_buttons = []
        self.rows_box.clear()
        with self.rows_box:
            for row in entries:
                button = (
                    ui.element("button")
                    .classes("document-row w-full")
                    .props("type=button")
                    .on("click", partial(self.on_open, row))
                )
                button.props["aria-label"] = f"Open {row['file'] or row['label']}"
                self.row_buttons.append((row, button))
                button.props["title"] = row["file"] or row["group"]
                with button:
                    with ui.row().classes("w-full items-center no-wrap gap-2"):
                        ui.label(row["label"]).classes("group-name")
                        dot = ui.element("span").classes("status-dot " + row["status"])
                        dot.props.update(
                            role="img",
                            title=row["status_label"],
                            **{"aria-label": row["status_label"]},
                        )
                    description = row["classification"]
                    if row["file"] and str(Path(row["file"]).parent) != ".":
                        description += " · " + str(Path(row["file"]).parent)
                    if row["file_count"] > 1:
                        description += f" · shared ({row['file_count']})"
                    ui.label(description).classes("group-class")
        self.highlight_selection(slug, file)

    def highlight_selection(self, slug: str | None, file: str | None) -> None:
        for row, button in self.row_buttons:
            if row["slug"] == slug and row["file"] == file:
                button.classes(add="selected")
                button.props["aria-current"] = "page"
            else:
                button.classes(remove="selected")
                button.props.pop("aria-current", None)
