import pytest

from intextum_cli.convert import ConvertedFile
from intextum_cli.extract import extract
from intextum_cli.schema import DocumentClass, load_classes
from intextum_cli.source import build_source

REGISTER_SCHEMA = """\
class: Register
description: A register with sections for assets, custodians and conditions.
fields:
  - name: assets
    dtype: object_list
    source_pages_matching: '(?im)^[ \\t]*Assets[ \\t]*$'
    fields:
      - {name: number, dtype: str, required: true}
      - {name: code, dtype: str, required: true}
      - {name: status, dtype: str, required: true, enum: [valid, removed, replaced, unclear]}
      - {name: status_quote, dtype: str, required: true, verbatim: true, quote_for: [number]}
  - name: custodians
    dtype: object_list
    source_pages_matching: '(?i)Custodians'
    fields:
      - {name: number, dtype: str, required: true}
      - {name: name, dtype: str, required: true}
      - {name: allocation, dtype: str}
      - {name: status, dtype: str, required: true, enum: [valid, removed, replaced, unclear]}
      - {name: status_quote, dtype: str, required: true, verbatim: true, quote_for: [number, name]}
  - name: conditions
    dtype: object_list
    source_pages_matching: '(?i)Conditions'
    fields:
      - {name: number, dtype: str, required: true}
      - {name: assets, dtype: list}
      - {name: description, dtype: str, required: true}
      - {name: recorded_on, dtype: date}
      - {name: removed_on, dtype: date}
      - {name: status, dtype: str, required: true, enum: [valid, removed, replaced, unclear]}
      - {name: status_quote, dtype: str, required: true, verbatim: true, quote_for: [number]}
  - name: changes
    dtype: object_list
    fields:
      - {name: section, dtype: str, required: true}
      - {name: references, dtype: list}
      - {name: date, dtype: date}
      - {name: note, dtype: str, required: true, verbatim: true}
scenes:
  - text: |-
      Conditions, entry 1, assets 4, 5, 6:
      Handling note for Example Supplies Ltd;
      recorded on 11.11.2019.
      Conditions, removals, entry 1:
      Removed on 21.05.2020.
    extractions:
      - field: conditions
        extraction_text: Handling note for Example Supplies Ltd
        value:
          number: '1'
          assets: ['4', '5', '6']
          description: Handling note
          recorded_on: '2019-11-11'
          removed_on: '2020-05-21'
          status: removed
          status_quote: Removed on 21.05.2020.
      - field: changes
        extraction_text: Removed on 21.05.2020.
        value:
          section: Conditions
          references: ['1']
          date: '2020-05-21'
          note: Removed on 21.05.2020.
"""


def register_schema(tmp_path, *names):
    path = tmp_path / "register.yaml"
    path.write_text(REGISTER_SCHEMA, encoding="utf-8")
    [schema] = load_classes(path)
    return schema.model_copy(
        update={"fields": [field for field in schema.fields if field.name in names]}
    )


def register_source(*pages):
    return build_source(
        [ConvertedFile("register.pdf", list(pages), paged=True)], max_chars=60000
    )


def test_uncertain_status_retains_historical_entry_and_requires_review(
    tmp_path, fake_llm
):
    schema = register_schema(tmp_path, "custodians")
    source = register_source("Custodians\n2b Mara Example, allocation 5/12.")
    llm = fake_llm(
        lambda *_: {
            "custodians": [
                {
                    "value": {
                        "number": "2b",
                        "name": "Mara Example",
                        "allocation": "5/12",
                        "status": "unclear",
                        "status_quote": None,
                    },
                    "evidence_anchor": "Mara Example",
                }
            ]
        }
    )
    result = extract(llm, schema, source)
    assert result.data["custodians"][0]["allocation"] == "5/12"
    assert result.data["custodians"][0]["status"] == "unclear"
    assert result.review_reasons == ["invalid:custodians"]
    assert result.fields["custodians"].validation_errors == [
        "status_quote:missing_required"
    ]


def test_entry_and_separate_removal_keep_both_source_pages(tmp_path, fake_llm):
    schema = register_schema(tmp_path, "conditions", "changes")
    scene = schema.scenes[0]
    passage, removal = scene.text.split("Conditions, removals", 1)
    source = register_source(passage, "Conditions, removals" + removal)
    examples = {example.field: example for example in scene.extractions}

    def reply(name, user, schema):
        field = next(iter(schema["properties"]))
        example = examples[field]
        return {
            field: [
                {"value": example.value, "evidence_anchor": example.extraction_text}
            ]
        }

    result = extract(fake_llm(reply), schema, source)
    entry = result.data["conditions"][0]
    assert entry["status"] == "removed"
    assert entry["recorded_on"] == "2019-11-11"
    assert entry["removed_on"] == "2020-05-21"
    assert result.fields["conditions"].item_evidence[0][0]["page"] == 1
    assert result.fields["conditions"].item_evidence[0][1]["page"] == 2
    assert result.fields["changes"].item_evidence[0][0]["page"] == 2
    assert result.review_reasons == []


