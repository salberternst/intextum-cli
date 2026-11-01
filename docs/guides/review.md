# Reviewing results

## Open a workspace

```bash
intextum view results.sqlite                       # http://127.0.0.1:8765
intextum view results.sqlite --input ./documents    # locate moved originals
```

`view` starts a local NiceGUI review workspace. Install it with
`python -m pip install -e ".[ui]"`; no frontend build step is needed. It binds to
`127.0.0.1` by default and reads and writes local files without authentication.
The database is sufficient for reviewing cached documents and correcting fields,
even when the original folder and schema files are unavailable. Original downloads,
desktop opening, and rebuilding need the source folder. The recorded input path is
used if it still exists; `--input` overrides it.

## Navigate documents

The sidebar lists processed source documents directly, with filters for "needs
review", "reviewed", "edited" and "failed", and document and review counts. Click
a document to open it; search matches filenames, paths, classes, and extraction
group names.

A colored dot marks each document's status. Documents processed together are
marked "shared": they use the same extracted fields and corrections, and a file
picker above the preview switches between them. Failed results remain accessible
even without source files. Drag the dividers to resize the list, preview, and
fields. Use Alt + Up/Down or the arrows in the header to move between the
visible documents. Keyboard shortcuts work everywhere except after clicking into
the rendered document text, which runs in a sandboxed frame; click outside it first.

The fields panel starts with the result's review items and processing warnings
and ends with **Mark reviewed** (or **Reopen review**). Less frequent actions are
in the header's **⋮** menu: **Change class…**, **Re-extract group**, **Review
history…**, and **Download result JSON**. In the document toolbar, the open
button (↗) opens the original in its default application; the download button
saves a copy.

## Document views and evidence

The **Document** view displays recognized content. Choose a representation:

| View | Use it to inspect |
| --- | --- |
| **Content** | Readable headings, paragraphs, lists, tables, and pictures. |
| **Elements** | The recognized document's structured elements. |
| **Pages** | Source page images and bounding boxes, when conversion supplied them. |
| **Source text** | The exact cached text used by extraction. |

Native Office documents can use **Content** and **Elements** without rendered
pages. **Pages** covers PDFs and scans; use the open button (↗) to view an
original in its desktop application. Office documents are not automatically
converted to PDF. Legacy Office inputs still require LibreOffice.

Field cards show values, review flags, validation errors, and evidence snippets.
Click a snippet to select its paragraph or whole table; the preview switches
files when needed. **Show full document** clears the selection. Individual
cells are not selected separately. When a quote cannot be matched unambiguously
to a document element, the viewer opens **Source text** instead.

### Rebuild a document view

Document views are stored during conversion. Choose **Build document view** or
**Rebuild document view** if a view or image is missing or damaged. This runs
recognition and may download recognition models on first use. Extraction text,
results, and corrections stay intact; the configured LLM is not called.

The original must match the content used by extraction. A changed original
requires another extraction. Opening a result reads only stored data, including
when a view is damaged.

## Correct fields and tables

**Edit** opens a correction dialog with controls for text, numbers, dates,
booleans, currencies, and enum choices. **Edit table** lets you change cells,
add rows, or remove selected rows for repeated fields. Click a cell, apply its
edit, then choose **Save correction** to save the table. Invalid values are
rejected before writing. Cancel leaves the stored result unchanged.

Editors use each result's embedded schema snapshot for precise types, including
when values are empty. `view --schemas` overrides those definitions for the current
review session without changing the stored snapshots.

Corrections are stored separately from model output and applied to both the field
and its `data` value when reading or exporting. Download the current JSON from the
header's **⋮** menu, or run `export` for updated JSON and CSV files. Every correction
appears in the exported `edits` history:

```json
{
  "edits": [{
    "at": "2026-09-16T09:26:40+00:00",
    "field": "delivery_date",
    "value": "2026-10-15",
    "previous": "2026-10-01",
    "note": "verified against the order confirmation"
  }]
}
```

A correction replaces the field's `value`, keeps the model's answer in
`extracted_value`, marks the field `"edited": true` and settles review reasons
about that field. **Corrections survive a rerun within the same class selection:**
every run re-applies the newest edit per field. If the model's answer changed
since the correction was made, the field gets `edit_outdated:<field>` so the
difference is not hidden.

## Complete review

After checking the fields, choose **Mark reviewed** (or press Enter in the
optional note field, or Alt + Enter) to finish review. This accepts any remaining
review items without removing processing warnings or evidence, and opens the next
document in the list that still needs review, so you can work through the queue
without leaving the keyboard. The queue follows the current search and filter,
skips other documents of a shared result once it is reviewed, and wraps around.

**N to review →** in the top bar counts results (a shared result counts once) and
jumps to the next one. **Reopen review** returns a result to the queue. For
documents outside all available classes, choose **None of these classes** under
**Change class…**; saving it completes review
immediately without a model call, clears the current class and fields, and moves
on to the next document.

Failed results require another extraction before they can be marked reviewed.
The JSON export includes the review state, timestamp, note, and decision history.
A new extraction or field correction reopens review; an incremental skip keeps
the review decision. Stale browser decisions are rejected with a refresh message.

## Change classes and re-extract

For unclassified or wrongly classified documents, choose **Change class…**, select
the correct class, and **Save class**. Then click **Re-extract** in the notice
above the fields to replace them using that schema. This processes the selected
extraction group; documents marked "shared" share the class, fields, and review
decision.

Other groups' results remain unchanged. Duplicate detection and external fields
use the recorded input scope. Re-extraction needs the original files in that
scope and a configured model endpoint. It runs only when explicitly requested;
opening documents and refreshing the viewer only read stored data.

### Re-extract a filtered list

To re-extract many results at once, narrow the list with search and the filter,
then choose **Re-extract this list…** in the **⋮** menu next to the filter. The
dialog shows how many results that covers and skips reviewed results unless you
clear **Skip reviewed results**. All selected groups run in one pass with a
progress counter, honoring any viewer class choice; re-extraction reopens their
review. The counter counts extraction groups; verification runs afterward when
configured.

### Class overrides

Class choices persist in the workspace and take precedence over automatic
classification, `groups.yaml`, and `--class` on subsequent CLI runs. Choose
**Automatic classification** to remove a viewer override and use the CLI/group
configuration again. Previous corrections remain in JSON history and in
**Review history…**, but do not apply to a newly selected class,
including when switching back to an earlier class.

## Re-extraction settings

**Re-extract group** uses the processing scope and settings recorded by the last
full `intextum extract` run. The viewer uses the embedded schemas (or
`view --schemas`) and recorded extraction options;
current environment/nearest `.env` model and endpoint settings take precedence.
API keys are read from configuration and never stored in the workspace.

See the [view command](../reference/cli.md#view) for server options and the
[workspace reference](../reference/workspace.md) for exports and portable backups.
