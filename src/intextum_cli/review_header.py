"""Result title, review status, navigation, and the result actions menu."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import quote

from nicegui import ui


def render_header(
    result: dict | None,
    slug: str | None,
    file: str | None,
    rows: list[dict],
    on_move: Callable[[int], Awaitable[None]],
    menu: Callable[[str, dict], None],
) -> None:
    if result is None:
        with ui.column().classes("gap-0 min-w-0"):
            ui.label("Your review workspace").classes("document-title")
            ui.label("Run an extraction to populate this workspace.").classes(
                "muted text-xs"
            )
        return
    with ui.column().classes("gap-0 min-w-0 grow"):
        details = [(result.get("class") or {}).get("name") or "Unclassified"]
        if len(result.get("files") or []) > 1:
            details.append(f"shared result: {result.get('group') or slug}")
        ui.label(" · ".join(details)).classes("eyebrow")
        ui.label(Path(file).name if file else result.get("group") or slug).classes(
            "document-title"
        )
    status_badge(result)
    position = next(
        (i for i, e in enumerate(rows) if e["slug"] == slug and e["file"] == file),
        -1,
    )
    with ui.row().classes("items-center gap-0 no-wrap"):
        prev = (
            ui.button(icon="chevron_left", on_click=lambda: on_move(-1))
            .props("flat round dense aria-label='Previous document'")
            .tooltip("Previous (Alt + ↑)")
        )
        prev.set_enabled(position > 0)
        ui.label(f"{position + 1} / {len(rows)}" if position >= 0 else "–").classes(
            "navigation-count"
        )
        nxt = (
            ui.button(icon="chevron_right", on_click=lambda: on_move(1))
            .props("flat round dense aria-label='Next document'")
            .tooltip("Next (Alt + ↓)")
        )
        nxt.set_enabled(bool(rows) and position < len(rows) - 1)
    with (
        ui.button(icon="more_vert")
        .props("flat round dense aria-label='More actions'")
        .mark("result-menu")
    ):
        with ui.menu().props("auto-close"):
            menu(slug, result)
            ui.separator()
            ui.menu_item(
                "Download result JSON",
                on_click=lambda: ui.download(f"/api/export/{quote(slug, safe='')}"),
            )


def status_badge(result: dict) -> None:
    if result.get("status") == "failed":
        label, kind = "Failed", "failed"
    elif (result.get("review") or {}).get("state") == "reviewed":
        label, kind = "Reviewed", "complete"
    elif result.get("needs_review"):
        label, kind = "Needs review", "needs-review"
    elif result.get("edits"):
        label, kind = "Edited", "edited"
    else:
        label, kind = "Complete", "complete"
    ui.label(label).classes("status-badge " + kind)
