# Synthetic Nature-style demonstration

This abridged, two-page manuscript is original fictional content created for
`docx-color-cli`. It uses a title, author/affiliation block, bold summary,
numbered citation, main text, references, table and Methods, inspired by
[Nature's formatting guide](https://www.nature.com/nature/for-authors/formatting-guide).
It is not an official template, a publication, a submission-ready paper or a Word
reference. Names, data and the numbered reference are fictional. The citation is
a synthetic Zotero-shaped field for demonstrating field preservation.

- [tracked.docx](tracked.docx): actual tracked insertions and deletions.
- [colored.docx](colored.docx): actual CLI output, with inserted text red and
  unchanged text black.
- [generate.py](generate.py): deterministic DOCX builder using Python's standard library.
- [render.cjs](render.cjs): documentation-only browser screenshot script.

From the repository root:

```bash
python examples/nature-style/generate.py
uv run docx-color examples/nature-style/tracked.docx examples/nature-style/colored.docx
```

The output accepts seven insertions and removes six deletion containers. The
example also includes an editable citation field, a HYPERLINK field with `\h`,
a native OMML fraction and a revised table cell.

## Screenshot reproduction

The README images are screenshots of these DOCX files rendered by
[docx-preview](https://github.com/VolodymyrBaydalka/docxjs) in headless Chrome.
They show the first page with revisions visible before conversion and the
accepted colors afterwards. The renderer uses green underlines for insertions
and red strikethroughs for deletions in the input. The output colors are read
from the converted DOCX, not added to the screenshot.

These are browser previews, not Microsoft Word screenshots or a fidelity oracle.
The Node tools are optional documentation tooling and are not Python dependencies.
For example, on macOS with Google Chrome installed:

```bash
npm install --prefix /tmp/docx-readme-preview docx-preview@0.3.7 playwright@1.56.1
NODE_PATH=/tmp/docx-readme-preview/node_modules \
CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
node examples/nature-style/render.cjs
```

On other systems, set `CHROME_PATH` to a Chromium-compatible browser executable,
or install Playwright's Chromium and omit `CHROME_PATH`. Font availability can
change line wrapping. Browser page requests are blocked; document bytes and
renderer scripts are loaded locally.

Only the two named synthetic DOCX files are allowed through the repository's
DOCX ignore rule. Private papers and Word references remain excluded. These
example files and screenshots are repository documentation, not wheel contents.
