# docx-color-cli

Accept tracked changes in Word documents and turn inserted text into permanent
font colors.

`docx-color-cli` converts a tracked DOCX into a new DOCX with insertions in red,
unchanged text in black, and deleted content removed. It works directly with
OOXML and keeps supported document structures and editable fields intact.

The project is under active development. Content fidelity takes priority over
formatting and performance. Supported revisions are accepted; unsupported or
ambiguous structures cause an error before the output is published. Compatibility
with every Word document and identical rendering in Microsoft Word are not guaranteed.

## Installation

Install from a local source checkout. The commands below do not assume a release
is available on PyPI.

### With uv

From the project directory, install the CLI in an isolated tool environment:

```bash
uv tool install .
docx-color --help
```

### With pip

Use an activated Python 3.11+ virtual environment:

```bash
python -m pip install .
docx-color --help
```

## Quick start

```bash
docx-color manuscript.docx manuscript_colored.docx
```

| Content in the original document | Output |
| --- | --- |
| Inserted text | Retained in red (`FF0000`) |
| Unchanged text | Retained in black (`000000`) |
| Deleted text | Removed |
| Replaced text | Old text removed; replacement retained in red |
| Supported moved text | Source removed; destination retained in red |

Supported revisions are accepted, leaving no unhandled revision markers in the
published output. Existing text colors are intentionally replaced by these colors.

Omit the output path to create `<input_stem>_colored.docx` beside the input:

```bash
docx-color manuscript.docx
```

Write conversion statistics to a JSON report:

```bash
docx-color manuscript.docx manuscript_colored.docx --report report.json
```

Choose different insertion and unchanged-text colors:

```bash
docx-color manuscript.docx manuscript_colored.docx --inserted-color 0000FF --unchanged-color 000000
```

The equivalent short options are `-ic` and `-uc`:

```bash
docx-color manuscript.docx manuscript_colored.docx -ic 0000FF -uc 000000
```

## Example:

Try the included, four-page synthetic manuscript (approximately 1,450 words after acceptance).

Download the [tracked input](examples/tracked.docx) and
[converted output](examples/colored.docx), or run from the checkout:

Four fictional authors contribute **124 revision markers: 73 insertions and 51
deletions** across the title, summary, results, discussion, Methods and table.
The converted document preserves two equations and editable citation/hyperlink fields.

```bash
uv run docx-color examples/tracked.docx examples/colored.docx
```

![Animated workflow showing tracked edits, the conversion command and red-and-black output](assets/demo.gif)

To compare against a separate DOCX manually saved after **Accept All Changes** in
Microsoft Word, enable reference validation:

```bash
docx-color manuscript.docx manuscript_colored.docx --reference accepted_in_word.docx
```

Any comparison failure prevents publication and preserves an existing output.
Comparison checks logical text, structure, editable fields, equations and linked
resources, ignoring font colors and equivalent run splitting. It is conservative:
Word re-save differences can also cause a rejection. It does not verify the
reference's provenance or identical page layout. No Word automation is used.

## Command-line reference

```text
docx-color [-h] [--inserted-color RGB] [--unchanged-color RGB] [--report REPORT]
           [--reference REFERENCE] [--no-strict] input [output]
```

| Argument | Description | Default |
| --- | --- | --- |
| `input` | Source DOCX containing tracked changes | Required |
| `output` | Destination DOCX | `<input_stem>_colored.docx` |
| `-ic`, `--inserted-color` | Color for inserted text, as six hexadecimal digits without `#` | `FF0000` |
| `-uc`, `--unchanged-color` | Color for unchanged text, in the same format | `000000` |
| `--reference` | Word-accepted DOCX; mismatches block output publication | No external comparison |
| `--report` | Path for a JSON conversion-statistics report | No report file |
| `--no-strict` | Legacy compatibility option; does **not** bypass safety checks | Disabled |
| `-h`, `--help` | Show command help | — |

Successful conversion prints the output path and statistics. Errors return a
nonzero exit status. The JSON report contains operation counts, not a certification
of equivalence with Microsoft Word.

