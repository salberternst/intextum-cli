# intextum-cli

`intextum-cli` uses Docling to recognize documents and an OpenAI-compatible
model endpoint to classify them and extract fields from YAML schemas. Results
and their evidence live in a SQLite workspace for local browser review,
correction, and JSON or CSV export.

```text
Documents → Docling → classify group → extract schema fields → SQLite → JSON / CSV
```

## Start here

Follow [Getting started](getting-started.md) to install the CLI, configure an
endpoint, and extract your first folder.

| Task | Documentation |
| --- | --- |
| Configure endpoints, models, and folder settings | [Configuration](configuration.md) |
| Organize folders and handle duplicates | [Grouping documents](guides/grouping.md) |
| Inspect OCR, tables, and drawn marks | [Document conversion](guides/conversion.md) |
| Define fields and evidence rules | [Writing schemas](guides/schemas.md) |
| Extract values from another file | [Attachments](guides/attachments.md) |
| Check results with a decision model | [Verification](guides/verification.md) |
| Correct values and finish review | [Reviewing results](guides/review.md) |
| Look up commands and flags | [CLI reference](reference/cli.md) |
| Understand exports, caching, and backups | [Workspace reference](reference/workspace.md) |
| Understand model calls and statistics | [Extraction reference](reference/extraction.md) |
| Contribute or evaluate a model | [Development](development.md) |
