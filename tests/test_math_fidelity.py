"""Independent formula mutation checks on newly authored elementary fixtures."""

from copy import deepcopy
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from helpers.corpus import package, run
from helpers.fidelity import M, W, compare, parse
from helpers.field_cases import frame
from helpers.math_cases import eq, fraction, mr, whole
from lxml import etree

from docx_color_cli import color_revisions
from docx_color_cli.validation import events


def test_math_word_properties_follow_math_properties(tmp_path):
    payload = '<m:r><m:rPr><m:sty m:val="i"/></m:rPr><m:t>κ</m:t></m:r>'
    a = package(tmp_path / "a.docx", frame(whole(payload)))
    b = package(tmp_path / "b.docx", frame(eq(payload)))
    out = tmp_path / "out.docx"
    color_revisions(a, b, out)
    with ZipFile(out) as z:
        root = parse(z.read("word/document.xml"))
    node = next(root.iter(M + "r"))
    assert [c.tag for c in node] == [M + "rPr", W + "rPr", M + "t"]
    assert node.find(M + "rPr/" + W + "color") is None
    assert (
        compare(b, out, allowed={("word/document.xml", 0, 0)})[0]["overall"] == "PASS"
    )


@pytest.mark.parametrize(
    "damage",
    [
        "text",
        "argument_order",
        "object_type",
        "font",
        "math_style",
        "duplicate_color",
        "control_font",
        "parameter",
        "duplicate_object",
        "control_color",
        "old_equation_color",
    ],
)
def test_formula_mutations_detected_by_both_validators(tmp_path, damage):
    formula = fraction(mr("9"), mr("z"))
    a = package(tmp_path / "a.docx", frame(run("Note ") + whole(formula) + eq(mr("r"))))
    b = package(tmp_path / "b.docx", frame(run("Note ") + eq(formula) + eq(mr("r"))))
    out = tmp_path / "out.docx"
    color_revisions(a, b, out)
    with ZipFile(out) as z:
        data = {n: z.read(n) for n in z.namelist()}
    original = data["word/document.xml"]
    root = parse(original)
    obj = next(root.iter(M + "f"))
    node = next(root.iter(M + "r"))
    ctrl = next(root.iter(M + "ctrlPr"))
    if damage == "text":
        next(node.iter(M + "t")).text = "8"
    elif damage == "argument_order":
        num, den = obj.find(M + "num"), obj.find(M + "den")
        num.tag, den.tag = den.tag, num.tag
    elif damage == "object_type":
        obj.tag = M + "rad"
    elif damage == "font":
        next(node.iter(W + "rFonts")).set(W + "ascii", "Arial")
    elif damage == "math_style":
        ET.SubElement(ET.SubElement(node, M + "rPr"), M + "sty", {M + "val": "b"})
    elif damage == "duplicate_color":
        node.find(W + "rPr").append(deepcopy(next(node.iter(W + "color"))))
    elif damage == "control_font":
        ET.SubElement(ctrl.find(W + "rPr"), W + "sz", {W + "val": "44"})
    elif damage == "parameter":
        ET.SubElement(obj.find(M + "fPr"), M + "type", {M + "val": "lin"})
    elif damage == "duplicate_object":
        next(root.iter(M + "oMath")).append(deepcopy(obj))
    elif damage == "control_color":
        next(ctrl.iter(W + "color")).set(W + "val", "000000")
    else:
        list(root.iter(M + "r"))[-1].find(W + "rPr/" + W + "color").set(
            W + "val", "FF0000"
        )
    data["word/document.xml"] = ET.tostring(root)
    mutant = tmp_path / "mutant.docx"
    with ZipFile(mutant, "w") as z:
        for name, value in data.items():
            z.writestr(name, value)
    allowed = {("word/document.xml", 0, i) for i in [5, 6]}
    controls = {("word/document.xml", 0, 0)}
    assert (
        compare(b, out, allowed=allowed, allowed_math_controls=controls)[0]["overall"]
        == "PASS"
    )
    assert (
        compare(b, mutant, allowed=allowed, allowed_math_controls=controls)[0][
            "overall"
        ]
        == "FAIL"
    )
    assert events(etree.fromstring(original)) != events(
        etree.fromstring(data["word/document.xml"])
    )