def test_status_quote_from_another_section_is_rejected(tmp_path, fake_llm):
    schema = register_schema(tmp_path, "custodians")
    quote = "Asset 1 entered again as asset 4"
    source = register_source(
        "Assets\n" + quote, "Custodians\n1a Alex Example, allocation 1/2."
    )

    def reply(name, user, schema):
        assert quote not in user.split("SOURCE TEXT:", 1)[1]
        return {
            "custodians": [
                {
                    "value": {
                        "number": "1a",
                        "name": "Alex Example",
                        "allocation": "1/2",
                        "status": "removed",
                        "status_quote": quote,
                    },
                    "evidence_anchor": "Alex Example",
                }
            ]
        }

    result = extract(fake_llm(reply), schema, source)
    assert result.fields["custodians"].validation_errors == [
        "status_quote:not_in_source"
    ]
    assert result.review_reasons == ["invalid:custodians"]
    assert result.fields["custodians"].item_evidence[0][0]["page"] == 2


def test_status_quote_about_another_entry_is_rejected(tmp_path, fake_llm):
    schema = register_schema(tmp_path, "custodians")
    quote = "Allocation of Chris Sample (2a) to Example Ltd"
    source = register_source(
        "Custodians\n| 1a | Alex Example | 1/2 |\n| 2a | Chris Sample | " + quote + " |"
    )
    llm = fake_llm(
        lambda *_: {
            "custodians": [
                {
                    "value": {
                        "number": "1a",
                        "name": "Alex Example",
                        "allocation": "1/2",
                        "status": "removed",
                        "status_quote": quote,
                    },
                    "evidence_anchor": "Alex Example",
                }
            ]
        }
    )
    result = extract(llm, schema, source)
    assert result.fields["custodians"].validation_errors == [
        "status_quote:unrelated_quote"
    ]
    assert result.review_reasons == ["invalid:custodians"]


def test_full_status_note_can_continue_down_one_table_column(tmp_path, fake_llm):
    schema = register_schema(tmp_path, "assets")
    quote = "Assets 1 and 2 after cor- rection entered again as 4 and 5."
    source = register_source(
        "Assets\n| No | Code |\n|---|---|\n| 1 | 10/1 |",
        "Assets\n| No | Note |\n|---|---|\n"
        "| 1,2 | Assets 1 and 2 after cor- |\n"
        "| 4,5 | rection entered again as 4 and 5. |",
    )
    result = extract(
        fake_llm(
            lambda *_: {
                "assets": [
                    {
                        "value": {
                            "number": "1",
                            "code": "10/1",
                            "status": "replaced",
                            "status_quote": quote,
                        },
                        "evidence_anchor": "10/1",
                    }
                ]
            }
        ),
        schema,
        source,
    )
    assert result.review_reasons == []
    assert [e["page"] for e in result.fields["assets"].item_evidence[0]] == [1, 2]


def custodians_reply(number, name, quote, anchor):
    return lambda *_: {
        "custodians": [
            {
                "value": {
                    "number": number,
                    "name": name,
                    "status": "removed",
                    "status_quote": quote,
                },
                "evidence_anchor": anchor,
            }
        ]
    }


def test_repeated_status_note_is_attributed_to_its_own_entry(tmp_path, fake_llm):
    schema = register_schema(tmp_path, "custodians")
    source = register_source(
        "Custodians\n| 2 | Chris Sample | Removed |\n| 7 | Alex Example | Removed |"
    )
    result = extract(
        fake_llm(custodians_reply("7", "Alex Example", "Removed", "Alex Example")),
        schema,
        source,
    )
    assert result.review_reasons == []
    # The snippet runs on from the match, so only entry 7's note ends this soon.
    assert result.fields["custodians"].item_evidence[0][1]["snippet"] == "Removed |"


