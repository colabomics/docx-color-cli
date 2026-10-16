"""Independent truth and preservation counterexamples for structural mapping rules."""

import json
from copy import deepcopy
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from helpers.corpus import ins, p, package, run
from helpers.fidelity import W, compare, parse
from helpers.structural_cases import cases, evaluate, identified, marker_run

from docx_color_cli.cli import main
from docx_color_cli.engine import convert


@pytest.fixture(scope="module")
def gold(tmp_path_factory):
    return evaluate(tmp_path_factory.mktemp("structural-gold"))


@pytest.mark.parametrize("case_id", [case.ident for case, _, _ in cases()])
def test_structural_independent_truth(gold, case_id):
    row = next(r for r in gold["cases"] if r["id"] == case_id)
    if case_id == "P5-M-duplicate-id":
        assert row["status"] == "FAILED" and row["error"] == "INVALID_DOCUMENT_PAIR"
        assert row["input_hashes_unchanged"]
        return
    assert row["fidelity"]["overall"] == "PASS"
    assert row["accuracy"]["FP"] == 0
    assert row["accuracy"]["TP"] == row["authored_expected_tp"]
    assert row["accuracy"]["FN"] == row["authored_expected_fn"]
    assert row["input_hashes_unchanged"]


@pytest.mark.parametrize(
    "damage",
    [
        "remove",
        "duplicate",
        "relocate",
        "marker-attribute",
        "marker-color",
        "marker-font",
        "run-attribute",
    ],
)
def test_both_validators_detect_page_marker_damage(tmp_path, damage):
    from lxml import etree

    from docx_color_cli.validation import events

    a = package(tmp_path / "a.docx", identified(run("old") + ins("new") + run("old")))
    b = package(tmp_path / "b.docx", identified(marker_run("oldnewold", [4])))
    out, mutant = tmp_path / "out.docx", tmp_path / "mutant.docx"
    convert(a, b, out, inserted_color="00A060")
    with ZipFile(out) as z:
        data = {n: z.read(n) for n in z.namelist()}
    original = data["word/document.xml"]
    root = parse(original)
    parents = {c: n for n in root.iter() for c in n}
    marker = next(root.iter(W + "lastRenderedPageBreak"))
    marker_run_node = parents[marker]
    paragraph = parents[marker_run_node]
    if damage == "remove":
        paragraph.remove(marker_run_node)
    elif damage == "duplicate":
        paragraph.insert(
            list(paragraph).index(marker_run_node), deepcopy(marker_run_node)
        )
    elif damage == "relocate":
        paragraph.remove(marker_run_node)
        paragraph.append(marker_run_node)
    elif damage == "marker-attribute":
        marker.set("changed", "true")
    elif damage == "marker-color":
        next(marker_run_node.iter(W + "color")).set(W + "val", "00A060")
    elif damage == "marker-font":
        next(marker_run_node.iter(W + "sz")).set(W + "val", "72")
    else:
        marker_run_node.set(W + "rsidR", "000000FF")
    data["word/document.xml"] = ET.tostring(root)
    with ZipFile(mutant, "w") as z:
        for n, content in data.items():
            z.writestr(n, content)
    allowed = {("word/document.xml", 0, i) for i in range(3, 6)}
    assert compare(b, out, allowed=allowed, rgb="00A060")[0]["overall"] == "PASS"
    assert (
        compare(b, mutant, allowed=allowed, rgb="00A060")[0]["content_fidelity"]
        == "FAIL"
    )
    assert events(etree.fromstring(original)) != events(
        etree.fromstring(data["word/document.xml"])
    )


@pytest.mark.parametrize(
    "extra",
    ['<w:fldChar w:fldCharType="begin"/>', "<w:tab/>", "<w:drawing/>", "<w:t/>"],
)
def test_page_marker_does_not_authorize_other_complex_payloads(tmp_path, extra):
    a = package(tmp_path / "a.docx", p(run("old") + ins("new")))
    b = package(
        tmp_path / "b.docx",
        p("<w:r><w:lastRenderedPageBreak/><w:t>oldnew</w:t>" + extra + "</w:r>"),
    )
    out = tmp_path / "out.docx"
    if extra == "<w:tab/>":
        from docx_color_cli import ColoringError

        with pytest.raises(ColoringError) as error:
            convert(a, b, out)
        assert error.value.code == "INVALID_DOCUMENT_PAIR"
        assert not out.exists()
        return
    result = convert(a, b, out)
    assert result["coloring"]["characters_colored"] == 0
    assert compare(b, out, allowed=set())[0]["overall"] == "PASS"


def test_incomplete_coloring_is_explicit_in_cli_and_saved_report(tmp_path, capsys):
    a = package(tmp_path / "a.docx", p(run("same")) + p(ins("same")))
    b = package(tmp_path / "b.docx", p(run("same")) * 2)
    out, report = tmp_path / "out.docx", tmp_path / "report.json"
    assert main([str(a), str(b), str(out), "--report", str(report)]) == 0
    captured = capsys.readouterr()
    assert "Coloring is incomplete" in captured.err
    assert "PARTIAL" in captured.out
    receipt = json.loads(report.read_text())
    assert receipt["publication"]["status"] == "SUCCESS"
    assert receipt["completeness"]["status"] == "PARTIAL"
    assert receipt["completeness"]["ordinary_characters_uncolored"] == 4
    assert json.loads(report.read_text())["completeness"] == receipt["completeness"]


def test_linear_subsequence_against_independent_exhaustive_embeddings():
    from itertools import combinations, product

    from docx_color_cli.alignment import unique_subsequence

    strings = [
        "".join(chars) for size in range(5) for chars in product("ab", repeat=size)
    ]
    for source in strings:
        for target in strings:
            # Independent combinatorial enumeration, not the production DP or bounds.
            embeddings = [
                indices
                for indices in combinations(range(len(source)), len(target))
                if "".join(source[i] for i in indices) == target
            ]
            if not embeddings:
                assert unique_subsequence(source, target) is None
                continue
            expected = []
            for i in range(len(source)):
                destinations = {
                    indices.index(i) if i in indices else None for indices in embeddings
                }
                if destinations == {None}:
                    expected.append(("UNMAPPED", None))
                elif len(destinations) == 1 and None not in destinations:
                    expected.append(("ALIGNED", next(iter(destinations))))
                else:
                    expected.append(("AMBIGUOUS", None))
            assert unique_subsequence(source, target) == expected
    assert unique_subsequence("a" * 16001, "a") is None
