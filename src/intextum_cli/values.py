"""Value coercion and validation per field dtype."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

_MISSING_VALUE_PLACEHOLDERS = frozenset(
    {
        "-", "--", "n/a", "na", "n.a.", "none", "null", "unknown",
        "not applicable", "not available", "not provided", "not specified",
        "nicht angegeben", "keine angabe", "k. a.", "k.a.",
    }
)  # fmt: skip
_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y")
# Garbled unicode escapes from a model show up as control characters.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Symbols and common abbreviations that are not ISO 4217 codes.
_CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP", "DM": "DEM"}


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        normalized = " ".join(value.split()).casefold()
        return not normalized or normalized in _MISSING_VALUE_PLACEHOLDERS
    if isinstance(value, list | dict):
        return len(value) == 0
    return False


def _parse_number(text: str) -> float | None:
    """Parse ``1.234,56`` / ``1,234.56`` / ``1234.56`` style numbers."""
    cleaned = re.sub(r"[^0-9,.\-]", "", text)
    if not cleaned:
        return None
    last_comma, last_dot = cleaned.rfind(","), cleaned.rfind(".")
    if last_comma >= 0 and last_dot >= 0:
        # Both appear: the last one is the decimal separator.
        thousands, decimal = (".", ",") if last_comma > last_dot else (",", ".")
        cleaned = cleaned.replace(thousands, "").replace(decimal, ".")
    elif last_comma >= 0 or last_dot >= 0:
        separator = "," if last_comma >= 0 else "."
        whole, _, fraction = cleaned.rpartition(separator)
        # Repeated, or followed by exactly three digits after a non-zero whole
        # part, it groups thousands: "30.000", "1,500", "1.234.567".
        if cleaned.count(separator) > 1 or (
            len(fraction) == 3 and whole.lstrip("-") not in {"", "0"}
        ):
            cleaned = cleaned.replace(separator, "")
        else:
            cleaned = cleaned.replace(separator, ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def ambiguous_number(value: Any) -> bool:
    """Whether text read as thousands could be a decimal: ``2.125``, ``1,250``."""
    if not isinstance(value, str):
        return False
    cleaned = re.sub(r"[^0-9,.\-]", "", value)
    return re.fullmatch(r"-?(?!0[.,])\d+[.,]\d{3}", cleaned) is not None


def coerce(value: Any, dtype: str) -> Any:
    """Best-effort conversion of an LLM value to the field's dtype.

    Values that cannot be converted are returned unchanged so validation can flag
    them instead of silently dropping them.
    """
    if is_empty(value):
        return [] if dtype == "list" else None
    if dtype == "list":
        items = value if isinstance(value, list) else [value]
        return [
            item.strip() if isinstance(item, str) else item
            for item in items
            if not is_empty(item)
        ]
    if dtype == "bool":
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in {"true", "yes", "1", "ja"}:
                return True
            if normalized in {"false", "no", "0", "nein"}:
                return False
        return value
    if dtype == "int":
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            number = _parse_number(value)
            if number is not None and number.is_integer():
                return int(number)
            return value.strip()
        return value
    if dtype == "float":
        if isinstance(value, int) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            number = _parse_number(value)
            return number if number is not None else value.strip()
        return value
    if dtype == "date":
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            text = value.strip()
            for fmt in _DATE_FORMATS:
                try:
                    return datetime.strptime(text, fmt).date().isoformat()
                except ValueError:
                    continue
            return text
        return value
    if dtype == "currency":
        return _coerce_currency(value)
    if isinstance(value, str):
        return value.strip()
    return value


def _coerce_currency(value: Any) -> Any:
    if isinstance(value, dict):
        amount = coerce(value.get("amount"), "float")
        currency = value.get("currency")
        if isinstance(amount, float):
            code = currency.strip() if isinstance(currency, str) else ""
            return {
                "amount": amount,
                "currency": _CURRENCY_SYMBOLS.get(code.upper(), code.upper()) or None,
            }
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return {"amount": float(value), "currency": None}
    if isinstance(value, str):
        text = value.strip()
        match = re.search(r"\b([A-Z]{3}|DM)\b|([€$£])", text)
        currency = None
        if match:
            raw = match.group(1) or match.group(2)
            currency = _CURRENCY_SYMBOLS.get(raw, raw)
        amount = _parse_number(text)
        if amount is not None:
            return {"amount": amount, "currency": currency}
        return text
    return value


def validation_errors(
    value: Any, dtype: str, enum: list[str] | None = None
) -> list[str]:
    if is_empty(value):
        return []
    if dtype == "str":
        if not isinstance(value, str):
            return ["invalid_string"]
        if _CONTROL_RE.search(value):
            return ["invalid_characters"]
        return ["not_in_enum"] if enum and value not in enum else []
    if dtype == "int":
        ok = isinstance(value, int) and not isinstance(value, bool)
        return [] if ok else ["invalid_integer"]
    if dtype == "float":
        ok = isinstance(value, int | float) and not isinstance(value, bool)
        return [] if ok else ["invalid_number"]
    if dtype == "bool":
        return [] if isinstance(value, bool) else ["invalid_boolean"]
    if dtype == "list":
        if not isinstance(value, list):
            return ["invalid_list"]
        errors = sorted(
            {e for item in value for e in validation_errors(item, "str", enum)}
        )
        return errors
    if dtype == "date":
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return []
        except (TypeError, ValueError):
            return ["invalid_date"]
    if dtype == "currency":
        ok = (
            isinstance(value, dict)
            and isinstance(value.get("amount"), int | float)
            and not isinstance(value.get("amount"), bool)
            and (
                value.get("currency") is None
                or (isinstance(value["currency"], str) and len(value["currency"]) == 3)
            )
        )
        return [] if ok else ["invalid_currency"]
    return []
