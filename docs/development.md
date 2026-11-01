# Development

## Set up and check the code

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,ui,docs]"
python -m pytest
python -m ruff check src tests
python -m ruff format --check src tests
```

GitHub Actions runs these checks with the UI dependencies on Python 3.11 and 3.14,
validates the example and corpus schemas, and checks that rebuilding the pinned
frontend reproduces the shipped bundle and license notices. A separate job builds
the sdist and wheel, installs the wheel with `[ui]` in a fresh environment, and
checks CLI startup, extraction without a model, incremental skips, JSON/CSV
exports, and cached review after the originals are moved. Tests run with model
downloads disabled.

A separate job runs [Gitleaks](https://github.com/gitleaks/gitleaks) against
the available Git history and a tracked-file snapshot, with findings redacted.
Its release version and SHA-256 checksum are pinned in the workflow.

## Installed wheel checks

To run the wheel smoke checks locally, install `build` in your development
environment, run `python -m build`, and install the resulting wheel with `[ui]`
in a fresh virtual environment. Use that environment's Python:

```bash
/path/to/wheel-venv/bin/python -I tests/wheel_smoke.py
```

The `-I` flag isolates imports from the checkout. The smoke script also checks
that the package comes from the selected virtual environment.

## Viewer bundle

The wheel includes the pinned `@docling/docling-components` used by the viewer's
**Elements** view and their license notices. `frontend/package-lock.json` records
the dependency versions. To rebuild after frontend dependency changes:

```bash
cd frontend
npm ci
npm run build
```

Node/npm are build tools only; normal CLI and viewer use requires no Node
process or external CDN.

## Documentation

The documentation uses [MkDocs](https://www.mkdocs.org/), with Markdown sources
in `docs/` and navigation in `mkdocs.yml`. The README provides the quick start;
keep detailed behavior in the relevant guide or reference page.

Install the documentation tooling with `python -m pip install -e ".[docs]"`.
From the repository root:

```bash
python -m mkdocs serve
python -m mkdocs build --strict
```

The preview runs at <http://127.0.0.1:8000> and reloads when source files change.
The build writes static HTML to `site/`, which is ignored by Git. CI builds the
documentation with strict link and navigation validation. Add each new page to
`nav` in `mkdocs.yml` and use relative Markdown links between documentation pages.
Link to repository examples on GitHub so those links also work in the built site.
The source distribution includes `docs/` and `mkdocs.yml`; generated `site/`
output stays outside the package.

For documentation-only changes, run the strict build and check changed content
and links; a full Python test run is not required. Keep command examples aligned
with `intextum --help` and each subcommand's `--help`.

## Test corpus

`corpus/` has a small, fictional German/English corpus with ground truth, for
checking a model or a prompt change:

| Group | Tests |
|---|---|
| `order-2026-0815/` | subfolder group: letter `.docx` + positions `.xlsx` |
| `order-B-2231` | `groups.yaml` glob: letter `.pdf` + positions `.csv` |
| `invoice-4471` | `groups.yaml` pulling two files out of `postfach/`: e-mail (due date, IBAN) + invoice `.pdf` (number, total) |
| `postfach/` | leftover newsletter `.html` → must stay unclassified |
| `invoice_scan_INV-7731.png` | OCR, English, GBP |
| `service_cancellation.odt` | OpenDocument service cancellation, third class, enum field |
| `nachbestellung.md` | order without an order number → must need review |
| `order-L-0907/` | legacy Office: `.doc` letter + `.xls` positions (needs LibreOffice) |
| `kuendigung_abo.rtf` | legacy RTF, subscription cancellation (needs LibreOffice) |
| `quartalsbericht_q3.pptx` | presentation → must stay unclassified |
| `messebericht_2026.ppt` | legacy PowerPoint → must stay unclassified (needs LibreOffice) |
| `auftragsbestaetigung_AB-5521.md`, `gutschrift_GS-118.md`, `zahlungserinnerung_4471.md`, `lieferschein_LS-7702.md` | near misses: order confirmation, credit note, payment reminder, delivery note → must stay unclassified |
| `honorarnote_2026-17.md` | fee note → an invoice that never says "Rechnung" |
| `inventory_sample_scan.pdf` | scanned ruled inventory register: OCR, ruled table, marks in the image, wrapped and repeated status quotes |
| `inventory_example_digital.pdf` | the same form with native text and drawn PDF lines |

```bash
intextum extract corpus/inbox -s corpus/schemas -o /tmp/corpus-results.sqlite --force --detect-marks
python corpus/score.py /tmp/corpus-results.sqlite      # e.g. "score: 42/42 checks (100%)"
```

`score.py` expects a result with a wrong value to need review, so a verifier
that flags extraction errors improves the score. `corpus/decision_check.py`
measures a decision model on the same results (see
[Verifying values](guides/verification.md)).

The inventory registers need `--detect-marks`. Their marks are also checked without a
model in `tests/test_corpus.py`. In the scan, a short diagonal over one word is
currently not detected, and a strike-through can damage the OCR of the struck
text, so those checks fail on purpose rather than hiding the gap.

`corpus/generate.py` rebuilds the files (macOS with LibreOffice), and `corpus/expected.yaml`
holds the expected classes, review flags and values. Without LibreOffice, `score.py`
skips the legacy groups and says so.

### Fixture review

Create regression examples independently with generic inventory, purchase order
or invoice scenarios. Reduce a reported bug to the behavior under test, such as
wrapped table cells or evidence on a separate page. Use invented wording and
layouts; do not adapt private documents or reproduce a customer's workflow.

Corpus documents carry a synthetic-data label. Use explicit Example, Beispiel
or Muster identities, fictional streets and towns, and `.example` email domains.
IBAN-shaped strings use deliberately invalid `00` check digits. They exercise
text extraction only and must never represent payment destinations.

Keep the generator, schemas, expected values, filenames and deterministic tests
consistent. The generator builds in a temporary directory and copies its outputs
to `corpus/inbox/`, preserving other local files. The inbox ignore rule also
covers this directory; add each reviewed new fixture explicitly with `git add -f`.

Before committing a binary fixture, inspect its rendered pages and extracted
text, author metadata, comments, embedded objects, attachments and external
links. Review diffs and run the checks above. Secret scanning does not identify
private scenarios or every identifier embedded in a document. Keep local `.env`
files, workspaces, caches and browser captures outside tracked files.

For a local secret scan with Gitleaks installed:

```bash
gitleaks git . --log-opts=--all --redact=100 --no-banner --ignore-gitleaks-allow
```
