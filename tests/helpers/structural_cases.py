"""Authored Phase 5 provenance: no mapping/projection functions build the truth."""

from html import escape

from helpers.corpus import Case, cell, ins, p, run, table

INS, OLD = "INSERTED", "UNCHANGED"
MARK = '<w:rPr><w:del w:id="90"/></w:rPr>'
PROPS = '<w:rFonts w:ascii="Cambria"/><w:b/><w:i/><w:color w:val="FF0000"/><w:sz w:val="24"/>'


def identified(content, ident="00000001", props=""):
    return p(content, props).replace(
        "<w:p>",
        '<w:p xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" w14:paraId="'
        + ident
        + '">',
    )


def marker_run(text, positions, props=PROPS):
    chunks, start = [], 0
    for end in positions:
        if end > start:
            chunks.append(
                '<w:t xml:space="preserve">' + escape(text[start:end]) + "</w:t>"
            )
        chunks.append("<w:lastRenderedPageBreak/>")
        start = end
    if start < len(text):
        chunks.append('<w:t xml:space="preserve">' + escape(text[start:]) + "</w:t>")
    return (
        '<w:r w:rsidR="000000AA"><w:rPr>'
        + props
        + "</w:rPr>"
        + "".join(chunks)
        + "</w:r>"
    )


def field(label="1", instruction="PAGE", deleted=False):
    instruction_tag = "delInstrText" if deleted else "instrText"
    return (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:'
        + instruction_tag
        + ">"
        + instruction
        + "</w:"
        + instruction_tag
        + "></w:r>"
        + '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        + run(label)
        + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )


def drawing(width="100"):
    return (
        '<w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"><wp:extent cx="'
        + width
        + '" cy="100"/></wp:inline></w:drawing></w:r>'
    )


def deletion(payload):
    return '<w:del w:id="80">' + payload + "</w:del>"


