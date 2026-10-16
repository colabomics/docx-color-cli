import json
from pathlib import Path

import pytest
from helpers.assertions import (
    assert_integrity,
    assert_segments,
    paragraphs,
    xml_part,
)
from helpers.fixtures import delete, insert, p, run

from docx_color_cli import color_revisions

CASES = json.loads(
    (Path(__file__).parent / "fixtures/basic/cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_text_revisions(docx, tmp_path, case):
    source = docx(
        "source.docx",
        p(
            "".join(
                {"text": run, "ins": insert, "del": delete}[op](value)
                for op, value in case["ops"]
            )
        ),
    )
    original = source.read_bytes()
    target = tmp_path / "output.docx"
    accepted = docx(
        "accepted.docx",
        p(
            "".join(
                run(value, '<w:color w:val="000000"/>') for value, _ in case["expected"]
            )
        ),
    )
    accepted_bytes = accepted.read_bytes()
    color_revisions(source, accepted, target)
    assert accepted.read_bytes() == accepted_bytes
    assert_segments(xml_part(target), case["expected"])
    assert paragraphs(target) == ["".join(value for value, _ in case["expected"])]
    assert source.read_bytes() == original
    assert_integrity(target)
