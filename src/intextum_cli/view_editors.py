"""NiceGUI controls for schema-aware corrections, including repeated fields."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from nicegui import ui

from .review import ROW_ID
from .schema import REPEATED_DTYPES, SchemaField
from .values import coerce


def table_data(value: list, spec: SchemaField) -> tuple[list[dict], list[dict]]:
    names = (
        [child.name for child in spec.fields]
        if spec.dtype == "object_list"
        else ["value"]
    )
    if spec.dtype == "object_list":
        names += [key for item in value for key in item if key not in names]
        names = list(dict.fromkeys(names))
    rows = []
    for index, item in enumerate(value):
        row = dict(item) if spec.dtype == "object_list" else {"value": item}
        rows.append(
            {
                ROW_ID: index,
                **{
                    key: json.dumps(cell, ensure_ascii=False)
                    if isinstance(cell, dict | list)
                    else cell
                    for key, cell in row.items()
                },
            }
        )
    columns = [
        {
            "name": key,
            "field": key,
            "label": key.replace("_", " "),
            "align": "left",
            "sortable": True,
        }
        for key in names
    ]
    return rows, columns


def table_editor(value: list, spec: SchemaField) -> Callable[[], Any]:
    rows, columns = table_data(value, spec)
    ui.label("Click a cell to edit. Changes are saved together.").classes("editor-help")
    table = (
        ui.table(
            rows=rows,
            columns=columns,
            row_key=ROW_ID,
            selection="multiple",
            pagination=10,
        )
        .classes("w-full edit-table")
        .props("flat bordered wrap-cells")
    )
    # Quasar's popup editor sends cell updates through NiceGUI's event channel.
    table.add_slot(
        "body-cell",
        """
        <q-td :props="props" class="editable-cell">
          <span>
            {{ props.value === null || props.value === '' ? '—' : props.value }}
          </span>
          <q-popup-edit v-model="props.row[props.col.field]" v-slot="edit" buttons
            label-set="Apply"
            @update:model-value="() => $parent.$emit('cell-change', props.row)">
            <q-input v-model="edit.value" dense autofocus @keyup.enter="edit.set"
              :label="props.col.label" />
          </q-popup-edit>
        </q-td>
    """,
    )

    def update(event):
        row = next(item for item in table.rows if item[ROW_ID] == event.args[ROW_ID])
        row.update(event.args)
        table.update()

    def add():
        key = max((row[ROW_ID] for row in table.rows), default=-1) + 1
        table.rows.append({ROW_ID: key, **{c["field"]: None for c in columns}})
        table.update()

    def remove():
        selected = {row[ROW_ID] for row in table.selected}
        table.rows = [row for row in table.rows if row[ROW_ID] not in selected]
        table.selected = []
        table.update()

    table.on("cell-change", update)
    with ui.row().classes("gap-2"):
        ui.button("Add row", icon="add", on_click=add).props("outline no-caps")
        ui.button("Remove selected", icon="delete_outline", on_click=remove).props(
            "flat no-caps"
        )

    def read():
        result = []
        children = {child.name: child for child in spec.fields}
        for row in table.rows:
            clean = {key: cell for key, cell in row.items() if key != ROW_ID}
            if spec.dtype == "list":
                result.append(clean.get("value"))
                continue
            for key, child in children.items():
                if child.dtype in {"list", "currency"} and isinstance(
                    clean.get(key), str
                ):
                    try:
                        clean[key] = json.loads(clean[key])
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"{key}: enter valid JSON") from exc
            result.append(clean)
        return result

    return read


def value_editor(value: Any, spec: SchemaField) -> Callable[[], Any]:
    label = spec.name.replace("_", " ")
    if spec.dtype in REPEATED_DTYPES:
        return table_editor(value or [], spec)
    if spec.dtype == "currency":
        current = value if isinstance(value, dict) else {}
        with ui.row().classes("w-full items-start gap-3"):
            amount = (
                ui.number(
                    "Amount", value=coerce(current.get("amount"), "float"), step=0.01
                )
                .classes("grow")
                .props("outlined")
            )
            code = (
                ui.input("Currency", value=current.get("currency") or "")
                .classes("w-28")
                .props("outlined maxlength=3")
            )
        return lambda: (
            {"amount": amount.value, "currency": code.value or None}
            if amount.value is not None
            else None
        )
    if spec.dtype == "bool":
        control = (
            ui.select(
                ["Not provided", "Yes", "No"],
                value="Not provided" if value is None else "Yes" if value else "No",
                label=label,
            )
            .classes("w-full")
            .props("outlined")
        )
        return lambda: {"Not provided": None, "Yes": True, "No": False}[control.value]
    if spec.enum:
        control = (
            ui.select(
                spec.enum, value=value if value in spec.enum else None, label=label
            )
            .classes("w-full")
            .props("outlined clearable")
        )
    elif spec.dtype in {"int", "float"}:
        initial = coerce(value, spec.dtype)
        control = (
            ui.number(
                label,
                value=initial if isinstance(initial, int | float) else None,
                step=1 if spec.dtype == "int" else 0.01,
            )
            .classes("w-full")
            .props("outlined clearable")
        )
    elif spec.dtype == "date":
        control = (
            ui.input(label, value=coerce(value, "date") or "")
            .classes("w-full")
            .props("outlined type=date clearable")
        )
    else:
        control = (
            ui.textarea(label, value="" if value is None else str(value))
            .classes("w-full")
            .props("outlined autogrow")
        )
    return lambda: control.value if control.value != "" else None