def cases():
    """Return (case, expected TP, expected FN) using an initially absent color."""
    result = []
    for number, (left, new, right) in enumerate(
        [
            ("old", "new", "old"),
            ("word ", "word", " word"),
            ("旧", "中e\u0301🚀 ", "尾"),
        ],
        1,
    ):
        text = left + new + right
        for at in sorted({0, len(left), len(left) + len(new) // 2, len(text)}):
            case = Case(
                f"P5-R{number}-{at}",
                "rendered marker; authored insertion boundaries",
                identified(
                    run(left, PROPS) + ins(new, props=PROPS) + run(right, PROPS)
                ),
                identified(marker_run(text, [at])),
                [[(left, OLD), (new, INS), (right, OLD)]],
            )
            result.append((case, len(new), 0))
    result.append(
        (
            Case(
                "P5-R-consecutive",
                "consecutive markers and entirely inserted text",
                identified(ins("new")),
                identified(marker_run("new", [0, 1, 1, 3])),
                [[("new", INS)]],
            ),
            3,
            0,
        )
    )
    result.append(
        (
            Case(
                "P5-R-field",
                "page marker inside hyperlink beside field",
                identified(
                    '<w:hyperlink w:anchor="target">'
                    + run("old")
                    + ins("new")
                    + "</w:hyperlink>"
                    + field()
                ),
                identified(
                    '<w:hyperlink w:anchor="target">'
                    + marker_run("oldnew", [4])
                    + "</w:hyperlink>"
                    + field()
                ),
                [[("old", OLD), ("new", INS), ("1", OLD)]],
            ),
            3,
            0,
        )
    )
    result.append(
        (
            Case(
                "P5-R-table",
                "page marker in stable table cell",
                table("<w:tr>" + cell(identified(run("old") + ins("new"))) + "</w:tr>"),
                table(
                    "<w:tr>" + cell(identified(marker_run("oldnew", [3]))) + "</w:tr>"
                ),
                [[("old", OLD), ("new", INS)]],
            ),
            3,
            0,
        )
    )

    for name, payload, supported in [
        ("closed-field", field("gone", deleted=True), True),
        ("nested-fields", field(field("gone"), deleted=True), True),
        ("drawing", drawing(), True),
        ("break", "<w:r><w:br/></w:r>", True),
        ("open-field", '<w:r><w:fldChar w:fldCharType="begin"/></w:r>', False),
        ("unmatched-field-end", '<w:r><w:fldChar w:fldCharType="end"/></w:r>', False),
        ("bookmark-range", '<w:bookmarkStart w:id="1" w:name="x"/>', False),
    ]:
        # Nested field XML is assembled separately, not embedded as text.
        if name == "nested-fields":
            payload = (
                '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                + field("gone", deleted=True)
                + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
            )
        result.append(
            (
                Case(
                    "P5-D-" + name,
                    "isolation of deleted container",
                    identified(run("old") + deletion(payload) + ins("new")),
                    identified(run("oldnew")),
                    [[("old", OLD), ("new", INS)]],
                ),
                3 if supported else 0,
                0 if supported else 3,
            )
        )
    result.append(
        (
            Case(
                "P5-D-fragmented",
                "field spans separate deletion containers: refuse",
                identified(
                    deletion('<w:r><w:fldChar w:fldCharType="begin"/></w:r>')
                    + ins("new")
                    + deletion('<w:r><w:fldChar w:fldCharType="end"/></w:r>')
                ),
                identified(run("new")),
                [[("new", INS)]],
            ),
            0,
            3,
        )
    )

    for altered in (False, True):
        a = identified(
            run("old") + deletion(drawing()) + ins("new") + drawing() + run("tail")
        )
        b = identified(
            (drawing("200") if altered else "")
            + run("oldnew")
            + ("" if altered else drawing("200"))
            + run("tail")
        )
        result.append(
            (
                Case(
                    f"P5-O-{int(altered)}",
                    "opaque object boundary, accepted object authoritative",
                    a,
                    b,
                    [[("old", OLD), ("new", INS), ("tail", OLD)]],
                ),
                0 if altered else 3,
                3 if altered else 0,
            )
        )

    for name, obj, label in [
        ("field", field(), "1"),
        (
            "hyperlink",
            '<w:hyperlink w:anchor="target">' + run("link") + "</w:hyperlink>",
            "link",
        ),
        ("math", "<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>", "x"),
        ("break", "<w:r><w:br/></w:r>", "\n"),
    ]:
        a = identified(run("a") + ins("new"), props=MARK) + identified(
            obj + run("z"), "00000002"
        )
        b = identified(run("anew") + obj + run("z"), "00000002")
        result.append(
            (
                Case(
                    "P5-J-" + name,
                    "merged region retains every object boundary",
                    a,
                    b,
                    [[("a", OLD), ("new", INS), (label + "z", OLD)]],
                ),
                3,
                0,
            )
        )
    result.append(
        (
            Case(
                "P5-J-deleted-drawing",
                "merged paragraph with isolated deleted drawing",
                identified(run("a") + deletion(drawing()) + ins("new"), props=MARK)
                + identified(run("z"), "00000002"),
                identified(run("anewz"), "00000002"),
                [[("a", OLD), ("new", INS), ("z", OLD)]],
            ),
            3,
            0,
        )
    )
    result.append(
        (
            Case(
                "P5-J-changed-field",
                "same display text but conflicting field instructions",
                identified(run("a") + ins("new"), props=MARK)
                + identified(field() + run("z"), "00000002"),
                identified(
                    run("anew") + field(instruction="NUMPAGES") + run("z"), "00000002"
                ),
                [[("a", OLD), ("new", INS), ("1z", OLD)]],
            ),
            0,
            3,
        )
    )
    result.append(
        (
            Case(
                "P5-J-shifted-field",
                "same text but zero-display field moved across inserted span",
                identified(ins("new"), props=MARK)
                + identified(field("") + run("tail"), "00000002"),
                identified(field("") + run("newtail"), "00000002"),
                [[("new", INS), ("tail", OLD)]],
            ),
            0,
            3,
        )
    )
    box = (
        "<w:r><w:drawing><w:txbxContent>"
        + p(run("box"))
        + "</w:txbxContent></w:drawing></w:r>"
    )
    result.append(
        (
            Case(
                "P5-O-textbox",
                "nested text story is not an opaque zero-width anchor",
                identified(run("old") + deletion(drawing()) + ins("new") + box),
                identified(run("oldnew") + box),
                [[("old", OLD), ("new", INS)], [("box", OLD)]],
            ),
            0,
            3,
        )
    )

    start, end = '<w:moveToRangeStart w:id="7"/>', '<w:moveToRangeEnd w:id="7"/>'
    moved = '<w:moveTo w:id="8">' + run("same") + "</w:moveTo>"
    content = ins("same", "1") + start + moved + ins("x", "2") + end + ins("same", "3")
    result.append(
        (
            Case(
                "P5-M-outside",
                "repeated words, insertions outside and inside a move range",
                identified(content),
                identified(run("samesamexsame")),
                [[("same", INS), ("same", OLD), ("x", INS), ("same", INS)]],
            ),
            8,
            1,
        )
    )
    for name, begin, finish in [
        ("missing", start, ""),
        ("reversed", end, start),
        ("duplicate", start + start, end),
        ("no-id", "<w:moveToRangeStart/>", end),
    ]:
        a = identified(ins("same") + begin + moved + finish)
        result.append(
            (
                Case(
                    "P5-M-" + name,
                    "malformed range cannot authorize outside insertions",
                    a,
                    identified(run("samesame")),
                    [[("same", INS), ("same", OLD)]],
                ),
                0,
                4,
            )
        )
    result.append(
        (
            Case(
                "P5-M-no-anchor",
                "move context without a stable paragraph ID",
                p(ins("same") + start + moved + end),
                p(run("samesame")),
                [[("same", INS), ("same", OLD)]],
            ),
            0,
            4,
        )
    )
    result.append(
        (
            Case(
                "P5-M-duplicate-id",
                "duplicated IDs do not prove correspondence",
                identified(ins("same") + start + moved + end),
                identified(run("samesame")) + identified(run("other")),
                [[("same", INS), ("same", OLD)], [("other", OLD)]],
            ),
            0,
            4,
        )
    )
    result.append(
        (
            Case(
                "P5-M-movefrom",
                "whole-target subsequence uniquely proves outside insertion",
                identified(
                    ins("new")
                    + '<w:moveFrom w:id="1">'
                    + run("gone")
                    + "</w:moveFrom>"
                    + start
                    + moved
                    + end
                ),
                identified(run("newsame")),
                [[("new", INS), ("same", OLD)]],
            ),
            3,
            0,
        )
    )
    result.append(
        (
            Case(
                "P5-M-wrapper",
                "insertion in move wrapper stays out of scope",
                identified(
                    ins("new")
                    + start
                    + '<w:moveTo w:id="8">'
                    + ins("x", "2")
                    + "</w:moveTo>"
                    + end
                ),
                identified(run("newx")),
                [[("new", INS), ("x", INS)]],
            ),
            3,
            1,
        )
    )

    deleted_row = (
        '<w:tr><w:trPr><w:del w:id="3"/></w:trPr>'
        + cell(identified(ins("same")))
        + "</w:tr>"
    )
    kept_row = "<w:tr>" + cell(identified(run("same"), "00000002")) + "</w:tr>"
    result.append(
        (
            Case(
                "P5-T-deleted-copy",
                "do not map a removed cell insertion onto identical kept text",
                table(deleted_row + kept_row),
                table(kept_row),
                [[("same", OLD)]],
            ),
            0,
            0,
        )
    )
    result.append(
        (
            Case(
                "P5-T-changed-shape",
                "table shape change remains explicit unsupported",
                table(
                    deleted_row
                    + "<w:tr>"
                    + cell(identified(ins("new"), "00000002"))
                    + "</w:tr>"
                ),
                table("<w:tr>" + cell(identified(run("new"), "00000002")) + "</w:tr>"),
                [[("new", INS)]],
            ),
            0,
            3,
        )
    )
    result.append(
        (
            Case(
                "P5-M-merged-context",
                "surviving ID bounds merged move context; protect inside range",
                identified(content, props=MARK) + identified("", "00000002"),
                identified(run("samesamexsame"), "00000002"),
                [[("same", INS), ("same", OLD), ("x", INS), ("same", INS)]],
            ),
            8,
            1,
        )
    )
    result.append(
        (
            Case(
                "P5-M-range-across-paragraphs",
                "range-only paragraphs require the same exclusion mask",
                identified(ins("new") + start + run("old"), props=MARK)
                + identified(end + ins("new", "2"), "00000002"),
                identified(run("newoldnew"), "00000002"),
                [[("new", INS), ("old", OLD), ("new", INS)]],
            ),
            6,
            0,
        )
    )
    from_text = '<w:moveFrom w:id="40">' + run("old") + "</w:moveFrom>"
    to_text = '<w:moveTo w:id="41">' + run("old") + "</w:moveTo>"
    result.append(
        (
            Case(
                "P5-L-full-chain",
                "unique subsequence uses entire merged chain",
                identified(run("head"), props=MARK)
                + identified(ins("new") + from_text + to_text, "00000002"),
                identified(run("headnewold"), "00000002"),
                [[("head", OLD), ("new", INS), ("old", OLD)]],
            ),
            3,
            0,
        )
    )
    result.append(
        (
            Case(
                "P5-L-prefix-competition",
                "incoming unchanged paragraph competes with repeated insertion",
                identified(run("abc"), props=MARK)
                + identified(
                    ins("abc")
                    + '<w:moveFrom w:id="40">'
                    + run("abc")
                    + "</w:moveFrom>",
                    "00000002",
                ),
                identified(run("abcabc"), "00000002"),
                [[("abc", OLD), ("abc", INS)]],
            ),
            0,
            3,
        )
    )
    result.append(
        (
            Case(
                "P5-L-field-barrier",
                "subsequence cannot flatten field boundaries",
                identified(ins("new") + from_text + field() + to_text),
                identified(run("new") + field() + run("old")),
                [[("new", INS), ("1old", OLD)]],
            ),
            0,
            3,
        )
    )
    result.append(
        (
            Case(
                "P5-L-budget",
                "subsequence stays within bounded paragraph window",
                "".join(identified("", f"{i:08X}", MARK) for i in range(40))
                + identified(ins("new") + from_text + to_text, "000000AA"),
                identified(run("newold"), "000000AA"),
                [[("new", INS), ("old", OLD)]],
            ),
            0,
            3,
        )
    )
    for variant in ("paired", "wrong-name", "duplicate-source", "overlap"):
        source_name = "other" if variant == "wrong-name" else "move-A"
        source_container = (
            '<w:moveFromRangeStart w:id="70" w:name="'
            + source_name
            + '"/><w:moveFrom w:id="71">'
            + run("same")
            + '</w:moveFrom><w:moveFromRangeEnd w:id="70"/>'
        )
        prefix = p(source_container, MARK)
        if variant in {"duplicate-source", "overlap"}:
            second_name = "move-A" if variant == "duplicate-source" else "move-B"
            prefix += p(
                '<w:moveFromRangeStart w:id="72" w:name="'
                + second_name
                + '"/><w:moveFrom w:id="73">'
                + run("same")
                + '</w:moveFrom><w:moveFromRangeEnd w:id="72"/>',
                MARK,
            )
        destination_start = '<w:moveToRangeStart w:id="7" w:name="move-A"/>'
        destination_end = end
        if variant == "overlap":
            destination_start += '<w:moveToRangeStart w:id="9" w:name="move-B"/>'
            destination_end = '<w:moveToRangeEnd w:id="9"/>' + end
        body = (
            ins("same", "1")
            + destination_start
            + moved
            + ins("x", "2")
            + destination_end
            + ins("same", "3")
        )
        result.append(
            (
                Case(
                    "P5-N-" + variant,
                    "separate ordinary insertion in a destination container",
                    prefix + identified(body),
                    identified(run("samesamexsame")),
                    [[("same", INS), ("same", OLD), ("x", INS), ("same", INS)]],
                ),
                9 if variant == "paired" else 8,
                0 if variant == "paired" else 1,
            )
        )
    return result


def evaluate(directory):
    import json
    from pathlib import Path

    from docx_color_cli.engine import convert
    from helpers.corpus import package
    from helpers.evaluate import aggregate
    from helpers.fidelity import accuracy, compare, digest

    directory = Path(directory)
    rows = []
    for case, expected_tp, expected_fn in cases():
        folder = directory / case.ident
        folder.mkdir(parents=True, exist_ok=True)
        a = package(folder / "tracked.docx", case.tracked)
        b = package(folder / "accepted.docx", case.accepted)
        out = folder / "colored.docx"
        hashes = [digest(a), digest(b)]
        manifest = case.manifest()
        (folder / "expected.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
        if case.ident == "P5-M-duplicate-id":
            from docx_color_cli import ColoringError

            try:
                convert(a, b, out, inserted_color="00A060")
            except ColoringError as error:
                assert error.code == "INVALID_DOCUMENT_PAIR"
            else:
                raise AssertionError("Incompatible authored pair must not publish")
            assert not out.exists()
            rows.append(
                {
                    "id": case.ident,
                    "status": "FAILED",
                    "error": "INVALID_DOCUMENT_PAIR",
                    "input_hashes_unchanged": hashes == [digest(a), digest(b)],
                }
            )
            continue
        result = convert(a, b, out, inserted_color="00A060")
        truth = case.truth()
        fidelity, before, after = compare(
            b,
            out,
            allowed={k for k, label in truth.items() if label == INS},
            rgb="00A060",
        )
        assert before.keys() == truth.keys()
        for pi, paragraph in enumerate(manifest["paragraphs"]):
            assert (
                "".join(
                    before["word/document.xml", pi, i].text
                    for i in range(len(paragraph["labels"]))
                )
                == paragraph["text"]
            )
        metrics = accuracy(before, after, truth, "00A060")
        rows.append(
            {
                "id": case.ident,
                "name": case.name,
                "authored_expected_tp": expected_tp,
                "authored_expected_fn": expected_fn,
                "accuracy": metrics,
                "fidelity": fidelity,
                "input_hashes_unchanged": hashes == [digest(a), digest(b)],
                "page_break_runs_split": result["coloring"]["page_break_runs_split"],
            }
        )
    report = {
        "evidence": "Independent authored synthetic code-point labels, not Word ground truth",
        "case_count": len(rows),
        "metrics": aggregate([r["accuracy"] for r in rows if "accuracy" in r]),
        "cases": rows,
    }
    (directory / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
