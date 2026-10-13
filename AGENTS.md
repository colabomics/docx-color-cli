# AGENTS.md — docx-color-cli development guide

## Mission and scope

`docx-color-cli` supports **DOCX → DOCX only**. It does not provide PDF output or
any other format conversion. Use Python 3.11+, `zipfile`, and `lxml`, with `uv`
for dependencies and `pytest` for tests. Runtime dependency: **only `lxml`**.

Do not introduce `python-docx`, `docx-revisions`, Microsoft Word automation, or
LibreOffice. A reference manually accepted and saved in Microsoft Word is allowed
as independent test evidence; normal tests must not require Word to be installed.

## Highest priority: content fidelity

Output content must match the final content displayed by Word's No Markup view.
No Markup is a display mode and cannot be implemented by blindly removing tags.
Content correctness outranks performance, simplicity, speed and appearance.

Only these intentional changes are allowed:

1. Retain inserted/replacement text and set font color to red (`FF0000`).
2. Retain unchanged text and set font color to black (`000000`).
3. Remove deleted content and accept revisions, including necessary structural
   changes when their semantics are reliably implemented.

Never lose, duplicate or reorder retained text. Preserve meaningful whitespace,
paragraph and cell boundaries, headings, lists, tables, images, equations,
hyperlinks, bookmarks, fields, cross-references, Zotero citations/bibliography,
footnotes/endnotes, headers/footers and content controls. Fields must remain
editable; do not flatten them into plain text. Preserve unrelated ZIP members,
relationships and content types. Explicitly authorized cleanup may remove image
relationships lost during acceptance and media proven unreferenced across the
package; update Content Types and validate the exact removal plan. Never overwrite the input document.

## Current phase boundary

Stage 3 **P0 repair is complete**. The subsequent explicitly requested whole
math-run revision support and math coloring are also complete; see
`docs/math_run_fix_report.md`. Ordinary nested insertion/deletion support was also
explicitly requested and completed; see `docs/nested_revision_report.md`.
Do not automatically start unrelated P1/P2/P3 work,
performance optimization, new CLI features or a product reference-validation mode.
A later explicit user task can authorize the next stage. Read
`docs/p0_fix_report.md` for implemented support versus safe refusal;
`docs/code_audit.md` retains the original pre-repair findings.

All unsafe revisions fail closed, including when legacy `--no-strict` is supplied.
Never restore that flag as an escape from content correctness. Supported ordinary
paragraph/row changes are accepted; cross-section/cell
marks, merged-cell row edits, conflicts and nested move containers are
refused. Ordinary nested ins/del, including whole math-run chains, is supported; deleted ancestry dominates.
The user subsequently authorized paragraph/cross-paragraph moves. These are
implemented for paired ranges with supported adjacent paragraph merges; see
`docs/paragraph_move_report.md`. Cross-cell/story ranges and shared moved content
remain rejected. Do not conflate XML endpoint overlap with shared content.
Do not describe a safety guard as implementation of that revision's semantics.
A local user-supplied Word reference is present under fixtures/academic. Different
paragraph properties now merge using the final surviving mark's complete pPr;
see `docs/paragraph_property_report.md`. Do not union properties or drop boundary
checks. The academic output is generated and all 641 paragraph texts/properties
and block boundaries match. Strict full comparison still fails on documented
CF019 differences (link representation and metadata). Empty math caused by
revision acceptance and comments losing their final anchor are now handled.
Do not claim complete fidelity or discard comments/fields to force equality.
Reference Word version remains unspecified.

## Repository map

- `src/docx_color_cli/cli.py`: orchestration, inline acceptance/colors, safe ZIP I/O and CLI.
- `src/docx_color_cli/revisions.py`: read-only revision policy and move preflight.
- `src/docx_color_cli/structure.py`: planned paragraph-mark and row transformations.
- `src/docx_color_cli/package.py`: production OPC/story checks and retention invariants;
  not a Word reference comparator or complete schema validator.
- `tests/fixtures/`: synthetic case data and optional independent Word pairs.
- `tests/helpers/`: fixture builders, logical comparisons, integrity assertions;
  no imports of the converter's revision algorithm.
- `tests/test_*.py`: behavior, known-defect regressions, helper self-tests and
  optional Word-reference tests.
- `docs/code_audit.md`: issue IDs, severity, locations and evidence.
- `docs/test_report.md`: counts, scope and unverified behavior.
- `docs/fix_plan.md`: later P0 → P1 → P2 → P3 work; not authorization to start it.

```bash
uv sync
uv run pytest -v
uv run pytest -v --runxfail
uv run docx-color input.docx output.docx --report report.json
```

## Testing rules

