"""Cached Docling content, source text, and evidence navigation.

Originals open in their native application; the viewer shows the recognized
content, which is what extraction evidence refers to.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from nicegui import run, ui

from .review import source_html
from .view import Library, open_in_system

MODES = {"content": "Content", "elements": "Elements", "images": "Pages"}


class DocumentPane:
    def __init__(self, library: Library):
        self.library = library
        self.client = ui.context.client
        self.group = ""
        self.file: str | None = None
        self.files: list[str] = []
        self.data: dict[str, Any] = {}
        self.state: dict[str, Any] = {}
        self.page = 0
        self.snippet = ""
        self.revision = 0
        self.frame = None
        self.refs: list[str] = []
        self.mode = "content"

    def build(self):
        with ui.column().classes("document-pane w-full h-full gap-0"):
            with ui.row().classes("document-toolbar w-full items-center no-wrap"):
                self.picker = (
                    ui.select(
                        [],
                        on_change=lambda e: self.select_file(e.value),
                    )
                    .props(
                        "dense borderless options-dense "
                        "aria-label='Document in this result'"
                    )
                    .classes("document-picker min-w-0")
                )
                with (
                    ui.tabs()
                    .props("dense no-caps inline-label")
                    .classes("document-tabs") as self.tabs
                ):
                    ui.tab("Document", icon="article")
                    ui.tab("Source text", icon="subject")
                self.tabs.on_value_change(lambda _: self.update_modes())
                # Display modes of the embedded viewer, controlled from here.
                self.mode_toggle = (
                    ui.toggle(MODES, value=self.mode, on_change=self.set_mode)
                    .props("dense no-caps unelevated toggle-color=primary")
                    .classes("mode-toggle")
                )
                ui.space()
                self.open_button = (
                    ui.button(icon="open_in_new", on_click=self.open_system)
                    .props("flat round dense aria-label='Open in default app'")
                    .tooltip("Open the original in its default application")
                )
                self.download_button = (
                    ui.button(icon="download", on_click=self.download)
                    .props("flat round dense aria-label='Download original'")
                    .tooltip("Download original")
                )
            with (
                ui.tab_panels(self.tabs, value="Document")
                .props("keep-alive")
                .classes("document-panels w-full grow")
            ):
                with ui.tab_panel("Document").classes("p-0 h-full"):
                    self.document = ui.column().classes("w-full h-full gap-0")
                with ui.tab_panel("Source text").classes("p-0 h-full"):
                    self.text = ui.column().classes("w-full h-full gap-0")

    async def show(
        self, files: list[str], *, selected_file: str | None = None, group: str = ""
    ):
        self.group = group
        self.files = files
        self.file = None
        self.picker.options = {name: name for name in files}
        self.picker.update()
        # The header already names a single document.
        self.picker.set_visibility(len(files) > 1)
        if files:
            preferred = (
                selected_file
                if selected_file in files
                else next(
                    (
                        name
                        for name in files
                        if Path(name).suffix.lower()
                        in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
                    ),
                    files[0],
                )
            )
            await self.select_file(preferred)
        else:
            self.revision += 1
            self.state = {}
            self.update_modes()
            self.document.clear()
            self.text.clear()

    async def select_file(self, name: str | None):
        if not name or name == self.file:
            return
        self.file = name
        original_available = self.library.file(name) is not None
        self.download_button.set_enabled(original_available)
        self.open_button.set_enabled(original_available)
        self.page, self.snippet, self.refs = 0, "", []
        self.picker.set_value(name)
        self.revision += 1
        revision = self.revision
        self.tabs.set_value("Document")
        self.document.clear()
        self.text.clear()
        with self.document:
            with ui.row().classes("empty-state"):
                ui.spinner(size="24px")
                ui.label("Loading cached document…")

        group = self.group

        def read():
            return self.library.text(name, group), self.library.document_status(
                name, self.group
            )

        try:
            data, state = await run.io_bound(read)
        except Exception as exc:
            data, state = {"error": str(exc)}, {"status": "error", "error": str(exc)}
        if revision != self.revision:
            return
        self.data, self.state = data, state
        self.render_document()
        self.render_text()

    async def build_view(self):
        name, revision = self.file, self.revision
        if not name:
            return
        self.document.clear()
        with self.document:
            with ui.column().classes("empty-state"):
                ui.spinner(size="30px")
                ui.label("Building document view…")
                ui.label("Recognition models may need to load on first use.").classes(
                    "muted"
                )
        state = await run.io_bound(self.library.build_document, name, self.group)
        data = await run.io_bound(self.library.text, name, self.group)
        if revision != self.revision:
            return
        with self.client:
            self.state = state
            self.data = data
            self.render_document()
            self.render_text()

    def render_document(self):
        self._render_document()
        self.update_modes()

    def _render_document(self):
        self.document.clear()
        self.frame = None
        with self.document:
            if self.state.get("status") == "ready":
                for note in self.state.get("notes", []):
                    ui.label(note).classes("source-note")
                self.frame = (
                    ui.element("iframe")
                    .props(f'src="{self.frame_url()}" title="Document content"')
                    .classes("document-frame")
                )
                if self.state.get("needs_rebuild") and self.state.get("can_build"):
                    with ui.row().classes(
                        "document-view-footer w-full items-center justify-end"
                    ):
                        ui.button(
                            "Rebuild document view",
                            icon="refresh",
                            on_click=self.build_view,
                        ).props("flat dense no-caps size=sm")
                return
            if self.state.get("error"):
                ui.label(self.state["error"]).classes("source-note")
            with ui.row().classes("document-build-banner w-full items-center"):
                ui.label("Structured document view is not cached yet.").classes("grow")
                ui.button(
                    "Build document view",
                    icon="auto_fix_high",
                    on_click=self.build_view,
                ).props("no-caps size=sm").set_enabled(
                    self.state.get("can_build", False)
                )
            if not self.state.get("can_build"):
                ui.label(
                    "The original is unavailable. "
                    "Use --input to locate it for rebuilding."
                ).classes("source-note")
            if self.data.get("cached"):
                ui.label(
                    "Showing cached source text until the document view is built."
                ).classes("source-note")
                self.source_body()
            else:
                with ui.column().classes("empty-state"):
                    ui.icon("article", size="48px")
                    ui.label(
                        "Build this view to inspect the recognized content."
                    ).classes("muted text-center")

    def update_modes(self):
        ready = self.state.get("status") == "ready"
        options = dict(MODES)
        if not self.state.get("image_pages"):
            options.pop("images")
        if self.mode not in options:
            self.mode = "content"
        self.mode_toggle.set_options(options, value=self.mode)
        self.mode_toggle.set_visibility(ready and self.tabs.value == "Document")

    async def set_mode(self, event):
        if not event.value or event.value == self.mode:
            return
        self.mode = event.value
        if self.frame is not None:
            message = json.dumps({"intextumMode": self.mode})
            await ui.run_javascript(
                f"document.getElementById('c{self.frame.id}')?.contentWindow"
                f"?.postMessage({message}, location.origin)"
            )

    def frame_url(self):
        query = urlencode(
            {
                "file": self.file,
                "group": self.group,
                "key": self.state["key"],
                "mode": self.mode,
                "embedded": "1",
            }
        )
        fragment = quote(json.dumps(self.refs), safe="")
        return f"/document-viewer?{query}#{fragment}"

    def source_body(self):
        pages = self.data.get("pages") or [""]
        self.page = min(self.page, len(pages) - 1)
        with ui.row().classes("text-toolbar w-full items-center"):
            ui.label("SOURCE TEXT").classes("eyebrow grow")
            ui.select(
                {i: f"Page {i + 1} of {len(pages)}" for i in range(len(pages))},
                value=self.page,
                on_change=lambda e: self.change_page(e.value),
            ).props("dense outlined options-dense").classes("w-40")
        with ui.scroll_area().classes("w-full grow source-scroll"):
            ui.html(source_html(pages, self.page, self.snippet)).classes("w-full")

    def render_text(self):
        self.text.clear()
        with self.text:
            if self.data.get("error"):
                ui.label(self.data["error"]).classes("source-note")
            elif not self.data.get("cached"):
                with ui.column().classes("empty-state"):
                    ui.label("Extracted text is not cached yet.").classes("empty-title")
            else:
                for note in self.data.get("notes", []):
                    ui.label(note).classes("source-note")
                self.source_body()

    def change_page(self, page: int):
        self.page = page
        self.render_text()
        if self.state.get("status") != "ready":
            self.render_document()

    async def reveal(self, evidence: dict[str, Any]):
        name = evidence.get("file")
        if name and name != self.file:
            if name not in self.files:
                self.files.append(name)
                self.picker.options = {file: file for file in self.files}
                self.picker.update()
                self.picker.set_visibility(True)
            await self.select_file(name)
        pages = self.data.get("pages") or []
        self.snippet = evidence.get("snippet") or ""
        needle = self.snippet.strip().split("\n", 1)[0]
        page = evidence.get("page")
        if page and 0 < page <= len(pages):
            self.page = page - 1
        elif needle:
            self.page = next((i for i, text in enumerate(pages) if needle in text), 0)
        if self.state.get("status") == "ready":
            name, revision = self.file, self.revision
            refs, warning = await run.io_bound(
                self.library.document_evidence, name, evidence, self.group
            )
            if revision != self.revision:
                return
            if refs:
                self.refs = refs
                self.tabs.set_value("Document")
                self.frame.props(f'src="{self.frame_url()}"')
                return
            with self.client:
                ui.notify(warning, type="warning")
        self.tabs.set_value("Source text")
        self.render_text()
        if pages and needle and needle in pages[self.page]:
            await ui.run_javascript(
                "document.querySelector('.q-tab-panel:not(.q-tab-panel--inactive) "
                "#evidence-match')?.scrollIntoView("
                "{block: 'center', behavior: 'smooth'});"
            )

    def download(self):
        if self.file and self.library.file(self.file):
            ui.download(f"/api/raw?download=1&file={quote(self.file, safe='')}")

    async def open_system(self):
        path = self.library.file(self.file) if self.file else None
        if path is not None:
            await run.io_bound(open_in_system, path)
