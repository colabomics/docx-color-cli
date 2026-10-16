"""Synthetic truth is authored per character, never claimed as a Word oracle."""

import json
from copy import deepcopy
from hashlib import sha256
from zipfile import ZipFile

import pytest
from lxml import etree

from docx_color_cli import ColoringError
from docx_color_cli.accepted import Package
from docx_color_cli.alignment import unique_lcs
from docx_color_cli.cli import main
from docx_color_cli.engine import convert
from docx_color_cli.extract import attach_offsets, extract
from docx_color_cli.projection import M, W, paragraphs

R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = W[1:-1]


def run(text, props=""):
    node = etree.Element(W + "r")
    if props:
        node.append(etree.fromstring(f'<w:rPr xmlns:w="{NS}">{props}</w:rPr>'))
    t = etree.SubElement(
        node, W + "t", {"{http://www.w3.org/XML/1998/namespace}space": "preserve"}
    )
    t.text = text
    return etree.tostring(node).decode()


def ins(text, ident="1", author="Test A"):
    return f'<w:ins w:id="{ident}" w:author="{author}" w:date="2026-01-01T00:00:00Z">{run(text)}</w:ins>'


def delete(text):
    return (
        '<w:del w:id="2">'
        + run(text).replace(":t ", ":delText ").replace(":t>", ":delText>")
        + "</w:del>"
    )


def p(content, props=""):
    return (
        "<w:p>" + ("<w:pPr>" + props + "</w:pPr>" if props else "") + content + "</w:p>"
    )


def table(content, props=""):
    return (
        '<w:tbl><w:tblGrid><w:gridCol w:w="2400"/></w:tblGrid><w:tr>'
        + props
        + "<w:tc>"
        + content
        + "</w:tc></w:tr></w:tbl>"
    )


def docx(path, body, extras=None):
    members = {
        "word/document.xml": f'<w:document xmlns:w="{NS}" xmlns:m="{M[1:-1]}" xmlns:r="{R}"><w:body>{body}</w:body></w:document>',
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="bin" ContentType="application/octet-stream"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="main" Type="{R}/officeDocument" Target="word/document.xml"/></Relationships>',
        **(extras or {}),
    }
    with ZipFile(path, "w") as archive:
        archive.comment = b"preserve-archive-comment"
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def chars(path):
    from helpers.fidelity import characters, read_package

    return [
        (c.text, dict(c.color[0][1]).get(W + "val") if c.color else None)
        for c in characters(read_package(path)[1]).values()
    ]


def verify_case(
    tmp_path, tracked, accepted, text, inserted, *, colors=None, pair_rejected=False
):
    a, b, out = [
        tmp_path / name for name in ("tracked.docx", "accepted.docx", "colored.docx")
    ]
    docx(a, tracked)
    docx(
        b,
        accepted,
        {
            "customXml/keep.xml": '<metadata preserve="true"/>',
            "word/media/keep.bin": b"opaque",
        },
    )
    before = [sha256(x.read_bytes()).digest() for x in (a, b)]
    if pair_rejected:
        from collections import Counter

        from docx_color_cli.alignment import align
        from docx_color_cli.coloring import prepare

        with pytest.raises(ColoringError) as caught:
            convert(a, b, out)
        assert caught.value.code == "INVALID_DOCUMENT_PAIR"
        assert not out.exists()
        source, target = Package(a), Package(b, accepted=True)
        records, _ = extract(source)
        projected = paragraphs(source, records)
        attach_offsets(records, projected)
        mappings, evidence = align(
            projected, target.paragraphs, records, accepted_xml=target.xml
        )
        selected = prepare(mappings, target.paragraphs)
        locations = [loc for para in target.paragraphs for loc in para.locations]
        assert "".join(para.text for para in target.paragraphs) == text
        assert {
            i
            for i, (node, offset) in enumerate(locations)
            if offset in selected.get(node, ())
        } == inserted
        assert [sha256(x.read_bytes()).digest() for x in (a, b)] == before
        counts = Counter(m.status for m in mappings)
        return {
            "publication_status": "FAILED",
            "mapping_evidence_counts": dict(Counter(m.evidence for m in mappings)),
            "mapping": {
                **{
                    status.lower() + "_characters": counts[status]
                    for status in [
                        "EXACT",
                        "ALIGNED",
                        "UNMAPPED",
                        "AMBIGUOUS",
                        "UNSUPPORTED",
                    ]
                },
                **evidence,
            },
        }
    report = convert(a, b, out)
    observed = chars(out)
    assert "".join(c for c, _ in observed) == text
    expected_colors = colors or [None] * len(text)
    assert [color for _, color in observed] == [
        "FF0000" if i in inserted else expected_colors[i] for i in range(len(text))
    ]
    assert [sha256(x.read_bytes()).digest() for x in (a, b)] == before
    assert report["coloring"]["characters_colored"] == len(inserted)
    assert all(
        report["integrity"][k]
        for k in (
            "zip_valid",
            "xml_valid",
            "accepted_text_preserved",
            "input_hashes_unchanged",
            "complex_objects_preserved",
        )
    )
    return report


