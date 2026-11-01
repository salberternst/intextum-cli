"""A per-browser NiceGUI workspace for reviewing an extraction run."""

from __future__ import annotations

from nicegui import run, ui

from .review import document_rows
from .review_actions import ReviewActions
from .review_batch import BatchExtraction
from .review_header import render_header
from .review_sidebar import ReviewSidebar
from .view import Library
from .view_document import DocumentPane
from .view_fields import FieldPanel


class ReviewWorkspace:
    def __init__(self, library: Library):
        self.client = ui.context.client
        self.library = library
        self.entries = []
        self.slug = None
        self.result = None
        self.query = ""
        self.scope = "all"
        self.file = None
        self.selection_revision = 0
        self.document = DocumentPane(library)
        self.fields = FieldPanel(library, self.document, self.correction_saved)
        self.actions = ReviewActions(library, self.refresh, self.reviewed)
        self.batch = BatchExtraction(
            library, self.actions, self.render_heading, self.refresh
        )
        self.sidebar = ReviewSidebar(
            self.filter,
            self.open_document,
            lambda: self.batch.show(self.visible(), self.entries),
        )

    async def build(self):
        ui.add_head_html('<link rel="stylesheet" href="/review.css">')
        ui.colors(primary="#147d76", secondary="#334155", accent="#147d76")
        with ui.column().classes("review-app w-full gap-0"):
            with ui.row().classes("app-header w-full items-center no-wrap gap-3"):
                with ui.element("div").classes("brand-icon"):
                    ui.icon("layers", size="18px")
                ui.label("intextum").classes("brand-name")
                ui.label("Document review").classes("brand-subtitle")
                ui.label(self.library.name).classes("collection-name")
                ui.space()
                self.stats = ui.row().classes("collection-stats items-center gap-4")
                ui.button(icon="refresh", on_click=self.refresh).props(
                    "flat round dense aria-label='Refresh'"
                ).tooltip("Reload results from the database")
            with ui.splitter(value=20, limits=(14, 32)).classes(
                "app-layout w-full grow"
            ) as layout:
                with layout.before:
                    self.sidebar.build()
                with layout.after:
                    with ui.column().classes("workspace w-full h-full gap-0"):
                        self.heading = ui.row().classes(
                            "group-heading w-full items-center no-wrap gap-3"
                        )
                        with ui.splitter(value=58, limits=(30, 75)).classes(
                            "review-split w-full grow"
                        ) as panels:
                            with panels.before:
                                self.document.build()
                                self.document.picker.on_value_change(self.file_changed)
                            with panels.after:
                                self.fields.build()
        ui.keyboard(on_key=self.key_event, repeating=False)
        await self.refresh()

    def filter(self, *, query=None, scope=None):
        if query is not None:
            self.query = query
        if scope is not None:
            self.scope = scope
        self.render_list()
        self.render_heading()

    def visible(self):
        return document_rows(self.entries, self.query, self.scope)

    def render_stats(self):
        self.stats.clear()
        rows = document_rows(self.entries)
        with self.stats:
            ui.label(f"{len(rows)} documents").classes("stat")
            # Results, not files: a shared result is one review decision.
            pending = len({row["slug"] for row in rows if row["needs_review"]})
            if pending:
                ui.button(f"{pending} to review →", on_click=self.next_review).props(
                    "flat dense no-caps"
                ).classes("stat warning").tooltip(
                    "Open the next document that needs review"
                )
            else:
                ui.label("All reviewed").classes("stat")

    def render_list(self):
        self.sidebar.render(self.visible(), self.slug, self.file)

    async def open_document(self, row):
        if row["slug"] == self.slug:
            self.selection_revision += 1
            if row["file"]:
                await self.document.select_file(row["file"])
            return
        await self.open_group(row["slug"], selected_file=row["file"])

    def file_changed(self, event):
        if not event.value:
            return
        self.file = event.value
        self.render_list()
        self.render_heading()

    async def refresh(self):
        self.entries = await run.io_bound(self.library.index)
        self.render_stats()
        self.render_list()
        if self.entries:
            slug = (
                self.slug
                if any(e["slug"] == self.slug for e in self.entries)
                else next(
                    (
                        e["slug"]
                        for e in self.entries
                        if e["needs_review"] and e["class"]
                    ),
                    self.entries[0]["slug"],
                )
            )
            await self.open_group(
                slug, selected_file=self.document.file if self.slug == slug else None
            )
        else:
            self.slug, self.result, self.file = None, None, None
            self.render_heading()
            self.fields.show(self.slug, self.result)
            await self.document.show([])

    async def open_group(self, slug, *, selected_file=None):
        self.selection_revision += 1
        revision = self.selection_revision
        result = await run.io_bound(self.library.result, slug)
        if revision != self.selection_revision:
            return
        if result is None:
            ui.notify(
                "This result no longer exists. Refresh to reload the list.",
                type="warning",
            )
            return
        self.slug, self.result = slug, result
        self.file = selected_file
        self.render_list()
        self.render_heading()
        self.fields.show(self.slug, self.result)
        files = list(result.get("files") or [])
        for entry in (result.get("fields") or {}).values():
            for file in (entry.get("source") or {}).get("files") or []:
                if file not in files:
                    files.append(file)
        await self.document.show(files, selected_file=selected_file, group=self.slug)

    def render_heading(self) -> None:
        self.heading.clear()
        with self.heading:
            render_header(
                self.result,
                self.slug,
                self.file,
                self.visible(),
                self.move,
                self.actions.menu,
            )
        self.actions.render(self.fields, self.slug, self.result)

    async def move(self, delta):
        rows = self.visible()
        position = next(
            (
                i
                for i, e in enumerate(rows)
                if e["slug"] == self.slug and e["file"] == self.file
            ),
            -1,
        )
        target = position + delta
        if 0 <= target < len(rows):
            await self.open_document(rows[target])

    async def key_event(self, event):
        if event.action.keydown and event.modifiers.alt:
            if event.key.arrow_down:
                await self.move(1)
            elif event.key.arrow_up:
                await self.move(-1)
            elif event.key.enter and self.actions.approve:
                await self.actions.approve()

    def next_to_review(self, rows, slug, file):
        """The next row after the given one whose result still needs review.

        Rows are taken from the list as the reviewer saw it, so a "needs review"
        filter that hides the just-reviewed row keeps its place in the queue.
        """
        position = next(
            (i for i, r in enumerate(rows) if r["slug"] == slug and r["file"] == file),
            -1,
        )
        pending = {e["slug"] for e in self.entries if e["needs_review"]}
        ordered = rows[position + 1 :] + rows[: position + 1]
        return next(
            (r for r in ordered if r["slug"] in pending and r["slug"] != slug), None
        )

    async def next_review(self):
        target = self.next_to_review(self.visible(), self.slug, self.file)
        if target is None:
            ui.notify("No other document in this list needs review.")
            return
        await self.open_document(target)

    async def reviewed(self, slug):
        rows, file = self.visible(), self.file
        self.entries = await run.io_bound(self.library.index)
        self.render_stats()
        target = self.next_to_review(rows, slug, file)
        if target is None:
            await self.refresh()
            ui.notify("Review complete: nothing left to review in this list.")
            return
        ui.notify("Marked reviewed", position="bottom-right")
        await self.open_group(target["slug"], selected_file=target["file"])

    def correction_saved(self, slug: str, result: dict) -> None:
        if self.slug != slug:
            return
        self.result = result
        for entry in self.entries:
            if entry["slug"] == slug:
                entry.update(
                    needs_review=result["needs_review"],
                    edited=True,
                    review_reasons=result["review_reasons"],
                    reviewed=result["review"]["state"] == "reviewed",
                )
        self.render_stats()
        self.render_list()
        self.render_heading()
        self.fields.show(self.slug, self.result)
