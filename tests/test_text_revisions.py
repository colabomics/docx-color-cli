import json
from pathlib import Path

import pytest
from helpers.assertions import (
    assert_integrity,
    assert_rejects_without_output,
    assert_segments,
    paragraphs,
    xml_part,
)
from helpers.fixtures import delete, insert, p, revision, run

from docx_color_cli.cli import convert

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
    convert(source, target)
    assert_segments(xml_part(target), case["expected"])
    assert paragraphs(target) == ["".join(value for value, _ in case["expected"])]
    assert source.read_bytes() == original
    assert_integrity(target)


def test_T013_simple_paired_move(docx, tmp_path):
    body = p(
        '<w:moveFromRangeStart w:id="1" w:name="move1"/>'
        + revision("moveFrom", run("moved"))
        + '<w:moveFromRangeEnd w:id="1"/>'
        + run("stay ")
        + '<w:moveToRangeStart w:id="2" w:name="move1"/>'
        + revision("moveTo", run("moved"), "2")
        + '<w:moveToRangeEnd w:id="2"/>'
    )
    target = tmp_path / "out.docx"
    convert(docx("source.docx", body), target)
    assert paragraphs(target) == ["stay moved"]
    assert_segments(xml_part(target), [("stay ", "000000"), ("moved", "FF0000")])
    assert_integrity(target)


@pytest.mark.parametrize(
    "content,expected",
    [
        (revision("ins", delete("ambiguous")), []),
        (revision("del", insert("ambiguous")), []),
        (revision("ins", insert("nested")), [("nested", "FF0000")]),
    ],
    ids=["ins-del", "del-ins", "ins-ins"],
)
def test_CF006_nested_revisions_accepted(docx, tmp_path, content, expected):
    target = tmp_path / "out.docx"
    convert(docx("source.docx", p(content)), target)
    assert_segments(xml_part(target), expected)
    assert_integrity(target)


def test_CF006_office_conflict_refused(docx, tmp_path):
    content = "<w14:conflictDel>" + run("conflict") + "</w14:conflictDel>"
    assert_rejects_without_output(
        convert, docx("source.docx", p(content)), tmp_path / "out.docx"
    )


@pytest.mark.parametrize(
    "content",
    [
        revision("moveTo", run("unpaired")),
        '<w:moveFromRangeStart w:id="1" w:name="m"/>'
        + run("source")
        + '<w:moveFromRangeEnd w:id="1"/>',
        '<w:pPr><w:rPr><w:moveFrom w:id="1"/></w:rPr></w:pPr>' + run("A"),
    ],
    ids=["unpaired", "range-only", "paragraph-mark"],
)
def test_CF007_unsupported_moves(docx, tmp_path, content):
    assert_rejects_without_output(
        convert, docx("source.docx", p(content)), tmp_path / "out.docx"
    )


def test_CF011_custom_xml_range(docx, tmp_path):
    body = p(
        '<w:customXmlMoveFromRangeStart w:id="1"/>'
        + run("content")
        + '<w:customXmlMoveFromRangeEnd w:id="1"/>'
    )
    assert_rejects_without_output(
        convert, docx("source.docx", body), tmp_path / "out.docx"
    )


def test_CF018_discarded_insertions_not_counted(docx, tmp_path):
    stats = convert(
        docx("source.docx", p(revision("del", insert("gone")) + run("keep"))),
        tmp_path / "out.docx",
    )
    assert stats.get("accepted_ins", 0) == 0
