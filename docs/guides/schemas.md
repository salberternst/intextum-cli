# Writing schemas

Create one YAML file per document class. A class with no `fields` is used only
for classification. Pass a YAML file or a directory to `--schemas`.

## A basic schema

```yaml
class: Purchase order
description: A customer orders goods; usually a cover letter plus a positions table
aliases: [Bestellung]
fields:
  - name: order_number
    dtype: str
    required: true
    description: Order number stated by the customer
  - name: positions
    dtype: object_list
    description: Ordered items from the positions table
    fields:
      - {name: article_number, dtype: str, description: Article number}
      - {name: quantity, dtype: int, description: Ordered quantity}
```

## Field options

| `dtype` | Value |
| --- | --- |
| `str` | Text; the default type. |
| `int` | Integer. |
| `float` | Number. |
| `bool` | `true` or `false`. |
| `date` | Date normalized to `YYYY-MM-DD`. |
| `currency` | Object with `amount` and `currency`, such as `{"amount": 19.5, "currency": "EUR"}`. |
| `list` | Repeated strings. |
| `object_list` | Repeated objects with child `fields`. |

Set `required: true` when an empty value should trigger review. Child fields
support all types except `object_list`; repeated objects cannot be nested.
See [Extraction and model calls](../reference/extraction.md#processing-steps)
for number, date, and currency coercion.

- `enum: [...]` limits `str` and `list` values to a fixed set.
- `empty_values: [...]` lists values that mean "no value" and are dropped after
  extraction, e.g. `empty_values: ["0"]` for a column that tables fill with 0 when
  there is no value. It works on fields and on child fields.
- `examples: [{text, value, extraction_text}]` adds few-shot examples.

## Selecting source pages

`source_pages_matching: 'regular expression'` limits a field to matching source
pages (or the matching file for unpaged text). Only those pages are sent to the
extraction model and used to locate that field's evidence. A field with no
matching pages is flagged `no_matching_source_pages:<field>` for review.

## Quoted evidence

Child fields inside an `object_list` can set `verbatim: true` on a `str` field,
for example a status justification. Its value must occur in the selected source
pages; paraphrased or unsupported quotes produce a `not_in_source` validation
error. Valid quotes add their own evidence, including a separate page when a
later note supports an earlier entry. Quotes may continue down one table
column across wrapped rows; separate tables and pages are kept apart. A quote's
presence alone does not prove that the claim made from it is correct.

A verbatim child can add `quote_for: [entry_number, name]`. The quote or its
immediate source-row context must contain one of those sibling identifiers;
a quote about another entry produces an `unrelated_quote` validation error.
A note that wraps over table rows numbered one by one counts for all of them,
and for numbered rows right below it where its column is empty.
Every occurrence of a repeated quote is checked, so identical notes on several
entries stay attributed to the right one. Identifiers must be `str`, `int` or
`date` fields; numbers ignore leading zeros and dates match common source
formats such as `07.04.2016`. Mark tags from `--detect-marks` are ignored when
matching quotes and anchors; a quote may keep them as proof of a mark.

## Source consistency rules

An enum or `bool` child can add `implied_by` to compare its value with the source:

```yaml
implied_by:
  cancelled:
    marks: [underline, strike, cross]
    quote: '(?i)entfernt'
```

Here, `cancelled` must be an allowed enum value. For a `bool` child, use `true`
or `false` as the key. `marks` looks for those `--detect-marks` tags in the source
row of the entry's evidence anchor and in its verbatim quotes; `quote` is a
pattern for those quotes. Omit `marks` if one marked row does not settle the
value. If a signal is present but the value differs, or the value is set without
any signal, the entry gets a `conflicts_with_source` validation error and goes
to review.

A `str`, `int` or `date` child can add `unique: true`. If two items repeat the
value, the field gets a `duplicate` validation error and goes to review, as when
a number that identifies a row is lost in recognition and the model reuses another.

## Class instructions and scenes

`description` is for classification. Two optional keys help extraction:

```yaml
class: Wartungsvertrag
description: Wartung von Geräten mit Vertragsnummer und Seriennummern
fields:
  - {name: Vertragsnummer, dtype: str}
  - name: Geräte
    dtype: object_list
    fields:
      - {name: Gerät, dtype: str}
      - {name: Seriennummer, dtype: str}
instructions: >-            # rules that apply to all fields of this class
  Nur Angaben übernehmen, die im Dokument stehen; fehlende Werte leer lassen.
scenes:                      # one example passage showing several fields at once
  - text: "Vertragsnummer: WV-2026/0042. Geräte: Kassensystem K3 (Seriennr. 0815) und Bondrucker B2 (Seriennr. 0042)."
    extractions:
      - {field: Vertragsnummer, extraction_text: "Vertragsnummer: WV-2026/0042", value: WV-2026/0042}
      - field: Geräte
        extraction_text: Kassensystem K3 (Seriennr. 0815)
        value: {Gerät: Kassensystem K3, Seriennummer: "0815"}
```

Each extraction call only gets the scene extractions for the fields it asks for.

## Validate schemas

```bash
intextum check-schemas schemas/
```

See the [example schemas](https://github.com/salberternst/intextum-cli/tree/main/examples/schemas)
and the [inventory-register schema](https://github.com/salberternst/intextum-cli/blob/main/corpus/schemas/inventory_register.yaml)
for complete definitions. Use [external fields](attachments.md) when a value
comes from an attachment, and inspect [conversion output](conversion.md) before
refining descriptions or evidence rules.
