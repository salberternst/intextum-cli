# Repository guidance

## Project

`intextum-cli` is a Python 3.11+ command-line tool that converts documents with
Docling, classifies document groups, and extracts structured fields through an
OpenAI-compatible model endpoint. It stores generated output in one SQLite
workspace and exports JSON and CSV on demand.
`intextum view` serves a local browser interface for reviewing and correcting them.
Read `README.md` for the quick start and `docs/` for CLI behavior, schema examples,
and configuration. `mkdocs.yml` defines the documentation navigation.

## Development

Use a virtual environment and install the editable package with development
dependencies:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,ui]"
```

Run these checks for Python changes:

```sh
python -m pytest
python -m ruff check src tests
python -m ruff format --check src tests
```

Format changed Python files with `python -m ruff format <paths>`. Ruff targets
Python 3.11, uses an 88-character line length, and checks imports. Follow the
existing type annotations and module structure.

## Code layout

- `src/intextum_cli/cli.py`: command dispatch and error reporting; the installed
  entry point is `intextum_cli.cli:main`. `cli_parser.py` defines arguments;
  `commands/` contains extraction, workspace, and schema command implementations.
- `config.py`: folder-specific `.env` discovery and model setting precedence.
- `pipeline.py`: run orchestration, incremental skips, and result commits.
  `group_processing.py` processes one group; `external_fields.py` selects and
  extracts attachments. `processing.py` contains options, source scopes, and
  summaries; `fingerprints.py` tracks every module that affects extraction.
- `store.py`: SQLite connection lifecycle, format validation, and workspace
  metadata. `result_store.py` owns results, schemas, corrections, and source
  bindings; `cache_store.py` owns cached conversions, binary assets, and
  classifications. `store_records.py` defines their shared records. Preserve the
  transaction boundaries when changing these repositories.
- `exports.py`: JSON and CSV exports from one consistent database snapshot.
  `naming.py` provides shared filesystem-safe names for results and schemas.
- `view.py` and `view_api.py`: review library, optional NiceGUI startup, and API.
- `review_ui.py`: workspace selection and navigation; `review_sidebar.py` renders
  search, filters, and source-file lists; `review_batch.py` handles batch extraction
  dialogs and progress. `review_header.py` renders metadata and status.
  `view_document.py`, `view_fields.py`, `view_editors.py`, `review.py`, and `static/`
  handle document views, fields, typed editors, and styling.
- `edits.py`: applying stored corrections.
  Correction recording belongs to `result_store.py`.
- `groups.py` and `dedupe.py`: discovery, grouping, scopes, and duplicates.
- `convert.py`: conversion lifecycle and caching; `conversion_readers.py` handles
  direct CSV and message readers; `conversion_recovery.py` retains recognized text
  omitted during layout or table assembly; `conversion_tables.py` reconstructs
  large ruled forms from positioned text and page images; `conversion_marks.py`
  tags text in those forms that drawn lines underline, strike or cross. Each
  `ConvertedFile` carries its source identity.
  `source.py` combines text, selects matching pages, and locates evidence.
- `document_cache.py`: complete cached Docling documents and images;
  `document_model.py` handles representations and source-to-element indexes;
  `document_render.py` renders sanitized HTML. Cache-only viewer reads must never
  convert documents or call a model. Rebuilds preserve extraction text, source
  versions, and corrections.
- `classify.py`, `extract.py`, and `llm.py`: classification, extraction, structured
  replies, endpoint compatibility, and model calls. `llm_types.py` defines shared
  replies, telemetry, and generation settings; `llm_endpoints.py` detects endpoints
  and discovers context limits. Keep both modules in extraction and classification
  code fingerprints. `extraction_prompt.py` owns prompts and response schemas;
  keep it in the extraction code fingerprint.
- `decisions.py` and `verification.py`: the decision-model client (Ollama and
  llama.cpp `/v1/systemone`, OpenRouter decisions) and the verification phase
  after extraction. Verification records are stored apart from results, keyed
  by verifier settings and their own code digest, so they never invalidate
  extraction. Keep the software endpoint-only: no model loading or unloading.
- `schema.py`, `values.py`, and `sources.py`: YAML schemas, value coercion, and
  attachment ranking. `stats.py` reports model statistics. These modules all live
  in `src/intextum_cli/`.
- `frontend/`: pinned Docling web components and reproducible bundle build.
  Run `npm ci && npm run build` there after dependency changes. The resulting
  `static/vendor/` JavaScript and license notices ship with the Python wheel;
  end users need no Node process, CDN, or separate document service.
- `tests/`: pytest tests; `conftest.py` provides the `fake_llm` fixture.
- `examples/`: sample grouping configuration and schemas.
- `corpus/`: fictional documents, schemas, ground truth in `expected.yaml`, and
  generation and scoring scripts.

## Implementation and validation

- Keep changes focused and update the README or example schemas when user-facing
  options, output formats, or schema behavior change. Keep the README concise and
  detailed documentation in `docs/`. Install `.[docs]` and run
  `python -m mkdocs build --strict` for documentation changes.
- Preserve evidence provenance: extracted values must remain traceable to source
  files and pages where available. Missing required values, invalid values, and
  unsupported evidence must continue to trigger review as appropriate.
- Preserve incremental processing. When changing extraction, grouping, sources,
  or configuration, check that fingerprints and cache keys account for the
  inputs that affect results.
- Keep model compatibility and JSON response fallbacks intact when changing
  `llm.py`. Use fake replies and mocked conversion for deterministic tests;
  ordinary tests should not need a running model or downloaded OCR models.
- Add regression coverage for behavior changes in the relevant test module.
  Documentation-only changes need content and link checks rather than a full
  Python test run. Report checks run and any checks that could not run.
- Keep generated results, conversion caches, virtual environments, and package
  metadata out of commits. Avoid regenerating binary corpus fixtures unless the
  task requires it; `corpus/generate.py` requires macOS and LibreOffice.
- Use independently invented, generic examples for regression tests. Never copy
  private documents, schema terminology, layouts or scenarios into fixtures.
  Use explicit Example/Muster identities, `.example` email domains and invalid
  account placeholders. Follow the fixture review guidance in `docs/development.md`.

For prompt or model changes, the optional corpus evaluation uses a configured
model endpoint and document conversion dependencies:

```sh
intextum extract corpus/inbox -s corpus/schemas -o /tmp/corpus-results.sqlite --force --detect-marks
python corpus/score.py /tmp/corpus-results.sqlite
```

Legacy Office formats require LibreOffice; the scorer skips their groups when it
is unavailable. Keep corpus documents, schemas, and expected values consistent.

`AGENTS.md` is the shared source of repository instructions. `CLAUDE.md` links to
this file; edit the instructions here.
