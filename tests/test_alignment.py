"""Adversarial character oracles for the additional alignment evidence paths."""

import pytest
from test_insertion_mapping import delete, ins, p, run, table, verify_case

from docx_color_cli.anchors import PARA_ID


def identified(content, ident="00000001", props=""):
    return p(content, props).replace(
        "<w:p>",
        f'<w:p xmlns:w14="{PARA_ID[1:].split("}")[0]}" w14:paraId="{ident}">',
    )


def marker(kind, ident):
    return f'<w:moveToRange{kind} w:id="{ident}"/>'


def math(content):
    return "<m:oMath>" + content + "</m:oMath>"


def field():
    return (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText>PAGE</w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        + run("1")
        + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )


def test_disjoint_ranges_do_not_quarantine_intervening_text(tmp_path):
    before = p(marker("Start", "1") + run("A") + marker("End", "1"))
    after = p(marker("Start", "2") + run("Z") + marker("End", "2"))
    report = verify_case(
        tmp_path,
        before + p(ins("new")) + after,
        p(run("A")) + p(run("new")) + p(run("Z")),
        "AnewZ",
        {1, 2, 3},
    )
    assert report["extraction"]["unresolved_projection_paragraphs"] == 2


@pytest.mark.parametrize("malformation", ["missing", "duplicate", "reversed", "no-id"])
def test_malformed_ranges_fail_closed(tmp_path, malformation):
    endpoints = {
        "missing": marker("Start", "1"),
        "duplicate": marker("Start", "1") * 2 + marker("End", "1"),
        "reversed": marker("End", "1") + marker("Start", "1"),
        "no-id": "<w:moveToRangeStart/>" + marker("End", "1"),
    }[malformation]
    verify_case(
        tmp_path,
        p(endpoints + run("old")) + p(ins("new")),
        p(run("old")) + p(run("new")),
        "oldnew",
        set(),
    )


def test_cross_paragraph_range_still_quarantines_insertions(tmp_path):
    verify_case(
        tmp_path,
        p(marker("Start", "1") + run("A"))
        + p(ins("new"))
        + p(run("Z") + marker("End", "1")),
        p(run("A")) + p(run("new")) + p(run("Z")),
        "AnewZ",
        set(),
    )


def test_repeated_paragraphs_have_unique_structural_ids(tmp_path):
    verify_case(
        tmp_path,
        identified(run("same")) + identified(ins("same"), "00000002"),
        identified(run("same")) + identified(run("same"), "00000002"),
        "samesame",
        {4, 5, 6, 7},
    )


def test_duplicate_ids_do_not_disambiguate_repetition(tmp_path):
    verify_case(
        tmp_path,
        identified(run("same")) + identified(ins("same")),
        identified(run("same")) * 2,
        "samesame",
        set(),
    )


@pytest.mark.parametrize("ident", ["00000001", "00000002"])
def test_math_revision_and_plain_text_require_consistent_paragraph_id(tmp_path, ident):
    equation = "<m:r><m:t>x</m:t></m:r>"
    tracked = identified(math('<w:ins w:id="2">' + equation + "</w:ins>") + ins(" new"))
    accepted = identified(math(equation) + run(" new"), ident)
    report = verify_case(
        tmp_path,
        tracked,
        accepted,
        "x new",
        {0, 1, 2, 3, 4} if ident == "00000001" else set(),
    )
    assert report["mapping"]["unsupported_characters"] == (
        0 if ident == "00000001" else 5
    )


def test_formula_boundary_change_is_not_text_correspondence(tmp_path):
    verify_case(
        tmp_path,
        identified(
            math('<w:ins w:id="2"><m:r><m:t>x</m:t></m:r></w:ins>') + ins("new")
        ),
        identified(math("<m:r><m:t>xn</m:t></m:r>") + run("ew")),
        "xnew",
        set(),
    )


def test_complex_field_does_not_poison_adjacent_plain_insertion(tmp_path):
    verify_case(
        tmp_path,
        identified('<w:ins w:id="2">' + field() + "</w:ins>" + ins(" new")),
        identified(field() + run(" new")),
        "1 new",
        # The field's displayed "1" is itself inside w:ins, too.
        {0, 1, 2, 3, 4},
    )


