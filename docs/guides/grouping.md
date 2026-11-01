# Grouping documents

## Default grouping and groups.yaml

1. Groups listed in `groups.yaml` at the top of the input folder (see
    [examples/groups.yaml](https://github.com/salberternst/intextum-cli/blob/main/examples/groups.yaml)).
    Entries can be files, folders, or globs. A group can set `class:` to skip
    classification.
2. Every other top-level subfolder is one group, including all files below it.
    With `--group-by file`, every other file is its own group instead.
3. Every other file directly in the input folder is its own group.

Hidden files and folders, Office lock files (`~$…`) and file types that cannot
be converted (e.g. `.shp`, `.dbf`) are ignored. So are files matching `--exclude`.
The run prints how many files were skipped, by extension.

The selected `--schemas` file or directory is excluded from discovery, including
when it lives inside the input folder. `groups.yaml` and `sources.yaml` are
configuration files and are also excluded.

## Choosing a class

Class selection follows this precedence:

1. A saved viewer choice, including **None of these classes**.
2. The group's `class:` in `groups.yaml`.
3. The `--class NAME` option.
4. Automatic classification by the model.

Use **Automatic classification** in the viewer to remove a saved choice and
return to the remaining rules. See [class overrides](review.md#class-overrides).

## Source scopes

Duplicate detection and [attachment selection](attachments.md#selecting-a-source)
use the same source scopes:

| Included documents | Scope |
| --- | --- |
| At least one file directly in the input folder | The whole input folder. |
| Files only inside subfolders | Each top-level subfolder separately. |

For example, an input folder containing only `customer-a/` and `customer-b/`
keeps their documents in separate scopes. `--group-by file` changes extraction
groups while keeping these scopes.

## Duplicates and versions

Folders often hold the same document several times: a `.docx` and its signed
`.pdf`, a draft and the final version, or a copy under `Archiv/`. Before
processing, files are converted for duplicate comparison. Files in the same
[scope](#source-scopes) count as duplicates when:

- they are byte-identical, or
- their texts overlap at least 90 % **and** they contain exactly the same numeric
  tokens in the same order, including signs and repeated values (dates, reference
  numbers, amounts). The number check keeps different contracts built from one
  template apart. Copies with extra numeric metadata, such as a signing date,
  remain separate.

One copy is kept, chosen in this order: not in an archive folder, signed
(`gez`, `unterschrieben`, …), not a draft (`Entwurf`), newest. The other copies
are skipped and listed under `duplicates` in the result JSON and in
`_summary.csv`. A group made up only of duplicates gets the status `duplicate`.
Pass `--keep-duplicates` to process every copy.

For fields whose values live in another file, see [Attachments](attachments.md).
Use the [CLI reference](../reference/cli.md#extract) to look up grouping and
exclusion flags.
