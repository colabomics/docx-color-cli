# AGENTS.md — docx-color-cli

## 1. Mission

`docx-color-cli` is a lightweight, cross-platform Python tool for coloring
newly inserted text in Microsoft Word documents.

The user provides:

1. **Tracked DOCX** — a document containing Microsoft Word Track Changes.
2. **Accepted DOCX** — the same document after all revisions have been
   accepted in Microsoft Word.

The tool produces:

3. **Colored DOCX** — a copy of the Accepted DOCX with newly inserted
   text colored red (`FF0000`) by default.

Core workflow:

    Tracked DOCX + Accepted DOCX → Colored DOCX

The Accepted DOCX is the single source of truth for final document
content, structure, and formatting.

The Tracked DOCX is used only to identify revision provenance.

Do not implement Word's Accept All Changes functionality.
Do not reconstruct the final document from the Tracked DOCX.


## 2. Highest Priorities

The following priorities define the project's success criteria.

### P0 — Content Fidelity

**The Colored DOCX must always contain exactly the same logical content
and document structure as the Accepted DOCX.**

Formally:

    Content(Colored DOCX) == Content(Accepted DOCX)

Only the font color of newly inserted text may intentionally change.

Necessary run splitting is allowed if it preserves all logical content,
document structure, and unrelated formatting.

Never:

- Add, remove, duplicate, or reorder text.
- Change meaningful whitespace.
- Alter paragraph, table, or section boundaries.
- Modify equations, images, drawings, or other non-text objects.
- Modify hyperlinks, bookmarks, cross-references, or comments.
- Modify field codes, field results, or Zotero citations.
- Modify styles, numbering, headers, footers, footnotes, or endnotes.
- Modify unrelated XML elements, attributes, or relationships.

Validate content and structural equivalence before publishing output.

**If equivalence cannot be established, abort without publishing
or overwriting the destination file.**

### P1 — Coloring Completeness

**Every surviving inserted character should be identified and colored.**

Missing inserted text is a major functional defect, not merely an
acceptable limitation.

The implementation must actively investigate unmapped insertions rather
than excluding them through overly conservative rules.

Target:

    Coloring Recall >= 99%

This is a development target, not permission to guess uncertain mappings.

Measure recall at the character level.

Report all missed, ambiguous, and unsupported inserted characters.

Do not artificially increase recall by narrowing the denominator.

Do not silently publish an incompletely colored document as if it were
fully processed.

### P2 — Coloring Precision

**Never incorrectly color unchanged text.**

Target:

    Coloring Precision = 100%

Use deterministic, evidence-based correspondence between the Tracked
and Accepted DOCX.

Do not:

- Use global substring replacement.
- Color every occurrence of repeated text.
- Select arbitrary matches to increase coverage.
- Ignore structural boundaries.
- Invent revision provenance.

When a mapping is ambiguous, investigate alternative structural anchors
and alignment strategies before declaring it unsupported.

Never sacrifice coloring precision to improve recall.

### Overall Principle

**Preserve all content. Color all inserted text. Never color the wrong text.**

Content fidelity, coloring completeness, and coloring precision are all
required for production-quality results.


## 3. Architecture and Alignment

Use revision-guided text alignment:

    Tracked DOCX
         |
         v
    Extract insertion provenance
         |
         v
    Construct final-text projection
         |
         v
    Align with Accepted DOCX
         |
         v
    Map inserted characters
         |
         v
    Apply font colors to Accepted DOCX
         |
         v
    Validate content and formatting
         |
         v
    Publish Colored DOCX

Prefer:

1. Exact structural correspondence.
2. Unique paragraph or region anchors.
3. Exact matching within corresponding regions.
4. Character-level sequence alignment.
5. Bounded local alignment when necessary.

Microsoft Word may reorganize runs, paragraphs, and XML structures when
accepting revisions.

Do not assume that run indices, paragraph indices, or XML node positions
remain identical between the two documents.

Mapping results should distinguish:

- EXACT
- ALIGNED
- AMBIGUOUS
- UNMAPPED
- UNSUPPORTED

Only reliably mapped inserted text may be recolored.

Do not build a general-purpose OOXML revision acceptance engine.

Prefer simple, generalizable alignment algorithms over document-specific
heuristics or unnecessary abstractions.


## 4. Coloring and Document Integrity

### Coloring

Default inserted-text color:

    FF0000

Only text originating from tracked insertions and surviving in the
Accepted DOCX should be recolored.

Do not color text affected only by formatting revisions.

Preserve unchanged text and all unrelated formatting, including:

