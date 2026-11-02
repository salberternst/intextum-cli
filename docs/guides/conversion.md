# Document conversion

## Supported files

- **Docling formats:** PDF and scans (`png jpg tif bmp webp`), `docx xlsx pptx`,
  OpenDocument (`odt ods odp`), `html mhtml`, email (`eml msg`), `epub`,
  `md csv adoc tex vtt`.
- **Plain text:** `txt json xml log`.

## Empty and legacy files

- **Empty files** (0 bytes) are reported as such.
- **Legacy formats** (`doc rtf xls ppt`): as in the
  [Docling docs](https://docling-project.github.io/docling/usage/supported_formats/),
  these require LibreOffice (`brew install --cask libreoffice`).

## Inspecting OCR

Inspect conversion before extracting:

```bash
intextum convert "inbox/register.pdf"
```

If recognition is incomplete, try full-page OCR and an explicitly selected
engine and language, and use the same options on `extract` (or put them in the
folder's `.env`):

```bash
intextum convert "inbox/register.pdf" --force-ocr --ocr-engine tesseract --ocr-language deu
```

`tesseract` selects Docling's Tesseract CLI engine. Tesseract must be installed
and the requested language must appear in `tesseract --list-langs`.

`ocrmac` selects Docling's Apple Vision engine, which runs on macOS only. Install
it with `pip install "intextum-cli[ocrmac]"` and name languages as macOS reports
them, for example `--ocr-engine ocrmac --ocr-language de-DE`.
`--ocr-language` can be repeated, for example `--ocr-language deu --ocr-language eng`;
codes follow the selected engine. Without these options, Docling chooses its OCR
engine and default languages.

Engine, language, table mode, and mark-detection changes invalidate conversion
and extraction caches. Viewer re-extraction and document-view rebuilds retain
these settings.

## Table modes

`--table-mode` is available on `convert` and `extract`:

| Mode | Behavior |
| --- | --- |
| `ruled` (default) | Use Docling's tables and reconstruct large forms with clear black rules from the page image and positioned text. |
| `docling` | Keep Docling's tables, filled with the PDF's own text. |
| `predicted` | Fill Docling's table cells from its own cell prediction, which can keep scanned entries and text spanning several columns apart. |

Reconstruction keeps adjacent columns separate even when the PDF originally
grouped their text together. Red cancellation lines do not count as table rules.
Original page images remain available for review.

Set `INTEXTUM_TABLE_MODE` in the folder's `.env` to use the same mode across
conversion and extraction.

## Detecting drawn marks

`--detect-marks` tags text inside large ruled forms that a line underlines,
strikes through, or crosses: `[underlined]`, `[struck through]`, `[crossed out]`.
Lines are found in the page image regardless of colour and, for PDFs, in drawn
vector paths. Lines in a scanned page image only tag scanned text, not digital
text placed over the scan later; drawn PDF lines tag both. Headers above the
form's header rule and pages without a ruled grid are left alone.

The tags describe what is drawn; [schema rules](schemas.md#source-consistency-rules)
decide what a mark means. Detection is off by default. Set
`INTEXTUM_DETECT_MARKS=true` in `.env` or pass `--detect-marks`; use
`--no-detect-marks` to override an enabled setting.

Marks outside ruled forms, faint lines, and lines that merely pass through a later
entry still need visual review. Printed row rules are not treated as underlines,
so a cancellation line drawn on a rule also goes undetected.

## Registers and evidence

For registers with historical entries, combine `source_pages_matching` with a
required `verbatim` status quote that uses `quote_for`: each entry list then reads
only its own section, and a status needs a literal quote that names the affected
entry. When the model cannot justify a status, a missing quote flags the entry
for review. Extraction receives text: with `--detect-marks`, lines drawn over
entries in ruled forms reach the model as tags, so schema instructions can say
what a mark means in that register, e.g. that underlined entries are cancelled.

See [quoted evidence](schemas.md#quoted-evidence) and
[source consistency rules](schemas.md#source-consistency-rules) for schema options.

## Conversion fallbacks

Conversion uses direct readers and OCR fallbacks when Docling cannot read usable
text, and recovers recognized text omitted during layout assembly.

- CSV files Docling cannot read, e.g. with Windows encoding, are read directly:
  UTF-8 or Windows-1252, with Latin-1 as a final fallback. The delimiter is
  detected automatically.
- Outlook `.msg` files that Docling mistakes for Excel files are read directly
  (subject, sender, recipients, date, body). Attachment names are listed, but
  their content is not converted.
- PDFs and images with fewer than 20 letters of text, such as scans without OCR
  text or broken font layers, are converted again with full-page OCR.
- Recognized text omitted by Docling's picture or table assembly is retained
  with its original page and position. This also helps mixed scanned/digital
  PDFs whose text layer covers only newer entries. Text inside picture elements
  and headers/footers is included, so dates and references remain available;
  other layers, such as hidden text and speaker notes, are not. Headers and
  footers alone do not count as text when deciding on the OCR fallback.
