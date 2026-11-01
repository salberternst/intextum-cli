from intextum_cli.convert import ConvertedFile
from intextum_cli.extract import extract
from intextum_cli.extraction_prompt import build_prompt, field_batches, response_schema
from intextum_cli.schema import DocumentClass, SchemaField
from intextum_cli.source import build_source

ORDER = DocumentClass.model_validate(
    {
        "class": "Order",
        "description": "Purchase order letter with a positions table",
        "fields": [
            {"name": "order_number", "required": True, "description": "Order id"},
            {"name": "order_date", "dtype": "date", "description": "Date"},
            {"name": "status", "enum": ["open", "closed"], "description": "Status"},
            {"name": "total", "dtype": "currency", "description": "Total"},
            {
                "name": "positions",
                "dtype": "object_list",
                "description": "Ordered items",
                "fields": [
                    {"name": "item", "description": "Item"},
                    {"name": "quantity", "dtype": "int", "description": "Qty"},
                ],
            },
            {"name": "notes", "dtype": "list", "description": "Notes"},
        ],
    }
)

SOURCE = build_source(
    [
        ConvertedFile(
            "letter.pdf",
            ["Order No. A-17 dated 03.04.2026", "Total: 1.250,00 EUR"],
            paged=True,
        ),
        ConvertedFile(
            "positions.xlsx",
            ["| Item | Qty |\n| Bolt | 10 |\n| Nut | 20 |\n| Bolt | 5 |"],
        ),
    ],
    max_chars=10_000,
)


def reply_for(name, user, schema):
    fields = set(schema["properties"])
    if "positions" in fields:
        return {
            "positions": [
                {
                    "value": {"item": "Bolt", "quantity": 10},
                    "evidence_anchor": "Bolt | 10",
                },
                {"value": {"item": "Nut", "quantity": "20"}, "evidence_anchor": "Nut"},
                {"value": {"item": "Bolt", "quantity": 5}, "evidence_anchor": "Bolt"},
            ]
        }
    if "notes" in fields:
        return {"notes": []}
    return {
        "order_number": {"value": "A-17", "evidence_anchor": "Order No. A-17"},
        "order_date": {"value": "03.04.2026", "evidence_anchor": "dated 03.04.2026"},
        "status": {"value": "pending", "evidence_anchor": "invented anchor"},
        "total": {
            "value": {"amount": 1250.0, "currency": "EUR"},
            "evidence_anchor": "Total: 1.250,00 EUR",
        },
    }


def test_extracts_across_files_with_evidence(fake_llm):
    llm = fake_llm(reply_for)
    result = extract(llm, ORDER, SOURCE)

    assert len(llm.calls) == 3  # scalars, positions, notes
    assert "=== FILE: positions.xlsx ===" in llm.calls[0]["user"]
    assert result.data == {
        "order_number": "A-17",
        "order_date": "2026-04-03",
        "status": "pending",
        "total": {"amount": 1250.0, "currency": "EUR"},
        "positions": [
            {"item": "Bolt", "quantity": 10},
            {"item": "Nut", "quantity": 20},
            {"item": "Bolt", "quantity": 5},
        ],
        "notes": [],
    }
    assert result.fields["order_number"].evidence[0]["file"] == "letter.pdf"
    assert result.fields["total"].evidence[0]["page"] == 2
    items = result.fields["positions"].item_evidence
    assert [ev[0]["file"] for ev in items] == ["positions.xlsx"] * 3
    # The second "Bolt" is grounded on the later row, not the first one again.
    assert items[2][0]["snippet"].startswith("Bolt | 5")
    assert result.fields["status"].validation_errors == ["not_in_enum"]
    assert result.review_reasons == ["invalid:status", "no_evidence:status"]


def test_no_matching_pages_requires_review_without_calling_model(fake_llm):
    schema = DocumentClass(
        name="Register",
        fields=[
            SchemaField(
                name="custodians",
                dtype="object_list",
                required=True,
                source_pages_matching="Betreuung",
                fields=[{"name": "name"}],
            )
        ],
    )
    source = build_source(
        [ConvertedFile("register.pdf", ["Dritte Abteilung"], paged=True)],
        max_chars=1000,
    )
    llm = fake_llm(
        lambda *_: (_ for _ in ()).throw(AssertionError("wrong section sent to model"))
    )
    result = extract(llm, schema, source)
    assert result.data == {"custodians": []}
    assert result.llm_calls == 0
    assert result.review_reasons == [
        "no_matching_source_pages:custodians",
        "missing_required:custodians",
    ]


