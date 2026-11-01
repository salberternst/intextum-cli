# CLI reference

```text
intextum [--version] [-v] COMMAND ...
```

Use `intextum --help` or `intextum COMMAND --help` for built-in help.
Global `-v` / `--verbose` shows library logs and goes before the command, for
example `intextum -v extract ./inbox -s ./schemas`.

| Global option | Behavior |
| --- | --- |
| `-h`, `--help` | Show help; also available on each subcommand. |
| `--version` | Print the installed version and exit. |
| `-v`, `--verbose` | Show library logs. |

| Command | Purpose |
| --- | --- |
| [`extract`](#extract) | Classify and extract document groups. |
| [`verify`](#verify) | Verify stored results with a decision model. |
| [`view`](#view) | Review and correct a SQLite workspace in the browser. |
| [`export`](#export) | Export current corrected results as JSON and CSV. |
| [`convert`](#convert) | Print recognized text from one source file. |
| [`check-schemas`](#check-schemas) | Validate schema YAML. |

## extract

```text
intextum extract INPUT --schemas SCHEMAS [options]
```

`INPUT` is a folder with documents; `SCHEMAS` is a YAML file or directory.
See [Grouping documents](../guides/grouping.md) for discovery and duplicates.

| Option | Behavior |
| --- | --- |
| `-s`, `--schemas PATH` | Required schema YAML file or directory. |
| `-o`, `--out PATH` | SQLite workspace; default: `<input>-results.sqlite`. |
| `--group-by folder\|file` | One group per top-level subfolder (default) or per file. |
| `--exclude REGEX` | Ignore matching relative file paths, case-insensitive; repeatable. Excluded files are also excluded from attachment selection and duplicate comparison. Example: `--exclude entwurf --exclude '^[^/]+/Archiv/'`. |
| `--keep-duplicates` | Process copies and versions of the same document separately. |
| `--class NAME` | Skip automatic classification for groups without a saved viewer choice or `groups.yaml` class. See [class precedence](../guides/grouping.md#choosing-a-class). |
| `--classify-only` | Skip field extraction; exported `_summary.csv` lists each group's class and reason. |
| `--max-chars N` | Source characters per extraction call; default: `60000`. Counted after field-specific page selection. Short files are kept whole; long files share the remaining budget. Truncation triggers review. |
| `--retries N` | Ask again for missing required fields; default: `1`. |
| `--force` | Reprocess unchanged groups. |
| `--dry-run` | Preview discovered groups without converting or extracting. |
| `--no-verify` | Skip verification even when a verifier is configured. |

`extract` also accepts the [model](#model-options),
[recognition](#recognition-options), and [verifier](#verifier-options) options
below. Inspect [model statistics](extraction.md#model-statistics) when requests
reach the context or output limit.

### Model options

These options apply to `extract`. Settings precedence is
**CLI → shell environment → nearest `.env` → defaults**; see
[Configuration](../configuration.md).

| Option | Behavior |
| --- | --- |
| `--env-file PATH` | Use this settings file instead of automatic `.env` discovery; relative to the working directory. |
| `--base-url URL` | OpenAI-compatible endpoint; `OPENAI_BASE_URL`; default: `http://localhost:11434/v1`. |
| `--model NAME` | Model name; `INTEXTUM_MODEL`; required when a model call is needed. |
| `--api-key KEY` | API key if needed; `OPENAI_API_KEY`. |
| `--max-output-tokens N` | Initial output token budget per call; default: `4096`. Cut-off replies are retried with a larger budget. |
| `--context-length N` | Model context window in tokens for statistics and warnings. By default, discover it from the endpoint where supported. |
| `--thinking` | Enable reasoning through `chat_template_kwargs.enable_thinking`; off by default. Thinking uses output tokens and takes more time. |
| `-q`, `--quiet` | Suppress per-call statistics and progress; final totals are still printed. |

### Recognition options

These options apply to `extract` and `convert`. See
[Document conversion](../guides/conversion.md) for formats, OCR requirements,
table modes, and mark detection limits.

| Option | Behavior |
| --- | --- |
| `--force-ocr` | OCR every page. |
| `--ocr-engine auto\|tesseract` | Docling automatic selection (default) or its Tesseract CLI engine; `INTEXTUM_OCR_ENGINE`. |
| `--ocr-language LANGUAGE` | Repeat for multiple engine-specific language codes; `INTEXTUM_OCR_LANGUAGES=deu,eng`. |
| `--table-mode ruled\|docling\|predicted` | Table recognition mode; default: `ruled`; `INTEXTUM_TABLE_MODE`. |
| `--detect-marks`, `--no-detect-marks` | Enable or disable drawn-line tags in ruled forms; default: off; `INTEXTUM_DETECT_MARKS`. |

### Verifier options

These options apply to `extract` and `verify`. Verification is disabled until a
model is configured; see [Verifying values](../guides/verification.md).

| Option | Behavior |
| --- | --- |
| `--verifier-model NAME` | Decision model; `INTEXTUM_VERIFIER_MODEL`. |
| `--verifier-base-url URL` | Decision endpoint; `INTEXTUM_VERIFIER_BASE_URL`; default: extraction endpoint. |
| `--verifier-api-key KEY` | API key for the verifier; `INTEXTUM_VERIFIER_API_KEY`. Reuses the extraction key only for the same endpoint. |
| `--verifier-threshold N` | Flag probabilities below this threshold, strictly between `0` and `1`; default: `0.3`; `INTEXTUM_VERIFIER_THRESHOLD`. |

## verify

```text
intextum verify DATABASE [--env-file PATH] [--force] [verifier options]
```

Check completed results and automatic classifications, including unclassified
results, whose verification is missing or outdated. Uses cached source text;
originals are not needed. `--force` checks all eligible results again. Configure
a verifier with the [options above](#verifier-options).
`--env-file` replaces automatic settings discovery from the recorded input
folder, or the current directory when that folder is unavailable.

## view

```text
intextum view DATABASE [options]
```

Requires the `ui` extra. See [Reviewing results](../guides/review.md) for the
review workflow and correction behavior.

| Option | Behavior |
| --- | --- |
| `--input PATH` | Folder containing originals; default: recorded input path, if available. |
| `-s`, `--schemas PATH` | Override embedded schemas for this review session. |
| `--port N` | Server port; default: `8765`. |
| `--host HOST` | Server address; default: `127.0.0.1`. |
| `--no-browser` | Do not open a browser window. |

The viewer reads and writes local files without authentication. The database
alone supports cached review and corrections. Original downloads, desktop
opening, document-view rebuilds, and re-extraction need the source folder.

## export

```text
intextum export DATABASE --out DIRECTORY [--format all|json|csv] [--state all|reviewed|open]
```

`-o` / `--out` is required. Both format and state default to `all`.
Exports use the current corrected results from one consistent database
snapshot; see [Workspace and exports](workspace.md) for JSON and CSV formats.
When exporting JSON, a review-state filter removes excluded results' JSON files
from earlier exports in the same directory. CSV-only exports leave JSON untouched.

## convert

```text
intextum convert FILE [--env-file PATH] [recognition options]
```

Print the text recognized from one file. Use it to inspect OCR or refine field
descriptions before extraction. The [recognition options](#recognition-options)
are the same as for `extract`. Settings discovery starts in the file's folder;
`--env-file` selects a settings file explicitly.

## check-schemas

```text
intextum check-schemas SCHEMAS
```

Validate a schema YAML file or directory without a model. See
[Writing schemas](../guides/schemas.md).

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Command succeeded. Results may still need review. |
| `1` | An extraction run had failed groups. |
| `2` | Invalid arguments, configuration, schema validation, or a command/storage error. |
