# Getting started

## Install

Use Python 3.11 or later. Run these commands from a checkout of the repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[ui]"
```

The `ui` extra includes the local browser review interface. For CLI-only use,
install with `python -m pip install -e .` instead.

Recognition can download models on first use. Legacy Office formats also need
LibreOffice; see [supported files](guides/conversion.md#supported-files).

## Configure a model endpoint

Start an OpenAI-compatible model server and use the model name it exposes:

```bash
export OPENAI_BASE_URL=http://localhost:1234/v1  # LM Studio
export INTEXTUM_MODEL=your-model-name
# export OPENAI_API_KEY=your-api-key           # if the endpoint requires one
```

The default endpoint is local Ollama at `http://localhost:11434/v1`.
Set `INTEXTUM_MODEL` or pass `--model`; there is no default extraction model.
You can also keep these values in a folder-specific `.env` file; see
[Configuration](configuration.md).

## Extract, review, and export

Put documents in `inbox/`. Each top-level subfolder becomes one group, and each
loose file becomes its own group. Use the included example schemas to try the
workflow, then [write schemas](guides/schemas.md) for your documents.

```bash
intextum check-schemas examples/schemas
intextum extract ./inbox --schemas examples/schemas --dry-run
intextum extract ./inbox --schemas examples/schemas
intextum view ./inbox-results.sqlite
intextum export ./inbox-results.sqlite -o ./exports
```

`--dry-run` previews the discovered groups without converting or extracting.
The extraction writes `inbox-results.sqlite`; `view` opens the review interface at
<http://127.0.0.1:8765>. Export creates JSON and CSV from the current corrected
results.

Run the same extraction again to skip unchanged groups. Use `--force` when you
want to process them again. Extraction exits with code `1` if any group failed;
see the [CLI reference](reference/cli.md#exit-codes) for other exit codes.

Continue with [grouping](guides/grouping.md), [reviewing results](guides/review.md),
or the [workspace and export reference](reference/workspace.md).