def quote_for_schema(dtype):
    return DocumentClass.model_validate(
        {
            "class": "Register",
            "fields": [
                {
                    "name": "entries",
                    "dtype": "object_list",
                    "fields": [
                        {"name": "key", "dtype": dtype},
                        {"name": "note", "verbatim": True, "quote_for": ["key"]},
                    ],
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "dtype,key,row,errors",
    [
        ("date", "07.04.2016", "| 07.04.2016 | Entfernt |", []),
        ("date", "2016-04-07", "| 7.4.16 | Entfernt |", []),
        ("date", "2016-04-07", "| 08.04.2016 | Entfernt |", ["note:unrelated_quote"]),
        ("int", "1", "| 001 | Entfernt |", []),
        ("str", "3", "| 5 | 3.000 DM Entfernt |", ["note:unrelated_quote"]),
        ("str", "3", "| Nr.3 | Entfernt |", []),
        ("str", "2", "| 2,3 | Entfernt |", []),
        ("str", "3", "| 2,3 | Entfernt |", []),
        ("str", "3", "| 5 | 3,000 DM Entfernt |", ["note:unrelated_quote"]),
        ("str", "7", "| 5 | 18.09.2018 Entfernt |", ["note:unrelated_quote"]),
    ],
)
def test_quote_identifier_is_compared_as_the_source_writes_it(
    fake_llm, dtype, key, row, errors
):
    source = register_source(row)
    reply = {
        "entries": [
            {"value": {"key": key, "note": "Entfernt"}, "evidence_anchor": "Entfernt"}
        ]
    }
    result = extract(fake_llm(lambda *_: reply), quote_for_schema(dtype), source)
    assert result.fields["entries"].validation_errors == errors


def test_wrapped_quote_on_a_marked_entry_ignores_the_mark_tags(tmp_path, fake_llm):
    schema = register_schema(tmp_path, "custodians")
    source = register_source(
        "Custodians\n| 2 | Alex Example | entfernt am [struck through] |\n"
        "|   |              | 7.4.2016 [struck through] |"
    )
    result = extract(
        fake_llm(custodians_reply("2", "Alex Example", "entfernt am 7.4.2016", "Alex")),
        schema,
        source,
    )
    assert result.review_reasons == []


def test_later_note_is_found_past_another_entrys_identical_note(tmp_path, fake_llm):
    schema = register_schema(tmp_path, "custodians")
    source = register_source(
        "Custodians\n| 7 | Alex Example | |\n"
        "| 2 | Chris Sample | Removed |\n"
        "Changes\n| 7 | Removed |"
    )
    result = extract(
        fake_llm(custodians_reply("7", "Alex Example", "Removed", "Alex Example")),
        schema,
        source,
    )
    assert result.review_reasons == []
    assert result.fields["custodians"].item_evidence[0][1]["snippet"] == "Removed |"


def test_quote_keeps_a_mark_tag_as_proof(tmp_path, fake_llm):
    schema = register_schema(tmp_path, "custodians")
    source = register_source("Custodians\n| 2 | Alex Example | Entfernt [underlined] |")
    result = extract(
        fake_llm(
            custodians_reply("2", "Alex Example", "Entfernt [underlined]", "Alex")
        ),
        schema,
        source,
    )
    assert result.data["custodians"][0]["status_quote"] == "Entfernt [underlined]"
    assert result.review_reasons == []


def bool_implied_schema(implied_by):
    return DocumentClass.model_validate(
        {
            "class": "Register",
            "fields": [
                {
                    "name": "entries",
                    "dtype": "object_list",
                    "fields": [
                        {"name": "key"},
                        {"name": "removed", "dtype": "bool", "implied_by": implied_by},
                        {"name": "proof", "verbatim": True},
                    ],
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "row,removed,proof,errors",
    [
        ("| 1 | Transport | Entfernt |", False, "Entfernt", True),
        ("| 1 | Transport | |", True, None, True),
        ("| 1 | Transport | Entfernt |", True, "Entfernt", False),
        ("| 1 | Transport | |", False, None, False),
        # A marked line kept in the quote is proof, with or without the row check.
        ("| 1 | Transport [underlined] | |", True, "Transport [underlined]", False),
        # Without marks in the rule, one marked row does not settle the value.
        ("| 1 | Transport [underlined] | |", False, None, False),
    ],
)
def test_implied_bool_is_compared_with_quotes(fake_llm, row, removed, proof, errors):
    # An unquoted YAML ``true`` key arrives as a boolean.
    schema = bool_implied_schema({True: {"quote": r"(?i)entfern|\[underlined\]"}})
    reply = {
        "entries": [
            {
                "value": {"key": "1", "removed": removed, "proof": proof},
                "evidence_anchor": "Transport",
            }
        ]
    }
    result = extract(fake_llm(lambda *_: reply), schema, register_source(row))
    expected = ["removed:conflicts_with_source"] if errors else []
    assert result.fields["entries"].validation_errors == expected


@pytest.mark.parametrize(
    "keys,errors",
    [
        (["1", "2"], []),
        (["1", "1"], ["key:duplicate"]),
        # A missing value has a required check of its own.
        ([None, None], []),
    ],
)
def test_unique_child_flags_repeated_values(fake_llm, keys, errors):
    schema = DocumentClass.model_validate(
        {
            "class": "Register",
            "fields": [
                {
                    "name": "entries",
                    "dtype": "object_list",
                    "fields": [{"name": "key", "unique": True}, {"name": "code"}],
                }
            ],
        }
    )
    reply = {
        "entries": [
            {"value": {"key": key, "code": "12/1"}, "evidence_anchor": "12/1"}
            for key in keys
        ]
    }
    result = extract(fake_llm(lambda *_: reply), schema, register_source("| 12/1 |"))
    assert result.fields["entries"].validation_errors == errors


SHARED_NOTE = """\
| Nr. | Betrag | Text | Spalte | Entfernungen |
| --- | --- | --- | --- | --- |
| 1 | 100 | Material | 1 | Entfernt am |
| 2 | 200 | Zubehör | 2 | 18.09.2018. |
| 3 | 300 | Reinigung | 3 |  |
|  |  | Text | | Unterschrift |
| 4 | 400 | Transport | 4 |  |
"""

UNNUMBERED_NOTE = """\
| Nr. | Text | Entfernungen |
| --- | --- | --- |
| 1 | Material | Entfernt am |
|  | Fortsetzung | 18.09.2018. |
| 2 | Zubehör |  |
"""


@pytest.mark.parametrize(
    "table,key,errors",
    [
        (SHARED_NOTE, "1", []),
        (SHARED_NOTE, "2", []),
        # A numbered row right below the note, where its column is empty.
        (SHARED_NOTE, "3", []),
        # The note's column holds other text above this row.
        (SHARED_NOTE, "4", ["proof:unrelated_quote"]),
        (UNNUMBERED_NOTE, "1", []),
        # The wrapped row has no number of its own, so the note stays with entry 1.
        (UNNUMBERED_NOTE, "2", ["proof:unrelated_quote"]),
    ],
)
def test_wrapped_note_over_numbered_rows_is_shared(fake_llm, table, key, errors):
    schema = DocumentClass.model_validate(
        {
            "class": "Register",
            "fields": [
                {
                    "name": "entries",
                    "dtype": "object_list",
                    "fields": [
                        {"name": "key"},
                        {"name": "proof", "verbatim": True, "quote_for": ["key"]},
                    ],
                }
            ],
        }
    )
    reply = {
        "entries": [
            {
                "value": {"key": key, "proof": "Entfernt am 18.09.2018."},
                "evidence_anchor": "Entfernt am",
            }
        ]
    }
    result = extract(fake_llm(lambda *_: reply), schema, register_source(table))
    assert result.fields["entries"].validation_errors == errors


def implied_schema():
    return DocumentClass.model_validate(
        {
            "class": "Register",
            "fields": [
                {
                    "name": "entries",
                    "dtype": "object_list",
                    "fields": [
                        {"name": "key"},
                        {
                            "name": "status",
                            "enum": ["active", "cancelled"],
                            "implied_by": {
                                "cancelled": {
                                    "marks": ["underline", "cross"],
                                    "quote": "(?i)entfernt",
                                }
                            },
                        },
                        {"name": "note", "verbatim": True},
                    ],
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "row,status,note,errors",
    [
        # The undetected cross: a removal note, but the model says active.
        ("| 1 | Transport | Entfernt |", "active", "Entfernt", True),
        ("| 1 | Transport [crossed out] | |", "active", None, True),
        # Cancelled with nothing in the source to support it.
        ("| 1 | Transport | Erfasst |", "cancelled", "Erfasst", True),
        ("| 1 | Transport [underlined] | |", "cancelled", None, False),
        ("| 1 | Transport | Entfernt |", "cancelled", "Entfernt", False),
        ("| 1 | Transport | Erfasst |", "active", "Erfasst", False),
        # A mark the schema does not list says nothing about the value.
        ("| 1 | Transport [struck through] | |", "active", None, False),
    ],
)
def test_implied_value_is_compared_with_the_source(fake_llm, row, status, note, errors):
    reply = {
        "entries": [
            {
                "value": {"key": "1", "status": status, "note": note},
                "evidence_anchor": "Transport",
            }
        ]
    }
    source = register_source(f"{row}\n| 2 | Wartung [underlined] | Entfernt |")
    result = extract(fake_llm(lambda *_: reply), implied_schema(), source)
    expected = ["status:conflicts_with_source"] if errors else []
    assert result.fields["entries"].validation_errors == expected
    assert result.review_reasons == (["invalid:entries"] if errors else [])
