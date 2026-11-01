# Values from attachments

Some documents keep part of their data elsewhere: a contract lists its items in
an Excel table "in Annex 1", an invoice has its line items in a CSV.
Mark such fields with `external`:

```yaml
classes:
  - class: Invoice
    description: An invoice for goods or services
    fields:
      - name: line_items
        dtype: object_list
        external:
          classes: [Item list]
          when: auto
        fields:
          - {name: description, dtype: str, description: Item description}
          - {name: quantity, dtype: int, description: Ordered quantity}
  - class: Item list
    description: A table listing invoiced items and quantities
```

Every class named in `external.classes` must be present in the loaded schemas.
A single YAML file can hold multiple definitions under `classes:`, as above;
separate files in a schema directory work too. Omit `external.classes` to
consider any other document class.

## Selecting a source

When `extract` processes the document, it first extracts the field from the document
itself. The model also reports any sentence pointing to an attachment for it, such as
"see the table in Annex 1". Then:

- **When a separate file is used.** With `when: auto`, a separate file is used if
  the field is empty or the document refers to an attachment. With `missing`, only
  if the field is empty. With `always`, every time.
- **Which files are candidates.** Every other file in the same
  [source scope](grouping.md#source-scopes), without duplicates. They are limited
  to `classes` if given (classification is cached)
  and never include files of the document's own class.
- **How the best file is picked.** Candidates are ranked by values already
  extracted from the document that appear in the file (numbers compared across
  `753,24`/`753.24`), shared reference numbers and dates, file dates, file names,
  whether the file is the kind of attachment the document refers to (table, map),
  and words like "annex", "attachment", "Anlage" or "Anhang" in the name. A draft
  matched with a final version, or an archived file with a current one, is penalised.
- **What happens next.** The best file is used if it scores at least 0.35. The
  field is then extracted from that file only, with the document's other values
  as context.

## Evidence and review flags

The result shows where the values came from. If the document had its own values,
they are kept as `document_value`. The following is an abbreviated field record:

```json
{
  "line_items": {
    "value": [{"description": "Harbor equipment", "quantity": 4}],
    "item_evidence": [[{"file": "acme/items.xlsx", "snippet": "Harbor equipment | 4"}]],
    "source": {
      "files": ["acme/items.xlsx"],
      "score": 0.6,
      "reasons": ["contains 753.24, harbor", "document refers to a table"],
      "runner_up": {"file": "acme/items draft.xlsx", "score": 0.38, "reasons": []}
    },
    "attachment_reference": {
      "quote": "see the table in Annex 1",
      "evidence": [{"file": "acme/contract.pdf", "page": 1, "snippet": "see the table in Annex 1"}]
    }
  }
}
```

The group is flagged `external_source_uncertain:<field>` when the best score is
below 0.4 or less than 0.15 ahead of the runner-up. It is flagged
`external_source_not_found:<field>` when no file qualifies. `_summary.csv` has a
`sources` column like `line_items ← acme/items.xlsx (0.60)`.

## Overriding the source

Put a `sources.yaml` in the input folder. Keys are group
names, which with `--group-by file` are the document's path:

```yaml
sources:
  acme/contract_2026.pdf:
    line_items: acme/items_2026.xlsx                     # use this file
  acme/contract_2015.doc:
    line_items: [acme/items_a.xlsx, acme/items_b.xlsx]   # combine
  acme/contract_2009.doc:
    line_items: none                                     # never look outside
```

Listed files are used as-is, without ranking. Changing `sources.yaml` or any file
in the scope reprocesses the affected groups on the next run.

Check your schemas with `intextum check-schemas schemas/`.