CASES = [
    (
        "single-word",
        p(run("The ") + ins("new") + run(" model")),
        p(run("The new model")),
        "The new model",
        set(range(4, 7)),
    ),
    (
        "deletion",
        p(run("A ") + delete("bad ") + run("result")),
        p(run("A result")),
        "A result",
        set(),
    ),
    (
        "replacement",
        p(run("A ") + delete("bad") + ins("good") + run(" result")),
        p(run("A good result")),
        "A good result",
        set(range(2, 6)),
    ),
    (
        "multiple-authors",
        p(ins("A", "7", "Alice") + run("-") + ins("B", "7", "Bob")),
        p(run("A-B")),
        "A-B",
        {0, 2},
    ),
    (
        "repeated-word",
        p(run("model ") + ins("model") + run(" model")),
        p(run("model model model")),
        "model model model",
        set(range(6, 11)),
    ),
    (
        "repeated-sentence",
        p(run("Same. ") + ins("Same.") + run(" Same.")),
        p(run("Same. Same. Same.")),
        "Same. Same. Same.",
        set(range(6, 11)),
    ),
    ("punctuation", p(run("A") + ins(",") + run(" B.")), p(run("A, B.")), "A, B.", {1}),
    (
        "spaces",
        p(run("a") + ins("  x ") + run("b")),
        p(run("a  x b")),
        "a  x b",
        {1, 2, 3, 4},
    ),
    (
        "unicode",
        p(run("α ") + ins("e\u0301🚀") + run(" β")),
        p(run("α e\u0301🚀 β")),
        "α e\u0301🚀 β",
        {2, 3, 4},
    ),
    (
        "chinese",
        p(run("结果") + ins("显著") + run("改善。")),
        p(run("结果显著改善。")),
        "结果显著改善。",
        {2, 3},
    ),
    (
        "split-source-runs",
        p('<w:ins w:id="1">' + run("new") + run(" text") + "</w:ins>"),
        p(run("new text")),
        "new text",
        set(range(8)),
    ),
    (
        "split-accepted-runs",
        p(run("a") + ins("new") + run("b")),
        p(run("an") + run("e") + run("wb")),
        "anewb",
        {1, 2, 3},
    ),
    (
        "multiple-text-nodes",
        p(
            '<w:ins w:id="1"><w:r><w:t>two</w:t><w:t xml:space="preserve"> nodes</w:t></w:r></w:ins>'
        ),
        p(run("two nodes")),
        "two nodes",
        set(range(9)),
    ),
    (
        "table-cell",
        table(p(run("cell ") + ins("new"))),
        table(p(run("cell new"))),
        "cell new",
        {5, 6, 7},
    ),
    (
        "paragraph-insertion",
        p(run("old")) + p(ins("new"), '<w:rPr><w:ins w:id="4"/></w:rPr>'),
        p(run("old")) + p(run("new")),
        "oldnew",
        {3, 4, 5},
    ),
    (
        "paragraph-deletion-unsupported",
        p(delete("old"), '<w:rPr><w:del w:id="4"/></w:rPr>') + p(ins("new")),
        p(run("new")),
        "new",
        set(),
    ),
    (
        "formula-adjacent",
        p("<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>" + ins(" new")),
        p("<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>" + run(" new")),
        "x new",
        {1, 2, 3, 4},
    ),
    (
        "field-adjacent",
        p('<w:fldSimple w:instr="PAGE">' + run("1") + "</w:fldSimple>" + ins(" new")),
        p('<w:fldSimple w:instr="PAGE">' + run("1") + "</w:fldSimple>" + run(" new")),
        "1 new",
        {1, 2, 3, 4},
    ),
    (
        "hyperlink-display",
        p(
            '<w:hyperlink w:anchor="target">'
            + run("old")
            + ins("new")
            + "</w:hyperlink>"
        ),
        p('<w:hyperlink w:anchor="target">' + run("oldnew") + "</w:hyperlink>"),
        "oldnew",
        {3, 4, 5},
    ),
    (
        "format-after-insert",
        p(
            '<w:ins w:id="1">'
            + run(
                "new", '<w:b/><w:rPrChange w:id="3"><w:rPr><w:i/></w:rPr></w:rPrChange>'
            )
            + "</w:ins>"
        ),
        p(run("new", "<w:b/>")),
        "new",
        {0, 1, 2},
    ),
    (
        "subsequently-deleted",
        p('<w:del w:id="2">' + ins("gone") + "</w:del>" + run("stay")),
        p(run("stay")),
        "stay",
        set(),
    ),
    (
        "nested-deletion",
        p('<w:ins w:id="1">' + run("n") + delete("gone") + run("ew") + "</w:ins>"),
        p(run("new")),
        "new",
        {0, 1, 2},
    ),
    ("no-insertions", p(run("plain")), p(run("plain")), "plain", set()),
    (
        "noncorresponding",
        p(run("A ") + ins("new")),
        p(run("Entirely different")),
        "Entirely different",
        set(),
    ),
    (
        "repeated-paragraphs",
        p(run("same")) + p(ins("same")),
        p(run("same")) + p(run("same")),
        "samesame",
        set(),
    ),
    (
        "many-identical",
        p(run("same")) * 49 + p(ins("same")),
        p(run("same")) * 50,
        "same" * 50,
        set(),
    ),
    (
        "table-structure-unsupported",
        table(p(ins("new")), '<w:trPr><w:ins w:id="2"/></w:trPr>'),
        table(p(run("new"))),
        "new",
        set(),
    ),
    (
        "complex-mixed-run",
        p(run("old") + ins("new")),
        p(
            '<w:r><w:t>oldnew</w:t><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
        ),
        "oldnew",
        set(),
    ),
]


