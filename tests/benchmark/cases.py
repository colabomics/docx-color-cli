"""Public benchmark selection from independently authored generic test truth."""

from dataclasses import dataclass, field

from helpers.corpus import INSERTED, UNCHANGED, Case, ins, p, run
from helpers.corpus import cases as ordinary_cases
from helpers.fidelity import W
from helpers.field_cases import cases as field_cases
from helpers.field_cases import relationships
from helpers.math_cases import cases as math_cases
from helpers.table_cases import cases as table_cases


@dataclass
class Scenario:
    case: Case
    origin: str
    expected_status: str = "SUCCESS"
    omission: str | None = None
    missed: int = 0
    controls: set = field(default_factory=set)
    tracked_parts: dict = field(default_factory=dict)
    accepted_parts: dict = field(default_factory=dict)
    extra_truth: dict = field(default_factory=dict)

    def paragraphs(self):
        return {"word/document.xml": self.case.expected, **self.extra_truth}

    def truth(self):
        result = {}
        for part, paragraphs in self.paragraphs().items():
            for pi, spans in enumerate(paragraphs):
                offset = 0
                for text, label in spans:
                    for _ in text:
                        result[part, pi, offset] = label
                        offset += 1
        return result

    def manifest(self):
        return {
            "id": self.case.ident,
            "description": self.case.name,
            "truth_source": self.origin,
            "evidence": "INDEPENDENTLY_AUTHORED_SYNTHETIC_NOT_WORD_REFERENCE",
            "tracked": f"{self.case.ident}/tracked.docx",
            "accepted": f"{self.case.ident}/accepted.docx",
            "expected_status": self.expected_status,
            "expected_fidelity": "NOT_APPLICABLE_NO_OUTPUT"
            if self.expected_status == "FAILED"
            else "PASS",
            "omission_reason": self.omission,
            "expected_false_negatives": self.missed,
            "inserted_math_controls": sorted(self.controls),
            "paragraphs": self.paragraphs(),
            "coordinates": "part / paragraph ordinal / Unicode code-point offset; controls: part / equation / control ordinal",
        }


def scenarios(*, include_tables=True):
    rows = []
    for c in ordinary_cases():
        if c.ident in {
            "S01",
            "S02",
            "S04",
            "S05",
            "S10",
            "S13",
            "S17",
            "S20",
            "S21",
            "S22",
        }:
            uncertain = c.ident == "S22"
            rows.append(
                Scenario(
                    c,
                    "helpers/corpus.py",
                    "PARTIAL" if uncertain else "SUCCESS",
                    "AMBIGUOUS_PROVENANCE" if uncertain else None,
                    4 if uncertain else 0,
                )
            )
    for c, _missed, uri in field_cases():
        if c.ident in {
            "format_only",
            "insert_and_format",
            "existing_colors",
            "native_link_insert",
            "link_representation",
            "field_container",
        }:
            rows.append(
                Scenario(
                    c,
                    "helpers/field_cases.py",
                    tracked_parts=relationships(),
                    accepted_parts=relationships(uri),
                )
            )
    for c, controls, missed, missed_controls in math_cases():
        if c.ident in {
            "math_whole",
            "math_variable",
            "math_fraction",
            "math_sum",
            "math_scripts",
            "math_original",
            "math_target_run_merged",
            "math_radical",
        }:
            assert missed_controls == 0
            rows.append(
                Scenario(
                    c,
                    "helpers/math_cases.py",
                    "PARTIAL" if missed else "SUCCESS",
                    "UNSUPPORTED_MATH_BOUNDARY" if missed else None,
                    missed,
                    {("word/document.xml", e, o) for e, o in controls},
                )
            )
    rows += [
        Scenario(
            Case(
                "paragraph_new",
                "new paragraph",
                p(run("old")) + p(ins("paragraph")),
                p(run("old")) + p(run("paragraph")),
                [[("old", UNCHANGED)], [("paragraph", INSERTED)]],
            ),
            "benchmark/cases.py",
        ),
        Scenario(
            Case(
                "styled_new",
                "bold and italic insertion",
                p(run("old ") + ins("new", props="<w:b/><w:i/>")),
                p(run("old ") + run("new", "<w:b/><w:i/>")),
                [[("old ", UNCHANGED), ("new", INSERTED)]],
            ),
            "benchmark/cases.py",
        ),
    ]
    for ident, part, tag, reference in [
        ("header_text", "word/header1.xml", "hdr", "header"),
        ("note_text", "word/footnotes.xml", "footnotes", "footnotes"),
    ]:

        def story(payload, tag=tag):
            content = p(payload)
            if tag == "footnotes":
                content = '<w:footnote w:id="1">' + content + "</w:footnote>"
            return f'<w:{tag} xmlns:w="{W[1:-1]}">{content}</w:{tag}>'

        body = p(
            run("body")
            + (
                '<w:r><w:footnoteReference w:id="1"/></w:r>'
                if reference == "footnotes"
                else ""
            )
        )
        if reference == "header":
            body += '<w:sectPr><w:headerReference w:type="default" r:id="story"/></w:sectPr>'
        extra = {
            "word/_rels/document.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="story" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            + reference
            + '" Target="'
            + part.removeprefix("word/")
            + '"/></Relationships>'
        }
        rows.append(
            Scenario(
                Case(ident, "story insertion", body, body, [[("body", UNCHANGED)]]),
                "benchmark/cases.py",
                tracked_parts={**extra, part: story(run("old ") + ins("new"))},
                accepted_parts={**extra, part: story(run("old new"))},
                extra_truth={part: [[("old ", UNCHANGED), ("new", INSERTED)]]},
            )
        )
    rows.append(
        Scenario(
            Case(
                "invalid_pair",
                "incompatible pair",
                p(ins("alpha")),
                p(run("unrelated")),
                [[("unrelated", "UNKNOWN_INVALID_PAIR")]],
            ),
            "benchmark/cases.py",
            "FAILED",
            "INVALID_DOCUMENT_PAIR",
        )
    )
    rows.append(
        Scenario(
            Case(
                "block_boundary",
                "unsupported block boundary",
                '<w:ins w:id="101">' + p(run("Delta")) + "</w:ins>",
                p(run("Delta")),
                [[("Delta", INSERTED)]],
            ),
            "benchmark/cases.py",
            "PARTIAL",
            "UNSUPPORTED_STRUCTURAL_BOUNDARY",
            5,
        )
    )
    assert len(rows) == 30
    if include_tables:
        selected = {
            "table_simple",
            "table_multiple",
            "table_repeated",
            "table_merged",
            "table_nested",
            "table_property_siblings",
        }
        for case, missed, invalid in table_cases():
            if case.ident in selected:
                assert not missed and not invalid
                rows.append(Scenario(case, "helpers/table_cases.py"))
    return rows
