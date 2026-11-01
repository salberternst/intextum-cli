"""Direct readers used when a document does not need or cannot use Docling."""

from __future__ import annotations

import csv
import re
from pathlib import Path


def read_csv_text(path: Path) -> tuple[list[str], str]:
    """Read a CSV that Docling rejects (e.g. Windows encoding) as a Markdown table.

    Returns the pages and a note describing the encoding and delimiter used.
    """
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - cp1252 decodes nearly everything
        text, encoding = raw.decode("latin-1"), "latin-1"
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=";,\t|")
    except csv.Error:
        return [text], f"CSV read as plain text ({encoding}, no delimiter found)"
    rows = [row for row in csv.reader(text.splitlines(), dialect) if any(row)]
    if not rows:
        return [text], f"CSV read as plain text ({encoding})"
    width = max(len(row) for row in rows)

    def line(cells: list[str]) -> str:
        cells = [cell.replace("|", "/").strip() for cell in cells]
        return "| " + " | ".join(cells + [""] * (width - len(cells))) + " |"

    table = [line(rows[0]), "|" + "---|" * width, *(line(row) for row in rows[1:])]
    delimiter = {"\t": "tab"}.get(dialect.delimiter, dialect.delimiter)
    return [
        "\n".join(table)
    ], f"CSV read without Docling ({encoding}, delimiter {delimiter})"


def read_msg_text(path: Path) -> tuple[list[str], str]:
    """Read an Outlook .msg (Docling mistakes it for a legacy Excel file)."""
    from oxmsg import Message

    message = Message.load(path)
    lines = [f"# {message.subject or '(no subject)'}", ""]
    if message.sender:
        lines.append(f"From: {message.sender}")
    recipients = ", ".join(
        _recipient(r) for r in getattr(message, "recipients", []) or []
    )
    if recipients:
        lines.append(f"To: {recipients}")
    if message.sent_date:
        lines.append(f"Date: {message.sent_date.isoformat()}")
    names = [
        getattr(a, "file_name", None) or getattr(a, "long_file_name", None)
        for a in message.attachments or []
    ]
    names = [name for name in names if name]
    if names:
        lines.append(f"Attachments (content not included): {', '.join(names)}")
    body = message.body
    if not body and message.html_body:
        body = _html_to_text(message.html_body)
    lines += ["", (body or "").replace("\r\n", "\n")]
    note = "Outlook message read without Docling"
    if names:
        note += f"; {len(names)} attachment(s) not converted"
    return ["\n".join(lines)], note


def _recipient(recipient) -> str:
    if isinstance(recipient, str):
        return recipient
    name = getattr(recipient, "name", None)
    address = getattr(recipient, "email_address", None)
    if name and address and name != address:
        return f"{name} <{address}>"
    return name or address or ""


def _html_to_text(html: str | bytes) -> str:
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"[ \t]+", " ", text)