def test_status_quote_does_not_replace_missing_item_evidence(fake_llm):
    schema = DocumentClass(
        name="Register",
        fields=[
            SchemaField(
                name="conditions",
                dtype="object_list",
                fields=[
                    {"name": "description"},
                    {"name": "quote", "verbatim": True},
                ],
            )
        ],
    )
    source = build_source(
        [ConvertedFile("register.pdf", ["Entry 1 removed."], paged=True)],
        max_chars=1000,
    )
    llm = fake_llm(
        lambda *_: {
            "conditions": [
                {
                    "value": {
                        "description": "Invented condition",
                        "quote": "Entry 1 removed.",
                    },
                    "evidence_anchor": "not in document",
                }
            ]
        }
    )
    result = extract(llm, schema, source)
    assert result.review_reasons == ["no_evidence:conditions"]
    assert result.fields["conditions"].item_evidence[0][0]["page"] == 1


def test_retries_missing_required_fields_only(fake_llm):
    attempts = []

    def handler(name, user, schema):
        if "order_number" not in schema["properties"]:
            return {key: [] for key in schema["properties"]}
        attempts.append(user)
        if len(attempts) == 1:
            return {
                k: {"value": None, "evidence_anchor": None}
                for k in schema["properties"]
            }
        return {"order_number": {"value": "A-17", "evidence_anchor": "A-17"}}

    llm = fake_llm(handler)
    result = extract(llm, ORDER, SOURCE, max_retries=1)
    assert len(llm.calls) == 4  # 3 batches + 1 retry of the scalar batch
    assert "RETRY NOTE" in attempts[1] and "order_number" in attempts[1]
    assert result.data["order_number"] == "A-17"
    assert result.review_reasons == []


def test_invalid_json_and_missing_required_need_review(fake_llm):
    llm = fake_llm(lambda name, user, schema: "sorry, no JSON here")
    result = extract(llm, ORDER, SOURCE, max_retries=0)
    assert result.review_reasons == [
        "llm_invalid_json",
        "missing_required:order_number",
    ]
    assert result.data["positions"] == [] and result.data["order_number"] is None


def test_response_schema_is_strict_and_nullable():
    schema = response_schema(ORDER.fields)
    assert schema["required"] == [f.name for f in ORDER.fields]
    assert schema["additionalProperties"] is False
    status = schema["properties"]["status"]["properties"]["value"]
    assert status["enum"] == ["open", "closed", None]
    positions = schema["properties"]["positions"]["items"]["properties"]["value"]
    assert positions["required"] == ["item", "quantity"]
    assert schema["properties"]["notes"] == {
        "type": "array",
        "items": {"type": "string"},
    }


def test_prompt_includes_instructions_and_only_relevant_scene_extractions():
    order = DocumentClass.model_validate(
        {
            **ORDER.model_dump(by_alias=True),
            "instructions": "Datumswerte im Format TT/MM/JJJJ.",
            "scenes": [
                {
                    "text": "Order No. Z-1, 2 x Bolt",
                    "extractions": [
                        {
                            "field": "order_number",
                            "extraction_text": "Order No. Z-1",
                            "value": "Z-1",
                        },
                        {
                            "field": "positions",
                            "extraction_text": "2 x Bolt",
                            "value": {"item": "Bolt", "quantity": 2},
                        },
                        {"field": "notes", "extraction_text": "", "value": None},
                    ],
                }
            ],
        }
    )
    scalars, positions, notes = field_batches(order.fields)
    scalar_prompt = build_prompt(order, scalars, SOURCE)
    assert "CLASS INSTRUCTIONS:\nDatumswerte im Format TT/MM/JJJJ." in scalar_prompt
    assert '"source_excerpt": "Order No. Z-1, 2 x Bolt"' in scalar_prompt
    assert "The examples show the output format only." in scalar_prompt
    assert '"value": "Z-1"' in scalar_prompt and '"quantity": 2' not in scalar_prompt
    positions_prompt = build_prompt(order, positions, SOURCE)
    assert (
        '"quantity": 2' in positions_prompt and '"value": "Z-1"' not in positions_prompt
    )
    assert "EXAMPLES:" not in build_prompt(order, notes, SOURCE)
    assert "output format only" not in build_prompt(order, notes, SOURCE)