## Supported documents and revisions

- Text insertions, deletions and replacements, including split runs and nested
  insertion/deletion revisions.
- Supported paragraph-mark insertions and deletions, including adjacent paragraph
  merges with different properties. The final surviving paragraph mark determines
  the merged paragraph's properties.
- Paired inline, whole-paragraph and cross-paragraph moves within the same document
  part, subject to structural boundary checks.
- Text and supported structural changes in tables: cell insertions, cell deletions
  consistent with the explicit final grid, explicit vertical merge-state changes,
  and row edits with valid surviving merge ownership. Row/cell insertion marks
  do not recolor unchanged text without a text-level insertion revision.
- Mathematical run revisions, including supported mixed-stream splitting and
  inherited properties, nested revisions, inserted equation controls and fully
  deleted equation objects. Partially retained objects are
  never discarded merely because their control is marked deleted.
- Supported formatting revisions, retaining current properties and removing
  historical snapshots, including `tblPrExChange`.
- Shared Strict/Transitional OOXML revision vocabulary, preserving each XML part's
  namespace dialect; no general Strict-to-Transitional format conversion.
- Revisions within independently processable AlternateContent alternatives, keeping
  both Choice and Fallback; complete custom XML/content-control markup ranges.

The converter preserves supported hyperlinks, bookmarks, images, OMML equations,
content controls, headers, footers, footnotes and endnotes. Word fields, cross-references
and Zotero citation/bibliography fields remain editable rather than being flattened
into plain text. Fields are preserved, not recalculated. Literal REF/PAGEREF/NOTEREF
and internal hyperlink dependencies are checked for newly missing or ambiguous
bookmark targets. Existing broken references are preserved, not repaired. Dynamic
or conditional reference changes that cannot be resolved safely are rejected.

Images proven unused after revision acceptance are cleaned up without recompressing
retained images. Equation containers made empty by accepted deletions and comments
that lose their final active reference are cleaned up with dependency checks.

## Limitations

The converter targets the final content shown in Word's **No Markup** view.
That view is not equivalent to simply removing revision tags, and complete Word
compatibility has not been established.

The following cases are currently rejected or unsupported:

- Unknown revision types, mixed namespace dialects within a part, and unsupported
  extension semantics.
- Unpaired moves, moves nested inside other moves, cross-cell/part moves, and
  ranges sharing moved content. Moves nested inside ordinary insertions/deletions
  are supported.
- Deleting section boundaries, merging across cells/tables, and unsupported
  terminal paragraph-mark deletions. Merging into a paragraph that retains its
  section boundary is supported.
- Cell deletions requiring inferred horizontal span/grid repair; vertical merge
  edits requiring ownership transfer or reconciliation of live continuation content.
- Partial/overlapping custom XML tag ranges, custom XML move ranges, cross-branch
  fields/ranges, conflicting math properties and equation-control deletions with
  retained or unrecognized arguments.
- Comment cleanup with unresolved dependencies, including surviving threaded replies.

Internal checks cover ZIP/XML integrity, relationships, field boundaries, supported
math argument cardinalities, table grids, revision removal and retention invariants.
They are not a complete OOXML schema validator or a rendering engine.

The independent comparator is also available as
`docx_color_cli.validation.validate_docx(output, reference)`. Its optional
`semantic=True` comparison recognizes a small, tested set of representation
alternatives and reports each normalization; the CLI uses the conservative default.
The private academic sample's body passes bounded semantic comparison, while full
comparison still detects font-signature differences. These remain deliberately
unignored. This is evidence for the tested sample, not a guarantee for all documents.

## File safety

The input document is preserved. Input, output, reference and report paths must identify
different files; checks include resolved paths, symbolic links and existing hard
links.

Output is written to a temporary file beside the destination and checked before
atomic replacement. Conversion or validation failure preserves an existing output.
**Successful conversion replaces an existing destination file.**

The optional report is published before the DOCX. These are separate atomic
operations: if final DOCX publication fails, the report may already contain the
attempted conversion's statistics.

## License

Licensed under the [MIT License](LICENSE).
