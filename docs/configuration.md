# Configuration

Put a `.env` file in the input folder or a parent project directory. Start with
[.env.example](https://github.com/salberternst/intextum-cli/blob/main/.env.example):

```dotenv
OPENAI_BASE_URL=http://localhost:1234/v1
INTEXTUM_MODEL=your-model-name
# OPENAI_API_KEY=your-api-key
```

## Separate settings per project

For example, each customer can have its own endpoint and model:

```text
customer-a/
  .env
  inbox/
  schemas/
```

```bash
intextum extract customer-a/inbox --schemas customer-a/schemas
# Or select a settings file explicitly, relative to the working directory:
intextum extract customer-a/inbox -s customer-a/schemas --env-file .env.customer-a
```

## Precedence

Settings take precedence in this order: **CLI flags → shell environment variables
→ `.env` → built-in defaults**. For example, `--base-url` overrides
`OPENAI_BASE_URL`. Without an endpoint setting, local Ollama at
`http://localhost:11434/v1` remains the default.

## Recognition settings

Recognition settings for a folder's documents can live in the same file, so
`extract` and `convert` read them without repeating flags:

```dotenv
INTEXTUM_OCR_ENGINE=tesseract        # --ocr-engine
INTEXTUM_OCR_LANGUAGES=deu,eng       # --ocr-language, comma-separated
INTEXTUM_TABLE_MODE=ruled            # --table-mode
INTEXTUM_DETECT_MARKS=true           # --detect-marks
```

## Settings file discovery

Automatic discovery walks upward from the input folder and loads only the nearest
`.env`; parent files are not merged. `--env-file` replaces automatic discovery and
reports an error if the selected file is missing. Values support quotes and
comments; variable expansion and shell commands are not evaluated. Loading a file
does not change the process environment. `.env` and `.env.*` files are ignored by
Git, while `.env.example` can be committed. Hidden settings files are excluded from
document processing.

## Settings reference

| Environment variable | CLI override | Default |
| --- | --- | --- |
| `OPENAI_BASE_URL` | `--base-url` | `http://localhost:11434/v1` |
| `INTEXTUM_MODEL` | `--model` | Must be set when a model call is needed |
| `OPENAI_API_KEY` | `--api-key` | Unset |
| `INTEXTUM_OCR_ENGINE` | `--ocr-engine` | `auto` |
| `INTEXTUM_OCR_LANGUAGES` | `--ocr-language` (repeatable) | Engine defaults |
| `INTEXTUM_TABLE_MODE` | `--table-mode` | `ruled` |
| `INTEXTUM_DETECT_MARKS` | `--detect-marks`, `--no-detect-marks` | `false` |
| `INTEXTUM_VERIFIER_MODEL` | `--verifier-model` | Unset; verification disabled |
| `INTEXTUM_VERIFIER_BASE_URL` | `--verifier-base-url` | Extraction endpoint |
| `INTEXTUM_VERIFIER_API_KEY` | `--verifier-api-key` | Extraction key for the same endpoint only |
| `INTEXTUM_VERIFIER_THRESHOLD` | `--verifier-threshold` | `0.3` |

Recognition settings apply to `extract` and `convert`. The standalone `verify`
command discovers `.env` from the workspace's recorded input folder, or from
the current directory when that folder is unavailable. See
[Verification](guides/verification.md) for setup and the
[CLI reference](reference/cli.md) for command-specific options.
