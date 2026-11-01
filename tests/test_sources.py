import os

import pytest

from intextum_cli.schema import DocumentClass
from intextum_cli.sources import (
    SourcesError,
    canonical_number,
    identifiers,
    is_uncertain,
    load_overrides,
    rank_candidates,
)

TABLE = DocumentClass.model_validate({"class": "Item list", "description": "Table"})
MAP = DocumentClass.model_validate({"class": "Site map", "description": "Map"})


@pytest.mark.parametrize(
    "token, expected",
    [("753,24", "753.24"), ("753.24", "753.24"), ("60,00", "60"), ("1.234,50", "1234.5"),
     ("1.234.567", "1234567"), ("0,8", "0.8"), ("abc", None)],
)  # fmt: skip
def test_canonical_number(token, expected):
    assert canonical_number(token) == expected


def test_identifiers_normalise_dates_and_numbers():
    ids = identifiers(
        "Item 12/3, from 01.10.2027 or 2027-10-01, 753,24 € and 3,4 kg, No. 7"
    )
    assert {"12/3", "2027-10-01", "753.24", "3.4"} <= ids
    assert "7" not in ids


def write(root, name, text, mtime=1_700_000_000):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_rank_prefers_the_table_with_the_documents_values(tmp_path):
    main = write(
        tmp_path,
        "t/order_harbor.doc.txt",
        "Order total 753,24 €, see the table in the annex",
    )
    final = write(
        tmp_path, "t/items_final.xlsx.txt", "SampleDepot | 5 | 46 | 2 | Total 753.24"
    )
    draft = write(
        tmp_path, "t/items_draft.xlsx.txt", "SampleDepot | 5 | 99 | 1 | Total 610.00"
    )
    old_map = write(tmp_path, "t/site_map.pdf.txt", "Scale 1:5000", mtime=1_500_000_000)
    ranked = rank_candidates(
        tmp_path,
        main,
        main.read_text(),
        {"order_total": "753.24", "site": "SampleDepot", "line_items": []},
        "line_items",
        "see the table in the annex",
        {path: path.read_text() for path in (final, draft, old_map)},
        {final: TABLE, draft: TABLE, old_map: MAP},
    )
    assert [c.path for c in ranked] == [final, draft, old_map]
    best = ranked[0]
    assert "contains 753.24" in " ".join(best.reasons)
    assert "document refers to a table" in best.reasons
    assert "draft vs. final" in ranked[1].reasons
    assert not is_uncertain(ranked)


def test_values_found_in_every_candidate_do_not_count(tmp_path):
    main = write(tmp_path, "t/order.txt", "Customer Globex Inc")
    a = write(tmp_path, "t/a.txt", "Globex")
    b = write(tmp_path, "t/b.txt", "Globex")
    ranked = rank_candidates(
        tmp_path, main, main.read_text(), {"customer": "Globex Inc"}, "line_items", None,
        {a: "Globex", b: "Globex"}, {a: None, b: None},
    )  # fmt: skip
    assert all("contains" not in " ".join(c.reasons) for c in ranked)
    assert is_uncertain(ranked)


def test_load_overrides(tmp_path):
    write(tmp_path, "t/a.xlsx", "a")
    write(tmp_path, "t/b.xlsx", "b")
    (tmp_path / "sources.yaml").write_text(
        "sources:\n"
        "  t/order.doc:\n"
        "    line_items: t/a.xlsx\n"
        "    conditions: [t/a.xlsx, t/b.xlsx]\n"
        "    addresses: none\n"
        "  t/other.doc:\n"
        "    line_items:\n",
        encoding="utf-8",
    )
    overrides = load_overrides(tmp_path)
    assert overrides["t/order.doc"]["line_items"] == [(tmp_path / "t/a.xlsx").resolve()]
    assert len(overrides["t/order.doc"]["conditions"]) == 2
    assert overrides["t/order.doc"]["addresses"] is None
    assert overrides["t/other.doc"]["line_items"] is None
    assert load_overrides(tmp_path / "t") == {}


@pytest.mark.parametrize(
    "content, message",
    [
        ("sources:\n  t/v.doc:\n    line_items: t/missing.xlsx\n", "file not found"),
        ("sources: [a]\n", "top-level 'sources:' mapping"),
        ("sources:\n  t/v.doc: t/a.xlsx\n", "must map field names"),
    ],
)
def test_load_overrides_errors(tmp_path, content, message):
    (tmp_path / "sources.yaml").write_text(content)
    with pytest.raises(SourcesError, match=message):
        load_overrides(tmp_path)