def test_empty_values_are_treated_as_missing():
    from intextum_cli.extract import records_from_reply
    from intextum_cli.schema import SchemaField

    items = SchemaField.model_validate(
        {
            "name": "line_items",
            "dtype": "object_list",
            "fields": [
                {"name": "code", "required": True},
                {"name": "variant", "empty_values": ["0", "0000"]},
            ],
        }
    )
    records = records_from_reply(
        items,
        [
            {"value": {"code": "46", "variant": "0"}, "evidence_anchor": "46"},
            {"value": {"code": "50", "variant": "1"}, "evidence_anchor": "50"},
            {"value": {"code": "51", "variant": "0000"}, "evidence_anchor": "51"},
        ],
    )
    assert [r["value"] for r in records] == [
        {"code": "46"},
        {"code": "50", "variant": "1"},
        {"code": "51"},
    ]
    number = SchemaField.model_validate(
        {"name": "Nr", "dtype": "int", "empty_values": ["0"]}
    )
    assert records_from_reply(number, {"value": 0, "evidence_anchor": None}) == []


def test_max_chars_applies_to_each_calls_selected_pages(fake_llm):
    schema = DocumentClass(
        name="Register",
        fields=[
            SchemaField(
                name="assets",
                dtype="object_list",
                source_pages_matching="Assets",
                fields=[{"name": "code"}],
            ),
            SchemaField(
                name="conditions",
                dtype="object_list",
                source_pages_matching="Conditions",
                fields=[{"name": "description"}],
            ),
        ],
    )
    pages = [
        "Assets\n" + "Code 10/1 widget. " * 40,
        "Conditions\nHandling note for Example Ltd.",
    ]
    source = build_source(
        [ConvertedFile("register.pdf", pages, paged=True)], max_chars=None
    )
    prompts = {}

    def reply(name, user, schema):
        field = next(iter(schema["properties"]))
        prompts[field] = user.split("SOURCE TEXT:", 1)[1]
        if field == "conditions":
            value, anchor = (
                {"description": "Handling note"},
                "Handling note for Example Ltd.",
            )
        else:
            value, anchor = {"code": "10/1"}, "Code 10/1"
        return {field: [{"value": value, "evidence_anchor": anchor}]}

    result = extract(fake_llm(reply), schema, source, max_chars=200)
    # The long asset page no longer crowds out the later conditions section.
    assert "Handling note for Example Ltd." in prompts["conditions"]
    assert "Code 10/1" not in prompts["conditions"]
    assert prompts["assets"].count("Code 10/1") < 40
    assert result.review_reasons == ["source_truncated:register.pdf"]
    assert result.fields["conditions"].item_evidence[0][0]["page"] == 2


def test_fitting_source_keeps_short_files_whole_and_marks_truncation():
    from intextum_cli.source import fit_source

    source = build_source(
        [
            ConvertedFile("long.pdf", ["a" * 500, "b" * 500], paged=True),
            ConvertedFile("short.txt", ["Short note"]),
        ],
        max_chars=None,
    )
    assert source.truncated_files == []
    fitted = fit_source(source, 300)
    assert fitted.truncated_files == ["long.pdf"]
    assert "Short note" in fitted.text
    assert [segment.page for segment in fitted.segments] == [1, None]
    assert fit_source(source, 10_000) is source


def test_float_that_may_be_a_decimal_is_flagged_for_review(fake_llm):
    schema = DocumentClass.model_validate(
        {
            "class": "Sheet",
            "fields": [
                {"name": "rate", "dtype": "float"},
                {"name": "count", "dtype": "int"},
                {
                    "name": "rows",
                    "dtype": "object_list",
                    "fields": [{"name": "weight", "dtype": "float"}],
                },
            ],
        }
    )
    source = build_source(
        [ConvertedFile("sheet.txt", ["Rate 2.125, count 30.000, weight 1,250"])],
        max_chars=None,
    )

    def reply(name, user, schema):
        if "rows" in schema["properties"]:
            return {
                "rows": [{"value": {"weight": "1,250"}, "evidence_anchor": "weight"}]
            }
        return {
            "rate": {"value": "2.125", "evidence_anchor": "Rate"},
            "count": {"value": "30.000", "evidence_anchor": "count"},
        }

    result = extract(fake_llm(reply), schema, source)
    assert result.fields["rate"].validation_errors == ["ambiguous_number"]
    assert result.fields["rows"].validation_errors == ["weight:ambiguous_number"]
    assert result.fields["count"].validation_errors == []
    assert set(result.review_reasons) == {"invalid:rate", "invalid:rows"}
