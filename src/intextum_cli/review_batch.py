"""Batch re-extraction selection, progress, and completion feedback."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from nicegui import run, ui

from .reextraction import availability
from .review_actions import ReviewActions
from .view import Library


class BatchExtraction:
    def __init__(
        self,
        library: Library,
        actions: ReviewActions,
        on_started: Callable[[], None],
        on_finished: Callable[[], Awaitable[None]],
    ):
        self.client = ui.context.client
        self.library = library
        self.actions = actions
        self.on_started = on_started
        self.on_finished = on_finished

    def show(self, rows: list[dict], entries: list[dict]) -> None:
        """Confirm re-extraction of every result in the current list."""
        reviewed = {e["slug"] for e in entries if e.get("reviewed")}
        slugs = list(dict.fromkeys(row["slug"] for row in rows))
        reason = availability(self.library)
        with (
            self.actions.host(),
            ui.dialog() as dialog,
            ui.card().classes("w-[480px] max-w-full gap-3"),
        ):
            ui.label("Re-extract this list").classes("text-lg font-semibold")
            summary = ui.label().classes("text-sm")
            ui.label(
                "Each result is classified and extracted again with the current "
                "model settings and any viewer class choice. This calls the model "
                "and reopens review; corrections stay in history."
            ).classes("text-sm muted")
            skip = ui.checkbox("Skip reviewed results", value=True)
            if reason:
                ui.label(reason).classes("field-issue")

            def selection():
                return [s for s in slugs if not (skip.value and s in reviewed)]

            def describe():
                count = len(selection())
                summary.set_text(
                    f"{count} result(s) from {len(rows)} listed document(s)."
                )
                start.set_enabled(bool(count) and not reason and not self.actions.busy)

            async def begin():
                dialog.close()
                await self.run(selection())

            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                start = ui.button("Re-extract", on_click=begin).props("no-caps")
            skip.on_value_change(describe)
            describe()
        dialog.open()

    async def run(self, slugs: list[str]) -> None:
        # The confirming dialog may be cleared meanwhile; report from the page.
        with self.client.content:
            await self._run(slugs)

    async def _run(self, slugs: list[str]) -> None:
        self.actions.busy = True
        self.on_started()
        done = 0

        def progress(count):
            nonlocal done
            done = count

        note = ui.notification(
            f"Re-extracting 0 / {len(slugs)}…",
            spinner=True,
            timeout=None,
            position="bottom-right",
        )

        def show_progress():
            note.message = f"Re-extracting {done} / {len(slugs)}…"

        timer = ui.timer(0.5, show_progress)
        try:
            results = await run.io_bound(self.library.reextract_many, slugs, progress)
        except Exception as exc:  # model, network, and conversion errors
            ui.notify(str(exc), type="negative")
        else:
            failed = sum(r.get("status") == "failed" for r in results)
            pending = sum(bool(r.get("needs_review")) for r in results)
            # Batches can outlast a glance away; keep the outcome until dismissed.
            ui.notify(
                f"Re-extracted {len(results)} result(s): "
                f"{pending} need review, {failed} failed.",
                type="negative" if failed else "positive",
                timeout=0,
                close_button="OK",
            )
        finally:
            timer.cancel()
            note.dismiss()
            self.actions.busy = False
            await self.on_finished()