@pytest.mark.parametrize("change", ["instruction", "unbalanced", "hyperlink"])
def test_structural_boundary_conflicts_refuse_rescue(tmp_path, change):
    a = identified('<w:ins w:id="2">' + field() + "</w:ins>" + ins(" new"))
    content = field() + run(" new")
    if change == "instruction":
        content = content.replace("PAGE", "NUMPAGES")
    elif change == "unbalanced":
        content = content.replace('w:fldCharType="end"', 'w:fldCharType="separate"')
    else:
        content = (
            field() + '<w:hyperlink w:anchor="target">' + run(" new") + "</w:hyperlink>"
        )
    verify_case(tmp_path, a, identified(content), "1 new", set())


def test_complex_deleted_field_stays_unsupported_with_id(tmp_path):
    a = identified(
        '<w:del w:id="2"><w:r><w:fldChar w:fldCharType="begin"/></w:r></w:del>'
        + ins("new")
    )
    verify_case(tmp_path, a, identified(run("new")), "new", set())


@pytest.mark.parametrize("text", ["new", "中文， ", "e\u0301🚀", "  ,.! "])
def test_exact_bounded_paragraph_merge(tmp_path, text):
    a = (
        p(run("left"))
        + p(run("A") + ins(text), '<w:rPr><w:del w:id="2"/></w:rPr>')
        + p(run("Z"))
        + p(run("right"))
    )
    b = p(run("left")) + p(run("A" + text[:1]) + run(text[1:] + "Z")) + p(run("right"))
    result = verify_case(
        tmp_path, a, b, "leftA" + text + "Zright", set(range(5, 5 + len(text)))
    )
    assert result["mapping"]["aligned_characters"] == len(text)


def test_paragraph_merge_without_deleted_mark_refused(tmp_path):
    verify_case(
        tmp_path,
        p(run("left")) + p(run("A") + ins("x")) + p(run("Z")) + p(run("right")),
        p(run("left")) + p(run("AxZ")) + p(run("right")),
        "leftAxZright",
        set(),
    )


def test_bounded_merge_refuses_nonidentical_stream(tmp_path):
    verify_case(
        tmp_path,
        p(run("left"))
        + p(ins("x"), '<w:rPr><w:del w:id="2"/></w:rPr>')
        + p(run("x"))
        + p(run("right")),
        p(run("left")) + p(run("x")) + p(run("right")),
        "leftxright",
        set(),
    )


def test_same_insertions_between_distinct_context_anchors(tmp_path):
    a = (
        p(run("left"))
        + p(ins("same"))
        + p(run("same"))
        + p(ins("same", "2"))
        + p(run("right"))
    )
    b = p(run("left")) + p(run("same")) * 3 + p(run("right"))
    verify_case(
        tmp_path, a, b, "leftsamesamesameright", set(range(4, 8)) | set(range(12, 16))
    )


def test_table_change_remains_unsupported_with_matching_ids(tmp_path):
    verify_case(
        tmp_path,
        table(identified(ins("new")), '<w:trPr><w:ins w:id="2"/></w:trPr>'),
        table(identified(run("new"))),
        "new",
        set(),
    )


def test_cross_paragraph_container_is_still_complex(tmp_path):
    verify_case(
        tmp_path,
        '<w:ins w:id="9">' + p(run("A")) + p(run("B")) + "</w:ins>",
        p(run("A")) + p(run("B")),
        "AB",
        set(),
    )


def test_inserted_then_deleted_text_not_recovered_in_merge(tmp_path):
    a = (
        p(run("left"))
        + p(
            '<w:ins w:id="1">' + run("n") + delete("gone") + run("ew") + "</w:ins>",
            '<w:rPr><w:del w:id="3"/></w:rPr>',
        )
        + p(run("Z"))
        + p(run("right"))
    )
    b = p(run("left")) + p(run("newZ")) + p(run("right"))
    verify_case(tmp_path, a, b, "leftnewZright", {4, 5, 6})


def test_large_nonidentical_local_gap_keeps_budget(tmp_path):
    a = p(run("left")) + p(run("a" * 600) + ins("X")) + p(run("right"))
    b = p(run("left")) + p(run("a" * 600 + "X!")) + p(run("right"))
    report = verify_case(
        tmp_path, a, b, "left" + "a" * 600 + "X!right", set(), pair_rejected=True
    )
    assert (
        report["mapping_evidence_counts"]["bounded local alignment budget exceeded"]
        == 1
    )


