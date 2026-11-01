import pytest

from intextum_cli.values import (
    ambiguous_number,
    coerce,
    is_empty,
    validation_errors,
)


@pytest.mark.parametrize(
    "value, dtype, expected",
    [
        ("1.234,56", "float", 1234.56),
        ("1,234.56", "float", 1234.56),
        ("1234.56", "float", 1234.56),
        ("30.000", "float", 30000.0),
        ("1,500", "float", 1500.0),
        ("1.234.567", "float", 1234567.0),
        ("1,234,567", "float", 1234567.0),
        ("0.125", "float", 0.125),
        ("-0,125", "float", -0.125),
        ("1,5", "float", 1.5),
        ("12.50", "float", 12.5),
        ("30.000", "int", 30000),
        ("30.000 €", "currency", {"amount": 30000.0, "currency": "EUR"}),
        ("12", "int", 12),
        (3.0, "int", 3),
        ("ja", "bool", True),
        ("31.12.2025", "date", "2025-12-31"),
        ("2025-01-02", "date", "2025-01-02"),
        ("1.234,50 €", "currency", {"amount": 1234.5, "currency": "EUR"}),
        ("30.000,00 DM", "currency", {"amount": 30000.0, "currency": "DEM"}),
        (
            {"amount": 286000, "currency": "DM"},
            "currency",
            {"amount": 286000.0, "currency": "DEM"},
        ),
        (
            {"amount": "99", "currency": "usd"},
            "currency",
            {"amount": 99.0, "currency": "USD"},
        ),
        (["a", "n/a", " b "], "list", ["a", "b"]),
        ("N/A", "str", None),
        ("  x ", "str", "x"),
    ],
)
def test_coerce(value, dtype, expected):
    assert coerce(value, dtype) == expected


def test_is_empty():
    assert (
        is_empty(None) and is_empty(" ") and is_empty("keine Angabe") and is_empty([])
    )
    assert not is_empty(0) and not is_empty(False)


def test_validation_errors():
    assert validation_errors("soon", "date") == ["invalid_date"]
    assert validation_errors("x", "str", ["a", "b"]) == ["not_in_enum"]
    assert validation_errors(["a", "z"], "list", ["a"]) == ["not_in_enum"]
    assert validation_errors({"amount": 1.0, "currency": "EURO"}, "currency") == [
        "invalid_currency"
    ]
    assert validation_errors(True, "int") == ["invalid_integer"]
    assert validation_errors(None, "int") == []


def test_control_characters_are_flagged():
    assert validation_errors("M\x0fller", "str") == ["invalid_characters"]
    assert validation_errors(["ok", "sp\x04testens"], "list") == ["invalid_characters"]
    assert validation_errors("line\nbreak\ttab", "str") == []


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2.125", True),
        ("1,250", True),
        ("-30.000", True),
        ("0.125", False),
        ("1.5", False),
        ("1.234,56", False),
        ("1.234.567", False),
        (2.125, False),
    ],
)
def test_ambiguous_number(text, expected):
    assert ambiguous_number(text) is expected