@pytest.mark.parametrize(
    "name,tracked,accepted,text,inserted", CASES, ids=[c[0] for c in CASES]
)
def test_known_character_provenance(tmp_path, name, tracked, accepted, text, inserted):
    report = verify_case(
        tmp_path,
        tracked,
        accepted,
        text,
        inserted,
        pair_rejected=name == "noncorresponding",
    )
    if "unsupported" in name or name == "complex-mixed-run":
        assert report["mapping"]["unsupported_characters"] > 0
    if name in {"repeated-paragraphs", "many-identical"}:
        assert report["mapping"]["ambiguous_characters"] == 4
    if name == "noncorresponding":
        assert report["mapping"]["unmapped_characters"] == 3


def test_existing_color_and_full_run_format(tmp_path):
    props = '<w:rFonts w:ascii="Cambria"/><w:b/><w:i/><w:u w:val="single"/><w:color w:val="123456" w:themeColor="accent1"/><w:spacing w:val="2"/><w:sz w:val="24"/><w:vertAlign w:val="superscript"/><w:lang w:val="en-US"/>'
    report = verify_case(
        tmp_path,
        p(run("The ") + ins("new") + run(" model")),
        p(run("The new model", props)),
        "The new model",
        {4, 5, 6},
        colors=["123456"] * 13,
    )
    assert report["coloring"]["runs_split"] == 1
    root = Package(tmp_path / "colored.docx", accepted=True).xml["word/document.xml"]
    assert len(list(root.iter(W + "r"))) == 3
    for node in root.iter(W + "rPr"):
        assert node.find(W + "rFonts").get(W + "ascii") == "Cambria"
        assert node.find(W + "sz").get(W + "val") == "24"


