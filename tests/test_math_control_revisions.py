import pytest
from helpers.assertions import (
    assert_integrity,
    assert_rejects_without_output,
    paragraphs,
    xml_part,
)
from helpers.fixtures import M, W, p, revision, run

from docx_color_cli.cli import convert


def deleted_run():
    return "<m:r>" + revision("del", "<m:t>gone</m:t>") + "</m:r>"


def obj(kind, content):
    return (
        f'<m:{kind}><m:{kind}Pr><m:ctrlPr><w:del w:id="1"><w:rPr/></w:del></m:ctrlPr></m:{kind}Pr>'
        + content
        + f"</m:{kind}>"
    )


@pytest.mark.parametrize(
    "kind,args",
    [
        ("d", ["e"]),
        ("f", ["num", "den"]),
        ("sSub", ["e", "sub"]),
        ("nary", ["sub", "sup", "e"]),
        ("func", ["fName", "e"]),
        ("eqArr", ["e", "e"]),
    ],
)
def test_deleted_control_and_payload(docx, tmp_path, kind, args):
    content = "".join(f"<m:{a}>" + deleted_run() + f"</m:{a}>" for a in args)
    source = docx(
        "in.docx",
        p(
            run("before")
            + "<m:oMath>"
            + obj(kind, content)
            + "<m:r><m:t>keep</m:t></m:r></m:oMath>"
            + run("after")
        ),
    )
    original = source.read_bytes()
    target = tmp_path / "out.docx"
    convert(source, target)
    root = xml_part(target)
    assert list(root.iter(M + kind)) == []
    assert [n.text for n in root.iter(M + "t")] == ["keep"]
    assert paragraphs(target) == ["beforekeepafter"]
    assert source.read_bytes() == original
    assert_integrity(target)


def test_nested_deleted_math_objects(docx, tmp_path):
    inner = obj(
        "sSub", "<m:e>" + deleted_run() + "</m:e><m:sub>" + deleted_run() + "</m:sub>"
    )
    source = docx(
        "in.docx",
        p(
            "<m:oMath>"
            + obj(
                "f", "<m:num>" + inner + "</m:num><m:den>" + deleted_run() + "</m:den>"
            )
            + "</m:oMath>"
        ),
    )
    target = tmp_path / "out.docx"
    convert(source, target)
    assert not list(xml_part(target).iter(M + "f"))
    assert not list(xml_part(target).iter(M + "sSub"))
    assert_integrity(target)


@pytest.mark.parametrize(
    "payload",
    [
        "<m:r><m:t>keep</m:t></m:r>",
        "<m:r>" + revision("ins", "<m:t>keep</m:t>") + "</m:r>",
        '<w:bookmarkStart w:id="7" w:name="target"/><w:bookmarkEnd w:id="7"/>',
        "<m:sSub><m:e/><m:sub/></m:sSub>",
        '<w:fldSimple w:instr="REF target">' + run("keep") + "</w:fldSimple>",
        "<m:unknown/>",
    ],
)
def test_control_deletion_never_discards_unproven_payload(docx, tmp_path, payload):
    source = docx(
        "in.docx",
        p("<m:oMath>" + obj("d", "<m:e>" + payload + "</m:e>") + "</m:oMath>"),
    )
    assert_rejects_without_output(convert, source, tmp_path / "out.docx")


def test_inserted_control_with_deleted_arguments(docx, tmp_path):
    content = obj("d", "<m:e>" + deleted_run() + "</m:e>").replace(
        '<w:del w:id="1"><w:rPr/></w:del>', '<w:ins w:id="1"><w:rPr/></w:ins>'
    )
    target = tmp_path / "out.docx"
    convert(docx("in.docx", p("<m:oMath>" + content + "</m:oMath>")), target)
    assert xml_part(target).find(".//" + M + "d") is not None
    assert not list(xml_part(target).iter(M + "t"))
    assert (
        xml_part(target)
        .find(".//" + M + "ctrlPr/" + W + "rPr/" + W + "color")
        .get(W + "val")
        == "FF0000"
    )
    assert_integrity(target)


def test_deleted_inner_object_preserves_outer_fraction(docx, tmp_path):
    inner = obj("d", "<m:e>" + deleted_run() + "</m:e>")
    content = (
        "<m:f><m:num>"
        + inner
        + "<m:r><m:t>x</m:t></m:r></m:num><m:den><m:r><m:t>y</m:t></m:r></m:den></m:f>"
    )
    target = tmp_path / "out.docx"
    convert(docx("in.docx", p("<m:oMath>" + content + "</m:oMath>")), target)
    root = xml_part(target)
    assert len(list(root.iter(M + "f"))) == 1
    assert not list(root.iter(M + "d"))
    assert [n.text for n in root.iter(M + "t")] == ["x", "y"]
    for r in root.iter(M + "r"):
        assert r.find(W + "rPr/" + W + "color").get(W + "val") == "000000"
    assert_integrity(target)
