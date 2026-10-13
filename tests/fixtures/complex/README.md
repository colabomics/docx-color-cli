# Word reference pairs

No Word-generated documents are included. Ordinary tests use synthetic OOXML.

Optional cases belong under `word/<case-name>/` with `original.docx`,
`reference.docx`, and `provenance.json`. The original must contain actual Word
tracked revisions; the reference must be saved manually in Microsoft Word after
accepting all revisions, with no additional edits. Do not use this converter,
LibreOffice or synthetic XML to generate the reference.

`provenance.json` must contain `producer: "Microsoft Word"`, `word_version`,
`accepted_all_revisions: true`, `synthetic: false`, and SHA-256 values under
`original_sha256` and `reference_sha256`. Metadata records the human assertion of
provenance; tests cannot independently authenticate it.

Use public or deliberately authored non-confidential content. Do not commit real
manuscripts. Tests skip when no pair is present; incomplete pairs or malformed
provenance fail. Unsupported conversions are not silently skipped or automatically
xfail-marked. An explicitly reviewed case may later receive a defect-specific
strict xfail marker.
