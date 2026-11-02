# Workspace and exports

## What the database contains

`extract` writes one SQLite database, by default `<input>-results.sqlite`.
Pass `-o results.sqlite` to choose its location. It contains extraction results,
correction history, schema snapshots, converted text, complete Docling documents,
images, and cached classifications. Original documents and YAML
configuration stay outside the database.

Existing JSON result folders and `.intextum` caches are not imported.
Unprocessed groups and their corrections remain in the database across reruns;
results are not automatically pruned.

## Processing status and review state

Three properties describe different aspects of a result:

| Property | Meaning |
| --- | --- |
| `status` | Processing outcome: `completed`, `unclassified`, `duplicate`, or `failed`. |
| `needs_review` | Whether the current result has unresolved review work. |
| `review.state` | Human review decision: `open` or `reviewed`. CSV calls this `review_state`. |

A completed result can need review because a required value is missing. A result
with no automatic review flags can still have `review.state: open` until someone
marks it reviewed. Marking reviewed accepts the remaining review items and clears
`needs_review` while retaining `review_reasons`, evidence, and processing warnings.
See [Complete review](../guides/review.md#complete-review) for the workflow.

## Export results

Export the current corrected results explicitly:

```bash
intextum export results.sqlite -o exports                  # JSON and CSV
intextum export results.sqlite -o exports --format json    # JSON only
intextum export results.sqlite -o exports --format csv     # CSV only
intextum export results.sqlite -o exports --state reviewed # reviewed results only
```

`--state reviewed` exports only results marked reviewed in the viewer, and
`--state open` only those still awaiting review. A filtered export removes JSON
files of excluded results left by an earlier JSON export. With `--format csv`,
existing JSON files are left untouched.

## JSON format

Exports use one consistent database snapshot. JSON output has one
`exports/<result-name>.json` per group. Filenames use the workspace's stable,
filesystem-safe names: for example, group `acme/contract.pdf` becomes
`acme_contract.pdf.json`. Name collisions receive numeric suffixes; the original
group name remains in the JSON.

The following is an abbreviated result:

```json
{
  "group": "order-4711",
  "files": ["order-4711/anschreiben.docx", "order-4711/positionen.xlsx"],
  "status": "completed",
  "needs_review": false,
  "review_reasons": [],
  "class": {"name": "Purchase order", "source": "llm", "reason": "…"},
  "data": {"order_number": "B-4711", "positions": [{"article_number": "HX-200", "quantity": 4}]},
  "fields": {
    "order_number": {"value": "B-4711", "evidence": [
      {"file": "order-4711/anschreiben.docx", "page": null, "snippet": "Bestellung Nr. B-4711…"}]},
    "positions": {
      "value": [{"article_number": "HX-200", "quantity": 4}],
      "item_evidence": [[{"file": "order-4711/positionen.xlsx", "page": null, "snippet": "HX-200 | 4"}]]
    }
  },
  "warnings": []
}
```

`fields` keeps evidence and validation details; `data` provides the current
corrected values. Evidence for a [`from_path`](../guides/schemas.md#values-from-the-file-path)
field has `"kind": "path"`, and its `snippet` is the text matched in the path. The `review` object records the review decision and history,
and corrections appear under `edits`. See
[Correct fields and tables](../guides/review.md#correct-fields-and-tables).

Common `review_reasons` include:

| Reason | Review concern |
| --- | --- |
| `missing_required:<field>` | A required value is empty. |
| `invalid:<field>` | A value failed type or schema validation. |
| `no_evidence:<field>` | An extracted value lacks source evidence. |
| `no_matching_source_pages:<field>` | The field's page selector matched nothing. |
| `external_source_uncertain:<field>` | Attachment ranking is inconclusive. |
| `external_source_not_found:<field>` | No attachment qualifies. |
| `source_truncated:<file>` | Source text exceeded the extraction budget. |
| `conversion_failed:<file>` | A source file could not be converted. |
| `edit_outdated:<field>` | The model answer changed since the correction. |
| `unverified:<field>` | The decision model scored the value below the threshold. |
| `class_doubtful` | The verifier doubts the current automatic class. |
| `llm_invalid_json` | A model reply could not be read as valid JSON. |
| `unclassified` | No document class was selected. |

## CSV format

CSV exports include two kinds of files:

- `_summary.csv` lists every exported group.
- `<Class>.csv` uses a filesystem-safe class name and has one row per completed
  extraction group of that class; classification-only results are omitted. Repeated
  fields are stored as JSON. Columns include the union of fields from the stored
  schema versions when only part of a workspace has been reprocessed.

Both include a `review_state` column (`reviewed` or `open`).

## Caching and incremental runs

- **Converted text and structured documents** live in the SQLite database.
  Conversion keys include source content and extension, Docling and Docling Core
  versions, OCR mode, image settings, and the conversion-format version. Renamed
  files with the same extension reuse their conversion. Text, document JSON,
  source-to-element indexes, and PNG assets are published together. Plain-text
  and CSV/MSG fallback readers also produce a simple document view. If preparing
  a structured view fails, usable extraction text is retained with a warning.
- **Evidence stays pinned to its source version.** Each result references the
  exact stored conversions used for its documents and external attachments.
  Changes to originals do not silently replace the content shown beside a result.
- **Unchanged groups are skipped.** A stored result fingerprint covers the group's
  files and content, class definitions, model and endpoint, extraction mode,
  thinking mode, resolved context length, character/retry/token limits, OCR
  settings, conversion versions, and tool code.
  External fields also include neighboring files and `sources.yaml` overrides.
  Failed groups are retried; `--force` processes unchanged groups too.
- **Classifications** are cached in the same database, keyed by the text the model
  sees, class names/descriptions/aliases, model, endpoint, thinking mode, resolved
  context length, output token limit, and classification/client code. Changes to
  extraction fields alone retain classification cache entries.
- **Corrections survive reruns.** Result commits apply the latest stored edits,
  including corrections made while a model call was running. Each group commits
  independently, so completed groups survive an interrupted run.

Recognition and legacy Office conversion use temporary working storage;
extraction does not create a persistent `.intextum` cache directory.

## Back up or move a workspace

Close extraction and viewer processes cleanly before copying the database file.
SQLite uses WAL mode and may create `-wal` and `-shm` companions while it is open.
Those files can contain committed changes; copying only an open database is not a
reliable backup. After clean shutdown, the database is a portable workspace for
cached review, editing, and exports. A live-backup command is not provided.
