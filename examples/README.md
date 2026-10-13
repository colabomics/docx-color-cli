# Synthetic manuscript example

This four-page, Nature-inspired manuscript contains approximately 1,450 words
in its accepted form. The title, author block, bold summary, main text, references,
table and Methods follow an abridged scholarly structure inspired by
[Nature’s formatting guide](https://www.nature.com/nature/for-authors/formatting-guide).
It is not an official template, publication or independently accepted Word reference.
All names, numerical values and bibliography entries are fictional.

## Files and usage

- [tracked.docx](tracked.docx): input with four authors’ tracked revisions.
- [colored.docx](colored.docx): actual output from the command below.

From the repository root:

```bash
uv run docx-color examples/tracked.docx examples/colored.docx
```

This replaces the included synthetic output file. No private manuscript is used.

## Revision coverage

The input contains **124 revision markers: 73 insertions and 51 deletions**.
A replacement contains a deletion and an insertion, so this count is not the
number of independent editorial decisions or Word review-pane entries.

| Fictional revising author | Revision markers |
| --- | ---: |
| Alex Example | 26 |
| Rowan Demo | 36 |
| Maya Test | 31 |
| Leo Sample | 31 |

Revisions cover the title, summary, narrative, numerical values, table cells,
references, Methods and declarations. The document also contains two native
OMML fractions, an editable synthetic Zotero-shaped citation field and a
HYPERLINK field with `\h`. The citation demonstrates field preservation; it is
not linked to a real Zotero library.

Validation checks exact retained characters and colors, deletion absence,
field codes/boundaries, equation text, paragraph/table counts and DOCX integrity.
This synthetic example is not proof of complete Microsoft Word equivalence.

## Preview images

The two images embedded in the main README show the first page of the actual
DOCX files, rendered using docx-preview 0.3.7 in headless Chrome. They are browser
screenshots, **not Microsoft Word screenshots**. Different fonts or renderers may
produce different pagination.

Before conversion, author colors are derived from each revision’s actual
`w:author` metadata, with underlined insertions and struck-through deletions.
After conversion, all retained inserted text is red and unchanged text is black,
regardless of the revising author. Output colors are read from the DOCX itself.

The local maintenance scripts `generate.py` and `render.js` are deliberately
Git-ignored and are not distributed. The example can be converted using only
the public input DOCX and the installed Python package.

Only these two explicitly named synthetic DOCX files are exempt from the Git
DOCX ignore rule. Private manuscripts and reference documents remain excluded.