def test_anchored_local_alignment(tmp_path):
    report = verify_case(
        tmp_path,
        p(run("left anchor"))
        + p(run("The ") + ins("new") + run(" model"))
        + p(run("right anchor")),
        p(run("left anchor")) + p(run("The new model!")) + p(run("right anchor")),
        "left anchorThe new model!right anchor",
        {15, 16, 17},
        pair_rejected=True,
    )
    assert report["mapping"]["aligned_characters"] == 3


def test_all_optimal_alignment_refuses_repeated_occurrence(tmp_path):
    report = verify_case(
        tmp_path,
        p(run("left")) + p(ins("x")) + p(run("right")),
        p(run("left")) + p(run("xx")) + p(run("right")),
        "leftxxright",
        set(),
        pair_rejected=True,
    )
    assert report["mapping"]["ambiguous_characters"] == 1


def test_lcs_can_omit_inserted_character():
    assert unique_lcs("aa", "a") == [("AMBIGUOUS", None), ("AMBIGUOUS", None)]
    assert unique_lcs("x", "xx") == [("AMBIGUOUS", None)]
    assert unique_lcs("abc", "ab!c") == [("ALIGNED", 0), ("ALIGNED", 1), ("ALIGNED", 3)]
    assert unique_lcs("a" * 600, "a" * 600) is None


def test_extraction_metadata_offsets_and_duplicate_ids(tmp_path):
    package = Package(
        docx(
            tmp_path / "a.docx",
            p(ins("AB", "7", "Alice") + run("-") + ins("CD", "7", "Bob")),
        )
    )
    records, stats = extract(package)
    projected = paragraphs(package, records)
    attach_offsets(records, projected)
    a, b = records.values()
    assert stats["insertion_containers"] == 2
    assert a.key != b.key and a.revision_id == b.revision_id == "7"
    assert (a.author, b.author) == ("Alice", "Bob")
    assert a.date == "2026-01-01T00:00:00Z"
    assert a.text == "AB" and a.paragraph == 0
    assert [(span[1], span[2]) for span in a.spans] == [(0, 2)]
    assert [(span[1], span[2]) for span in b.spans] == [(3, 5)]
    assert a.structural_context == ()


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
@pytest.mark.parametrize("victim", ["tracked", "accepted"])
def test_input_alias_protection(tmp_path, alias, victim):
    import os

    a = docx(tmp_path / "tracked.docx", p(ins("x")))
    b = docx(tmp_path / "accepted.docx", p(run("x")))
    source = a if victim == "tracked" else b
    out = source
    if alias != "same":
        out = tmp_path / "alias.docx"
        if alias == "symlink":
            out.symlink_to(source)
        else:
            os.link(source, out)
    before = source.read_bytes()
    with pytest.raises(ValueError, match="distinct regular files"):
        convert(a, b, out)
    assert source.read_bytes() == before


def test_existing_output_replaced_only_after_validation(tmp_path, monkeypatch):
    from docx_color_cli import engine as cli

    a = docx(tmp_path / "a.docx", p(ins("new")))
    b = docx(tmp_path / "b.docx", p(run("new")))
    output = tmp_path / "out.docx"
    output.write_bytes(b"previous output")
    validation = cli.validate_output

    def fail(*args):
        raise ValueError("injected validation failure")

    monkeypatch.setattr(cli, "validate_output", fail)
    with pytest.raises(ValueError, match="content-fidelity validation failed"):
        convert(a, b, output)
    assert output.read_bytes() == b"previous output"
    monkeypatch.setattr(cli, "validate_output", validation)
    convert(a, b, output)
    assert chars(output) == [("n", "FF0000"), ("e", "FF0000"), ("w", "FF0000")]


@pytest.mark.parametrize("damage", ["zip", "xml", "residual-revision", "relationship"])
def test_invalid_inputs_no_publication(tmp_path, damage):
    a = docx(tmp_path / "a.docx", p(ins("new")))
    extras = {"word/document.xml": "<broken>"} if damage == "xml" else None
    b = docx(
        tmp_path / "b.docx",
        p(
            ins("new")
            if damage == "residual-revision"
            else '<w:hyperlink r:id="missing">' + run("new") + "</w:hyperlink>"
            if damage == "relationship"
            else run("new")
        ),
        extras,
    )
    if damage == "zip":
        b.write_bytes(b"not a zip")
    output = tmp_path / "out.docx"
    assert main([str(a), str(b), str(output)]) == 1
    assert not output.exists()


