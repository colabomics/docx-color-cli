# docx-color-cli 1.2.0

Manuscript revisions are hard enough. Highlighting every addition shouldn't be.

## Highlights

- **Automatic insertion coloring:** identify surviving additions from Word's tracked changes and color them in the corresponding accepted document.
- **One command, three paths:** provide the tracked document, its accepted copy, and the output location.
- **Editable equations and tables:** color supported mathematical insertions and table-cell additions while preserving native Word structures.
- **Document fidelity:** validate text, tables, equations, references, hyperlinks, and non-color formatting before publishing the output.
- **Local processing:** your manuscript stays on your computer. Both input files remain unchanged.
- **Clear results:** report SUCCESS, PARTIAL, or FAILED, with optional JSON reports that omit manuscript text.
- **Safe output publication:** validate a temporary DOCX before atomically replacing the destination. A separate report-writing failure is reported accurately.
- **Ready-to-try examples:** use the [public Word documents](examples/) and watch the [animated demonstration](assets/demo.gif).

## Installation

Requires Python 3.11 or newer.

Install with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install docx-color-cli
```

Or install with pip:

```bash
python -m pip install docx-color-cli
```

## Quick Start

Prepare two corresponding Word documents:

1. Keep the original document with Track Changes as `tracked.docx`.
2. Save a separate copy in Microsoft Word, accept all revisions, turn off Track Changes, and save it as `accepted.docx`. Do not make additional content edits to either copy.

The tool does not accept revisions itself. The accepted document is the authority for final content and formatting.

```bash
docx-color tracked.docx accepted.docx colored.docx
```

Surviving insertions that can be identified safely are colored red (`FF0000`). Use `--color` for another six-digit hexadecimal color and `--report` to save a JSON report:

```bash
docx-color tracked.docx accepted.docx colored.docx --color 0000FF --report result.json
```

Successful conversion replaces an existing output file. PARTIAL means a validated DOCX was published, but some candidates remain unresolved or the auxiliary report could not be published. Exit code 0 includes PARTIAL results; check the status and review the document.

## Python API

```python
from docx_color_cli import color_revisions

result = color_revisions(
    "tracked.docx",
    "accepted.docx",
    "colored.docx",
    color="FF0000",
)

print(result["overall_status"])
```

## Validation

The coloring implementation has been tested on macOS, Ubuntu, and Windows with Python 3.11, 3.12, and 3.13:

- **macOS and Ubuntu:** 692 tests passed in each environment.
- **Windows:** 691 tests passed with one documented POSIX-specific permission-test skip in each environment.
- **Public example:** SUCCESS, 3,075 inserted characters colored, zero unresolved candidates, zero unauthorized color changes, and content fidelity PASS across all nine hosted environments using independently installed wheels.
- **Synthetic benchmark:** 36 independently authored scenarios, with 100% precision and 92.42% recall. Documented unsupported cases retain their expected insertion labels.

These measurements apply to the tested examples and synthetic corpus. They do not establish universal accuracy or replace a visual review in Word.

## Known Limitations

- Both inputs must represent the same document and revision state. Arbitrary document pairs are not supported.
- Ambiguous correspondence, some structural revisions, and complex field or mathematical changes may remain uncolored. The tool reports unresolved candidates rather than guessing.
- Strict OOXML documents are not supported. Exceptionally large or highly compressed packages may be rejected by safety limits.
- Avoid concurrent edits to inputs or outputs. DOCX and JSON report publication are separate operations, not one cross-file transaction.
- Always review the final document before submission, including equations and reference fields.

## License

[MIT](LICENSE).