- For each suspected P0/P1 defect, create a minimal fixture and an independently
  specified expectation. Reproduce before repair; only change conversion semantics
  within the explicitly authorized issue scope, never to hide failing assertions.
- Use PASS for met expectations, FAIL for new/unexpected defects, strict XFAIL
  with issue ID and narrow expected exception for confirmed unresolved defects,
  and SKIP only for missing prerequisites such as independent Word references.
- Verify final text/order/colors, deletion absence and revision absence; not
  just file creation. Compare structural paragraphs/tables and OMML, not only
  flattened text. Check field codes/results and image XML/relationships/bytes.
- Keep comparison logic independent of revision acceptance. Do not generate
  expected output by calling the converter under test.
- Test helper positive controls and deliberate content mutations so a broken
  helper cannot report every case as a successful defect detection.
- Normal tests must be deterministic and portable across Linux/macOS/Windows,
  without network, absolute user paths, external random files or office apps.
- Never fabricate a Microsoft Word reference. Record manual provenance, Word
  version and SHA-256; reject incomplete pairs. Never commit confidential drafts
  or manuscript text as fixtures.
- Keep private pairs in the Git-ignored `tests/fixtures/academic/` directory.
  Never force-add them. The sdist allowlist must exclude manuscripts and generated
  artifacts even when those files are present locally. Check both wheel and
  sdist contents before release; preserve synthetic fixtures and regression tests.
- Test malformed ZIP/XML, unsupported revisions, invalid colors, equal paths,
  nonzero CLI exits, write failures, original preservation and temporary cleanup.
- Synthetic checks are not proof that Word opens without repair or renders an
  identical layout. Clearly record missing Word/reference/visual evidence.

## Rules for authorized repairs

Use the smallest structurally safe OOXML transformations. Distinguish run edits,
paragraph-mark edits, row/cell edits, moves and math control edits by context.
Keep current properties and discard historical snapshots without interpreting
them as active revisions. Reject unsupported/conflicting structures before
publishing output. Do not silently relax validation or use `--no-strict` as a fix.

Keep `--red`, `--black`, `--report` and safe path behavior compatible. Resolve and
samefile-check input/output/report pairs; publish only a validated temporary DOCX,
preserving existing output on failures. Report and DOCX publication are individually
atomic, not a cross-file transaction. Production code must never import tests.
Keep the test oracle independent from the conversion and production checks. Counts must
describe actual transformations. Run the full suite after repairs, review XPASS,
and update the audit, test report and user documentation. Stop at the requested
phase boundary.

## Authorized math-control deletion follow-up

Whole deleted objects are supported under the conservative policy in
`math_revisions.py`; see `docs/math_control_fix_report.md`. A deleted control
alone is insufficient: every run/nested object must be proven deleted. Surviving
parameters and unknown/non-text payload remain errors. Control insertion was subsequently explicitly authorized and implemented; see
`docs/math_control_insertion_report.md`. Color the inserted control only; argument
text follows its own revisions. Unknown/conflicting forms remain unsupported. Never weaken this proof or the independent reference oracle to
make the academic fixture pass.

## Authorized resource cleanup

See `docs/resource_cleanup_report.md` and `resources.py`. Prune only image
resources with proof that this conversion removed their explicit references.
All remaining package relationships pin targets, including opaque/unknown
sources. Literal XML filename mentions and compound parts are conservatively
retained. The later explicit task separately authorized comment cleanup under the rules
below; do not expand image cleanup to styles, embedded objects or unknown parts. Live resource bytes must stay unchanged; validate staged OPC and planned
ZIP membership before atomic publication.

## Authorized remaining-content follow-up

See `docs/final_content_cleanup_report.md`. Remove only math containers proven
empty as a consequence of accepted deletions, preserving original empties and
placeholders. Remove a comment only if this conversion removed its final active
reference; update matched extension records, relationships and Content Types.
Surviving threaded replies and unknown dependencies must fail closed. Preserve
people metadata and pre-existing orphan comments. Strict test comparison remains
the default; bounded semantic comparison is opt-in in tests, with negative
controls and explicit normalization warnings. Never ignore unknown field switches
or font signatures solely to pass the academic reference.

The explicitly requested HYPERLINK `\h` follow-up is complete; see
`docs/hyperlink_h_report.md`. MS-OE376 documents this as suppressing visited-link
history. Test-only semantic comparison recognizes a single trailing `\h` for
quoted HTTP(S) links and reports it, while preserving target/result/style checks.
Production retains the complete field and switch. Do not generalize this rule
to REF/TOC or unknown switches. The academic body now passes bounded semantic
comparison; font signatures still differ and strict full comparison still fails.