def test_report_has_no_text_and_custom_color(tmp_path):
    secret = "Private manuscript phrase"
    a = docx(tmp_path / "a.docx", p(ins(secret)))
    b = docx(tmp_path / "b.docx", p(run(secret)))
    out, report = tmp_path / "out.docx", tmp_path / "report.json"
    assert (
        main(
            [
                str(a),
                str(b),
                str(out),
                "--color",
                "00ff00",
                "--report",
                str(report),
            ]
        )
        == 0
    )
    assert secret not in report.read_text()
    assert all(color == "00FF00" for _, color in chars(out))
    assert json.loads(report.read_text())["integrity"]["input_hashes_unchanged"]


def test_validation_detects_wrong_color_text_and_formatting(tmp_path):
    from docx_color_cli.validation import events

    original = Package(docx(tmp_path / "b.docx", p(run("original", "<w:b/>")))).xml[
        "word/document.xml"
    ]
    for tag in ("color", "text", "bold"):
        altered = deepcopy(original)
        if tag == "color":
            etree.SubElement(
                altered.find(".//" + W + "rPr"), W + "color", {W + "val": "FF0000"}
            )
        elif tag == "text":
            altered.find(".//" + W + "t").text = "changed"
        else:
            bold = altered.find(".//" + W + "b")
            bold.getparent().remove(bold)
        assert events(original) != events(altered)


def test_lcs_evidence_matches_exhaustive_alignment_oracle():
    """Enumerate all alignments independently, including omission alternatives."""
    from functools import lru_cache
    from itertools import product

    strings = [
        "".join(chars) for size in range(4) for chars in product("ab", repeat=size)
    ]
    for left in strings:
        for right in strings:

            @lru_cache(None)
            def enumerate_paths(i, j, left=left, right=right):
                if i == len(left) or j == len(right):
                    return {()}
                choices = enumerate_paths(i + 1, j) | enumerate_paths(i, j + 1)
                if left[i] == right[j]:
                    choices |= {
                        ((i, j), *tail) for tail in enumerate_paths(i + 1, j + 1)
                    }
                longest = max(map(len, choices))
                return {path for path in choices if len(path) == longest}

            paths = enumerate_paths(0, 0)
            expected = []
            for i in range(len(left)):
                destinations = {dict(path).get(i) for path in paths}
                if len(destinations) == 1 and None not in destinations:
                    expected.append(("ALIGNED", next(iter(destinations))))
                elif destinations == {None}:
                    expected.append(("UNMAPPED", None))
                else:
                    expected.append(("AMBIGUOUS", None))
            assert unique_lcs(left, right) == expected


def test_zip_zero_external_attributes_preserved(tmp_path):
    a = docx(tmp_path / "a.docx", p(ins("new")))
    b = docx(tmp_path / "b.docx", p(run("new")))
    with ZipFile(b) as source:
        entries = [(info, source.read(info)) for info in source.infolist()]
    with ZipFile(b, "w") as target:
        for info, data in entries:
            target.writestr(info, data)
            info.external_attr = 0
    out = tmp_path / "out.docx"
    convert(a, b, out)
    with ZipFile(out) as archive:
        assert all(info.external_attr == 0 for info in archive.infolist())


def test_block_insertion_is_reported_unsupported(tmp_path):
    report = verify_case(
        tmp_path,
        '<w:ins w:id="1">' + p(run("new")) + "</w:ins>",
        p(run("new")),
        "new",
        set(),
    )
    assert report["extraction"]["insertion_kinds"] == {"COMPLEX": 1}
    assert report["mapping"]["unsupported_characters"] == 3


def test_formatting_only_is_not_an_insertion(tmp_path):
    report = verify_case(
        tmp_path,
        p(run("same", '<w:b/><w:rPrChange w:id="2"><w:rPr/></w:rPrChange>')),
        p(run("same", "<w:b/>")),
        "same",
        set(),
    )
    assert report["extraction"]["eligible_inserted_characters"] == 0