- Font family and size
- Bold, italic, underline, and strikethrough
- Superscript and subscript
- Character spacing and language
- Theme formatting
- Existing colors of unchanged text

If a run contains both inserted and unchanged text, split it only when
necessary and safe.

Never lose text, whitespace, or formatting during run splitting.

### Document Integrity

Both input DOCX files are immutable.

The output must be based directly on the Accepted DOCX.

The tool must:

1. Preserve unrelated ZIP members.
2. Preserve document relationships and content types.
3. Preserve tables, equations, images, fields, and citations.
4. Preserve all logical text and document structure.
5. Modify only the required text-color properties.
6. Validate the resulting DOCX before publication.

Write output to a temporary file and publish only after validation.

On failure:

- Never modify either input.
- Never overwrite an existing output.
- Remove temporary files.
- Return a clear error.

Byte-for-byte equality of entire DOCX archives is not required because
XML serialization and run splitting may differ.

However, logical content, document structure, and unrelated formatting
must remain equivalent to the Accepted DOCX.


## 5. Technical and Testing Requirements

### Technology

- Python 3.11+
- Dependency management: `uv`
- DOCX processing: `zipfile` and `lxml`
- Runtime dependency: preferably only `lxml`
- Testing: `pytest`
- Linting and formatting: `ruff`

The tool should run on Windows, macOS, and Linux.

Microsoft Word is not required at runtime because the user supplies
an already accepted DOCX.

Do not introduce Microsoft Word automation, LibreOffice, `python-docx`,
or unnecessary runtime dependencies without explicit authorization.

### Testing

Prioritize real-world coloring correctness over the number of tests.

Tests must cover:

- Insertions, deletions, and replacements
- Multiple authors and revisions
- Repeated words and sentences
- Different run boundaries
- Mixed inserted and unchanged text
- Unicode, Chinese text, and whitespace
- Existing text colors and formatting
- Paragraph and table changes
- Equations, hyperlinks, fields, and citations
- Ambiguous and unsupported mappings
- Input integrity and safe output publication

For each conversion, verify:

1. Output content equals Accepted DOCX content.
2. Text order and meaningful whitespace are unchanged.
3. Document structure and unrelated formatting are preserved.
4. Inserted text is colored correctly.
5. Unchanged text is not recolored.
6. Both input files remain unchanged.
7. No unrelated ZIP members or relationships are modified.

Use independent test expectations.

Never generate expected results using the converter being tested.

Synthetic tests are not independent Microsoft Word ground truth.

Do not claim zero false coloring on real documents without
independent evidence.

Private academic DOCX files must remain Git-ignored.

Never modify, commit, distribute, or include private manuscripts
in reports or build artifacts.

Before completing development work, run:

    uv run pytest -q
    uv run ruff check .
    uv run ruff format --check .

Report failures, skipped tests, and unverified behavior honestly.


## 6. Development and Release Rules

### Development

- Keep the code simple, focused, and maintainable.
- Prefer minimal local XML modifications.
- Avoid unnecessary abstractions and special cases.
- Do not expand into a general OOXML revision engine.
- Improve alignment completeness without sacrificing correctness.
- Maintain independent content-fidelity validation.
- Do not modify unrelated files.
- Preserve existing public APIs unless explicitly authorized.

### Git and Release Safety

This project has an explicitly gated publishing workflow.

Therefore:

- Never change the package version without explicit authorization.
- Never create release tags automatically.
- Never push to GitHub without explicit authorization.
- Never merge branches automatically.
- Never publish to PyPI automatically.
- Never discard uncommitted user changes.
- Never restore intentionally deleted files.
- Never commit private DOCX files or temporary artifacts.

Local commits are allowed only when requested or explicitly authorized.

Always inspect Git status before major modifications.


## 7. Current Development Focus

Maintain the supported package under `src/docx_color_cli/` and current tests
under `tests/`. Independent, public synthetic truth and validation oracles live
under `tests/helpers/` and `tests/benchmark/`.

Do not retain duplicate runtime implementations or manuscript-derived fixtures.
Private inputs and unique local evidence must remain outside public Git content.
Use the Accepted-authoritative workflow and preserve all validated behavior.

Do not begin algorithm research or publication without explicit authorization.


## Ultimate Goal

Build a simple, reliable, cross-platform DOCX coloring tool.

    tracked.docx + accepted.docx → colored.docx

The Colored DOCX must preserve exactly the same logical content and
document structure as the Accepted DOCX.

The goal is to color every surviving inserted character accurately,
without modifying anything else.

**Preserve everything. Miss nothing. Color only what was inserted.**