def test_unique_surviving_id_bounds_a_merge_without_neighbor_anchors(tmp_path):
    a = identified(
        ins("new"), "00000001", '<w:rPr><w:del w:id="2"/></w:rPr>'
    ) + identified(run(" tail"), "00000002")
    b = identified(run("new tail"), "00000002")
    report = verify_case(tmp_path, a, b, "new tail", {0, 1, 2})
    assert report["mapping"]["structural_join_regions"] == 1


def test_surviving_id_merge_refuses_mismatched_final_text(tmp_path):
    a = identified(
        ins("a"), "00000001", '<w:rPr><w:del w:id="2"/></w:rPr>'
    ) + identified(run("a"), "00000002")
    b = identified(run("a"), "00000002")
    verify_case(tmp_path, a, b, "a", set())


def test_merge_refuses_a_source_id_that_also_survives_elsewhere(tmp_path):
    a = identified(
        ins("new"), "00000001", '<w:rPr><w:del w:id="2"/></w:rPr>'
    ) + identified(run(" tail"), "00000002")
    b = identified(run("different"), "00000001") + identified(
        run("new tail"), "00000002"
    )
    verify_case(tmp_path, a, b, "differentnew tail", set(), pair_rejected=True)


def test_merge_refuses_competing_unchanged_paragraph_anchor(tmp_path):
    a = (
        p(run("new tail"))
        + identified(ins("new"), "00000001", '<w:rPr><w:del w:id="2"/></w:rPr>')
        + identified(run(" tail"), "00000002")
    )
    verify_case(tmp_path, a, identified(run("new tail"), "00000002"), "new tail", set())


def test_move_wrappers_with_matching_ids_stay_unsupported(tmp_path):
    a = identified('<w:moveTo w:id="8">' + ins("new") + "</w:moveTo>")
    verify_case(tmp_path, a, identified(run("new")), "new", set())


def test_join_does_not_cross_changed_table_cells(tmp_path):
    a = (
        "<w:tbl><w:tr><w:tc>"
        + identified(ins("new"), "00000001", '<w:rPr><w:del w:id="2"/></w:rPr>')
        + "</w:tc><w:tc>"
        + identified(run(" tail"), "00000002")
        + "</w:tc></w:tr></w:tbl>"
    )
    b = table(identified(run("new tail"), "00000002"))
    verify_case(tmp_path, a, b, "new tail", set())


def test_inverted_context_anchors_do_not_enable_local_alignment(tmp_path):
    a = p(run("left")) + p(ins("x")) + p(run("right"))
    b = p(run("right")) + p(run("x!")) + p(run("left"))
    verify_case(tmp_path, a, b, "rightx!left", set(), pair_rejected=True)


def test_page_break_is_preserved_and_only_inserted_text_colored(tmp_path):
    a = identified(run("old") + ins("new"))
    b = identified("<w:r><w:lastRenderedPageBreak/><w:t>oldnew</w:t></w:r>")
    report = verify_case(tmp_path, a, b, "oldnew", {3, 4, 5})
    assert report["mapping"]["unsupported_characters"] == 0
    assert report["coloring"]["page_break_runs_split"] == 1


def test_nested_insertion_census_matches_authored_truth(tmp_path):
    from test_insertion_mapping import docx

    from docx_color_cli import color_revisions
    from docx_color_cli.accepted import Package
    from docx_color_cli.extract import extract
    from docx_color_cli.projection import paragraphs

    source = docx(
        tmp_path / "source.docx",
        p('<w:ins w:id="1">' + run("a") + ins("中", "2") + delete("gone") + "</w:ins>")
        + p('<w:del w:id="5">' + ins("removed", "6") + "</w:del>")
        + p('<w:moveTo w:id="7">' + ins("moved", "8") + "</w:moveTo>"),
    )
    reference = docx(tmp_path / "reference.docx", p(run("a中")) + p(run("moved")))
    package = Package(source)
    records, _ = extract(package)
    ordinary = {r.key for r in records.values() if r.kind == "ORDINARY"}
    observed = "".join(
        char
        for para in paragraphs(package, records)
        for char, origin in zip(para.text, para.origins, strict=True)
        if origin in ordinary
    )
    assert observed == "a中"
    result = color_revisions(source, reference, tmp_path / "out.docx")
    assert result["coloring"]["independently_verified_false_coloring_count"] is None