def test_moved_insertion_remains_unsupported(tmp_path):
    body = p('<w:moveTo w:id="9">' + ins("new") + "</w:moveTo>")
    report = verify_case(tmp_path, body, p(run("new")), "new", set())
    assert report["extraction"]["insertion_kinds"] == {"MOVED": 1}
    assert report["mapping"]["unsupported_characters"] == 3


def test_same_text_in_different_cells_has_structural_evidence(tmp_path):
    tracked = (
        "<w:tbl><w:tr><w:tc>"
        + p(run("same"))
        + "</w:tc><w:tc>"
        + p(ins("same"))
        + "</w:tc></w:tr></w:tbl>"
    )
    accepted = (
        "<w:tbl><w:tr><w:tc>"
        + p(run("same"))
        + "</w:tc><w:tc>"
        + p(run("same"))
        + "</w:tc></w:tr></w:tbl>"
    )
    report = verify_case(tmp_path, tracked, accepted, "samesame", {4, 5, 6, 7})
    assert report["mapping"]["exact_characters"] == 4


def test_image_and_comments_are_unchanged(tmp_path):
    a, b, out = [tmp_path / name for name in ("a.docx", "b.docx", "out.docx")]
    image = '<w:r><w:drawing><a:blip xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" r:embed="image"/></w:drawing></w:r>'
    extras = {
        "word/_rels/document.xml.rels": f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="image" Type="{R}/image" Target="media/object.bin"/></Relationships>',
        "word/media/object.bin": b"opaque-image",
        "word/comments.xml": f'<w:comments xmlns:w="{NS}"><w:comment w:id="1">{p(run("comment"))}</w:comment></w:comments>',
    }
    docx(a, p(image + ins("new")), extras)
    docx(b, p(image + run("new")), extras)
    report = convert(a, b, out)
    with ZipFile(b) as original, ZipFile(out) as colored:
        for name in extras:
            assert original.read(name) == colored.read(name)
        x = etree.fromstring(original.read("word/document.xml")).find(
            ".//" + W + "drawing"
        )
        y = etree.fromstring(colored.read("word/document.xml")).find(
            ".//" + W + "drawing"
        )
        assert etree.tostring(x) == etree.tostring(y)
    assert report["coloring"]["characters_colored"] == 3


def test_complex_deleted_field_is_unresolved(tmp_path):
    body = p(
        '<w:del w:id="2"><w:r><w:fldChar w:fldCharType="begin"/></w:r></w:del>'
        + ins("new")
    )
    report = verify_case(tmp_path, body, p(run("new")), "new", set())
    assert report["mapping"]["unsupported_characters"] == 3


def test_xml_space_loss_is_detected(tmp_path):
    from docx_color_cli.validation import events

    root = Package(docx(tmp_path / "a.docx", p(run(" a ")))).xml["word/document.xml"]
    changed = deepcopy(root)
    changed.find(".//" + W + "t").attrib.pop(
        "{http://www.w3.org/XML/1998/namespace}space"
    )
    assert events(root) != events(changed)


def test_nested_insertions_have_one_origin_per_character(tmp_path):
    body = p('<w:ins w:id="1">' + run("a") + ins("b", "2") + run("c") + "</w:ins>")
    report = verify_case(tmp_path, body, p(run("abc")), "abc", {0, 1, 2})
    assert report["extraction"]["insertion_containers"] == 2
    assert report["extraction"]["eligible_inserted_characters"] == 3
    assert report["extraction"]["raw_container_text_characters"] == 4


def test_cell_merge_history_does_not_supply_correspondence(tmp_path):
    before = (
        '<w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/><w:tcPrChange w:id="2"><w:tcPr/></w:tcPrChange></w:tcPr>'
        + p(ins("new"))
        + "</w:tc></w:tr></w:tbl>"
    )
    after = (
        '<w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr>'
        + p(run("new"))
        + "</w:tc></w:tr></w:tbl>"
    )
    report = verify_case(tmp_path, before, after, "new", set())
    assert report["mapping"]["unsupported_characters"] == 3
