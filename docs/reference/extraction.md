# Extraction and model calls

## Processing steps

1. **Convert.** Docling produces a structured `DoclingDocument`. The complete
    document and available images are stored in SQLite for review; the Markdown
    export remains the model input, with its exact text stored in the database.
    Plain-text and CSV/MSG fallback readers also produce a simple document view.
2. **Combine.** A group's files are joined under `=== FILE: <name> ===` headers
    and tracked by offset, so evidence maps back to its file and page.
3. **Classify.** The LLM gets the start of each file plus the class list, with
    a "No matching document class" option.
4. **Extract.**

    - Scalar fields share one call, and each list field gets its own call
      so it has its own output budget.
    - Replies are constrained with a JSON schema. If the server rejects that,
      the tool falls back to JSON mode, then to plain text. It retries with a
      larger token budget when a reply is cut off.
    - Each value comes with a short verbatim anchor. The anchor is matched
      against the source: first exactly, then ignoring case, whitespace and
      table pipes.
    - Values are coerced to their dtype, e.g. `1.234,56` → `1234.56`,
      `30.000` → `30000` and `31.12.2025` → `2025-12-31`. A single separator
      followed by exactly three digits groups thousands; `0.125` stays a
      decimal. Because `2.125` could be a decimal, a `float` value in that form
      also gets an `ambiguous_number` validation error for review. Currency
      abbreviations such as `DM` map to ISO codes (`DEM`).

## Model statistics

At startup the run prints the model, its context window (read from LM Studio or vLLM, or
`--context-length`) and the limits in use. It warns if `--max-chars` plus
`--max-output-tokens` can exceed the context window. Then every model call gets
one line (example, numbers made up):

```
model my-model @ http://localhost:1234/v1 · context 8,192 tokens · max output 4,096 tokens · max source 60,000 chars · thinking off
[3/9] acme/contract.doc (1 file): …
    llm classify acme/contract.doc · in 1,873 tok · out 41 tok · first token 3.2s · total 5.1s · 21.6 tok/s · context 1,914/8,192 (23%)
    llm extract acme/contract.doc [line_items] · in 4,410 tok · out 12 tok · …
    ⚠ input + max output (4,096) exceeds the context window
llm: 14 call(s) · in 38,210 tok · out 6,905 tok · 21m14s · 9.8 tok/s · largest request 9,012 tok of 8,192
```

While a reply streams, a progress line shows the tokens so far (counted from the
stream, hence `~`), the elapsed time and, after a reply was cut off, the retry
with a doubled budget:

```
    … ~2,310/8,192 tok · 58.0s · attempt 2, earlier reply was cut off · extract acme/contract.doc [line_items]
```

In a terminal the line is updated in place; in a log file it appears once a reply
has streamed for 30 seconds, and every 30 seconds after that.

Each line shows:

- **what the call was for:** `classify`, `extract <group> [fields]`, or
  `source <group> ← <file>` for a value taken from a separate file;
- **tokens:** input, output and, if reported, thinking tokens;
- **timing:** time to the first token, total time and tokens per second;
- **context:** how much of the context window the call used.

Token counts come from the server (`stream_options.include_usage`). A `~` marks an
estimate from the text length, used when the server reports none. A warning is
shown when input plus the output limit exceeds the context window, or when a reply
was cut off. A request that does not fit usually means a reply that is truncated or
empty.
