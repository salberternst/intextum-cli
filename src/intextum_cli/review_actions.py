"""Class changes, extraction, review status, and completion for shared results."""

from __future__ import annotations

from nicegui import run, ui

from .edits import correction_applies
from .reextraction import availability
from .review import display_value
from .store import StorageError
from .verification import NONE_OPTION
from .view import Library

# Select value for "none of the classes fits"; class names are never NUL-prefixed.
_NO_MATCH = "\0no-match"


class ReviewActions:
    def __init__(self, library: Library, on_saved, on_reviewed):
        self.library = library
        self.client = ui.context.client
        self.on_saved = on_saved
        # Called with the reviewed slug, so the queue can advance.
        self.on_reviewed = on_reviewed
        self.busy = False
        self.buttons = []
        self.dialog_host = None
        self.approve = None

    def menu(self, slug: str, result: dict) -> None:
        """Less frequent actions, rendered inside the header's overflow menu."""
        change = ui.menu_item(
            "Change class…", on_click=lambda: self.class_dialog(slug, result)
        ).mark("change-class")
        extract = ui.menu_item(
            "Re-extract group", on_click=lambda: self.extract(slug, result)
        ).mark("reextract")
        reason = availability(self.library)
        for item in (change, extract):
            if self.busy:
                item.props("disable")
        if reason:
            extract.props("disable")
            extract.tooltip(reason)
        if result["review"]["history"] or self.inactive_corrections(result):
            ui.menu_item("Review history…", on_click=lambda: self.history(result))

    def render(self, fields, slug: str | None, result: dict | None) -> None:
        """Review status above the fields and the completion action below them."""
        self.buttons = []
        self.approve = None
        fields.status_box.clear()
        fields.footer.clear()
        fields.footer.set_visibility(result is not None)
        if result is None:
            return
        review = result["review"]
        with fields.status_box:
            if review["pending_extraction"]:
                selected = review["class_override"] or "automatic classification"
                with ui.row().classes("review-banner pending w-full items-center"):
                    ui.icon("sync_problem", size="18px")
                    ui.label(
                        f"Class changed to {selected}. Re-extract to update fields."
                    ).classes("grow")
                    extract = self.button(
                        "Re-extract", lambda: self.extract(slug, result), primary=True
                    )
                    if reason := availability(self.library):
                        extract.disable()
                        extract.tooltip(reason)
            elif review["classification_action"] == "no_match":
                with ui.row().classes("review-banner w-full items-center"):
                    ui.icon("block", size="18px")
                    ui.label("No matching class confirmed for this group.")
            elif review["classification_action"] == "automatic":
                self.class_check(slug, result)
            issues = list(result.get("review_reasons") or [])
            if result.get("error"):
                issues.insert(0, result["error"])
            if issues and review["state"] != "reviewed":
                with ui.expansion(
                    f"{len(issues)} review item(s)", icon="fact_check"
                ).classes("review-issues w-full"):
                    for reason in issues:
                        ui.label(reason.replace("_", " ")).classes("text-xs")
            if result.get("warnings"):
                with ui.expansion(
                    f"{len(result['warnings'])} processing warning(s)",
                    icon="info_outline",
                ).classes("processing-notes w-full"):
                    for warning in result["warnings"]:
                        ui.label(warning).classes("text-xs muted")
        with fields.footer:
            if review["state"] == "reviewed":
                text = f"Reviewed {review['at'][:16].replace('T', ' ')}"
                if review["note"]:
                    text += f" · {review['note']}"
                ui.label(text).classes("muted text-xs grow min-w-0 ellipsis")
                self.button(
                    "Reopen review",
                    lambda: self.decide(slug, result, "reopen"),
                )
                return
            blocked = None
            if result.get("status") == "failed":
                blocked = "Re-extract this failed result before reviewing it."
            elif review["pending_extraction"]:
                blocked = "Re-extract the selected class before reviewing it."
            if blocked:
                ui.label(blocked).classes("muted text-xs grow min-w-0")
            else:
                note = (
                    ui.input(placeholder="Review note (optional)")
                    .props("dense outlined aria-label='Review note'")
                    .classes("review-note grow min-w-0")
                )
            finish = self.button(
                "Mark reviewed",
                None,
                primary=True,
                icon="check",
            ).tooltip("Mark reviewed and open the next document (Alt + Enter)")
            finish.set_enabled(not self.busy and blocked is None)
            if blocked is None:

                async def approve():
                    if self.busy or not finish.enabled:
                        return
                    finish.disable()
                    await self.decide(slug, result, "approve", note.value or "")

                self.approve = approve
                finish.on_click(approve)
                note.on("keydown.enter", approve)

    @staticmethod
    def inactive_corrections(result: dict) -> list[dict]:
        return [
            edit
            for edit in result.get("edits", [])
            if not correction_applies(result, edit)
            or result["review"]["classification_action"] == "no_match"
        ]

    def history(self, result: dict) -> None:
        with (
            self.host(),
            ui.dialog() as dialog,
            ui.card().classes("w-[520px] max-w-full gap-3"),
        ):
            ui.label("Review history").classes("text-lg font-semibold")
            for event in reversed(result["review"]["history"]):
                text = event["action"].replace("_", " ")
                if event.get("class_name"):
                    text += ": " + event["class_name"]
                if event.get("note"):
                    text += " · " + event["note"]
                with ui.column().classes("gap-0"):
                    ui.label(text).classes("text-sm")
                    ui.label(event["at"]).classes("muted text-xs")
            if inactive := self.inactive_corrections(result):
                ui.label("Previous class corrections").classes("text-sm font-semibold")
                ui.label(
                    "Retained for reference; these values are not applied."
                ).classes("muted text-xs")
                for edit in reversed(inactive):
                    with ui.column().classes("gap-0"):
                        ui.label(
                            f"{edit.get('class_name') or 'Previous class'} · "
                            f"{edit['field']}: {display_value(edit.get('value'))}"
                        ).classes("text-sm")
                        details = edit.get("at", "")
                        if edit.get("note"):
                            details += " · " + edit["note"]
                        ui.label(details).classes("muted text-xs")
            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dialog.close).props("flat no-caps")
        dialog.open()

    def host(self):
        """A page-level parent, so dialogs outlive the menu or row that opened them."""
        if self.dialog_host is None:
            with self.client.content:
                self.dialog_host = ui.element("div")
        self.dialog_host.clear()
        return self.dialog_host

    def button(self, label, callback, *, primary=False, icon=None):
        button = ui.button(label, icon=icon, on_click=callback).props(
            "unelevated dense no-caps" if primary else "outline dense no-caps"
        )
        button.classes("action-button")
        button.set_enabled(not self.busy)
        self.buttons.append(button)
        return button

    def class_check(self, slug: str, result: dict) -> None:
        """The verifier's view of the automatic class, with a one-click switch."""
        check = result.get("class_check")
        if not check:
            return
        doubtful = "class_doubtful" in (result.get("review_reasons") or [])
        suggestion = check["suggestion"]
        current = (result.get("class") or {}).get("name")
        if not doubtful:
            text = (
                f"No class fits — {check['probability']:.0%} sure"
                if check["unclassified"]
                else f"Class confirmed — {check['probability']:.0%}"
            )
            with ui.row().classes("review-banner w-full items-center"):
                ui.icon("verified", size="18px")
                ui.label(text).classes("grow")
                ui.label(check["model"]).classes("muted text-xs")
            return
        with ui.row().classes("review-banner pending w-full items-center"):
            ui.icon("help_outline", size="18px")
            if suggestion:
                prefix = "Possibly" if check["unclassified"] else "Verifier suggests"
                text = f"{prefix} {suggestion} — {check['suggestion_probability']:.0%}"
            else:
                text = (
                    f"Probably none of the classes fits — "
                    f"{check['suggestion_probability']:.0%}, {current} "
                    f"{check['probability']:.0%}"
                )
            ui.label(text).classes("grow")
            if suggestion:
                self.button(
                    f"Use {suggestion}",
                    lambda: self.use_class(slug, result, suggestion),
                    primary=True,
                )
            else:
                self.button("Change class…", lambda: self.class_dialog(slug, result))

    async def use_class(self, slug: str, result: dict, name: str) -> None:
        try:
            await run.io_bound(
                self.library.review_action,
                slug,
                "class",
                result["review"]["revision"],
                name,
                "Suggested by the verifier",
            )
        except (ValueError, KeyError, OSError, StorageError) as exc:
            ui.notify(str(exc), type="negative")
            return
        with self.client:
            await self.on_saved()
            ui.notify(f"Class set to {name}. Re-extract to update the fields.")

    async def decide(self, slug: str, result: dict, action: str, note: str = ""):
        try:
            await run.io_bound(
                self.library.review_action,
                slug,
                action,
                result["review"]["revision"],
                None,
                note,
            )
        except (ValueError, KeyError, OSError, StorageError) as exc:
            ui.notify(str(exc), type="negative")
            await self.on_saved()
            return
        with self.client:
            if action == "approve":
                await self.on_reviewed(slug)
            else:
                await self.on_saved()

    def class_dialog(self, slug: str, result: dict):
        with (
            self.host(),
            ui.dialog() as dialog,
            ui.card().classes("w-[480px] max-w-full"),
        ):
            ui.label("Change class").classes("text-lg font-semibold")
            ui.label(
                f"Applies to group {result['group']} and all "
                f"{len(result.get('files') or [])} source file(s)."
            ).classes("text-sm muted")
            classes = self.library.classes
            if classes is None:
                classes = self.library.store.results.classes(result["group"])
            # The verifier's probabilities, when it checked this classification.
            scores = (result.get("class_check") or {}).get("probabilities") or {}

            def scored(label: str, option: str) -> str:
                return f"{label} · {scores[option]:.0%}" if option in scores else label

            options = {"": "Automatic classification"}
            options.update({c.name: scored(c.name, c.name) for c in classes})
            options[_NO_MATCH] = scored("None of these classes", NONE_OPTION)
            if result["review"]["classification_action"] == "no_match":
                selected = _NO_MATCH
            else:
                selected = (
                    result["review"]["class_override"]
                    or (result.get("class") or {}).get("name")
                    or ""
                )
            choice = ui.select(
                options,
                value=selected if selected in options else "",
                label="Document class",
            ).classes("w-full")
            hint = ui.label().classes("text-sm muted")

            def describe():
                hint.set_text(
                    "This completes review without calling the model and "
                    "removes fields from the current result."
                    if choice.value == _NO_MATCH
                    else "Save the selection, then re-extract the group to "
                    "replace its fields. Previous corrections remain in history."
                )

            choice.on_value_change(describe)
            describe()
            note = ui.textarea("Review note (optional)").classes("w-full")

            async def save():
                action, class_name = "class", choice.value
                if class_name == _NO_MATCH:
                    action, class_name = "no_match", None
                elif not class_name:
                    action = "automatic"
                save_button.disable()
                try:
                    await run.io_bound(
                        self.library.review_action,
                        slug,
                        action,
                        result["review"]["revision"],
                        class_name,
                        note.value or "",
                    )
                except (ValueError, KeyError, OSError, StorageError) as exc:
                    ui.notify(str(exc), type="negative")
                    save_button.enable()
                    return
                dialog.close()
                with self.client:
                    if action == "no_match":
                        # Confirming no class completes review; continue the queue.
                        await self.on_reviewed(slug)
                    else:
                        await self.on_saved()
                    ui.notify("Class saved")

            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                save_button = ui.button("Save class", on_click=save).props("no-caps")
        dialog.open()

    async def extract(self, slug: str, result: dict):
        if self.busy:
            return
        self.busy = True
        for button in self.buttons:
            button.disable()
        with self.client.content:
            await self.run_extraction(slug, result)

    async def run_extraction(self, slug: str, result: dict):
        ui.notify("Re-extracting group…")
        try:
            updated = await run.io_bound(
                self.library.reextract, slug, result["review"]["revision"]
            )
            if updated.get("status") == "failed":
                ui.notify(updated.get("error") or "Extraction failed", type="negative")
            else:
                ui.notify("Group re-extracted. Check its fields, then mark reviewed.")
        except Exception as exc:  # model, network, and conversion errors
            ui.notify(str(exc), type="negative")
        finally:
            self.busy = False
            await self.on_saved()
