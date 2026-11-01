# intextum-cli

Classify document groups and extract structured fields into a SQLite workspace.
Review evidence and correct values in a local browser, then export JSON or CSV.

Uses Docling and an OpenAI-compatible model endpoint such as Ollama, LM Studio,
or vLLM.

```text
Documents → Docling → classify group → extract schema fields → SQLite → JSON / CSV
```

- **Group related files.** Extract a letter and its spreadsheet attachment together.
- **Define schemas in YAML.** Choose fields, types, and evidence rules per class.
- **Trace every value.** Keep evidence linked to source files and pages where available.
- **Review and correct.** Missing, invalid, and unsupported values trigger review.
- **Run incrementally.** Reuse cached conversions and skip unchanged groups.

## Quick start

Requires Python 3.11+ and a running OpenAI-compatible model endpoint. From a
checkout of this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[ui]"

export OPENAI_BASE_URL=http://localhost:1234/v1  # LM Studio; default: Ollama :11434
export INTEXTUM_MODEL=your-model-name
# export OPENAI_API_KEY=your-api-key           # if the endpoint requires one

intextum check-schemas examples/schemas
intextum extract ./inbox --schemas examples/schemas --dry-run
intextum extract ./inbox --schemas examples/schemas
intextum view ./inbox-results.sqlite
intextum export ./inbox-results.sqlite -o ./exports
```

Each top-level subfolder is one group; each loose file is its own group. Use
`groups.yaml` for explicit groups. Store model and recognition settings in a
folder-specific `.env` file; start with [.env.example](.env.example).

The `ui` extra enables browser review at <http://127.0.0.1:8765>. Install with
`python -m pip install -e .` for CLI-only use. Recognition can download models on
first use; legacy Office formats require LibreOffice.

## Documentation

The [documentation overview](docs/index.md) links to every guide and reference.
Common starting points:

- [Getting started](docs/getting-started.md): installation and the first extraction.
- [Writing schemas](docs/guides/schemas.md): field types and evidence rules.
- [Reviewing results](docs/guides/review.md): corrections and review decisions.
- [CLI reference](docs/reference/cli.md): commands, flags, and exit codes.

Build or preview the searchable documentation with [MkDocs](https://www.mkdocs.org/):

```bash
python -m pip install -e ".[docs]"
python -m mkdocs serve
# Validate links and build static HTML in site/:
python -m mkdocs build --strict
```

The documentation preview runs at <http://127.0.0.1:8000>.

## Development

See the [development guide](docs/development.md) for checks, frontend builds,
installed-wheel validation, and model evaluation. Repository conventions live
in [AGENTS.md](AGENTS.md).

Licensed under the [MIT license](LICENSE).
