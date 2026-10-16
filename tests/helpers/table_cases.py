"""Independently authored table provenance, including explicit expected omissions."""

from helpers.corpus import INSERTED as I
from helpers.corpus import UNCHANGED as U
from helpers.corpus import Case, cell, delete, ins, p, run

ROW_FORMAT = '<w:tblPrEx><w:tblW w:w="0" w:type="auto"/></w:tblPrEx><w:trPr><w:cantSplit/></w:trPr>'


def row(cells, props=""):
    return "<w:tr>" + props + "".join(cells) + "</w:tr>"


def table(rows, props=""):
    return "<w:tbl>" + props + "".join(rows) + "</w:tbl>"


def values(*texts):
    return [cell(p(run(t))) for t in texts]


def replacement(old, new):
    return cell(p(delete(old) + ins(new)))


def cases():
    result = []

    def add(name, tracked, accepted, truth, missed=0, invalid=False):
        result.append(
            (Case("table_" + name, name, tracked, accepted, truth), missed, invalid)
        )

    def pair(name, source, target, truth, missed=0):
        add(name, table([row(source)]), table([row(target, ROW_FORMAT)]), truth, missed)

    pair(
        "simple",
        [replacement("10", "12"), *values("keep")],
        values("12", "keep"),
        [[("12", I)], [("keep", U)]],
    )
    pair(
        "multiple",
        [replacement("10", "12"), replacement("0.25", "0.30")],
        values("12", "0.30"),
        [[("12", I)], [("0.30", I)]],
    )
    pair(
        "repeated",
        [*values("12"), replacement("10", "12"), *values("12")],
        values("12", "12", "12"),
        [[("12", U)], [("12", I)], [("12", U)]],
    )
    pair(
        "adjacent",
        [replacement("10", "12"), *values("120")],
        values("12", "120"),
        [[("12", I)], [("120", U)]],
    )
    pair(
        "paragraphs",
        [cell(p(run("first")) + p(run("old ") + ins("new")))],
        [cell(p(run("first")) + p(run("old new")))],
        [[("first", U)], [("old ", U), ("new", I)]],
    )
    # An insertion in the second cell cannot select identical text in the first.
    add(
        "reverse_properties",
        table([row([*values("12"), replacement("10", "12")], ROW_FORMAT)]),
        table([row(values("12", "12"))]),
        [[("12", U)], [("12", I)]],
    )
    pair(
        "duplicate_paragraphs",
        [cell(p(ins("same")) + p(run("same")))],
        [cell(p(run("same")) * 2)],
        [[("same", I)], [("same", U)]],
        missed=4,
    )
    pair(
        "duplicate_across_cells",
        [cell(p(ins("same"))), *values("same")],
        values("same", "same"),
        [[("same", I)], [("same", U)]],
    )
    pair(
        "split_runs",
        [
            cell(
                p(
                    delete("0.25")
                    + '<w:ins w:id="2">'
                    + run("0.")
                    + run("30", "<w:b/>")
                    + "</w:ins>"
                )
            )
        ],
        [cell(p(run("0.") + run("30", "<w:b/>")))],
        [[("0.30", I)]],
    )
    color = '<w:color w:val="008080"/>'
    change = '<w:rPrChange w:id="4"><w:rPr><w:i/></w:rPr></w:rPrChange>'
    pair(
        "format_only",
        [cell(p(run("keep", color + "<w:b/>" + change)))],
        [cell(p(run("keep", color + "<w:b/>")))],
        [[("keep", U)]],
    )
    pair(
        "existing_colors",
        [cell(p(run("keep", '<w:color w:val="FF0000"/>') + ins("new", props=color)))],
        [cell(p(run("keep", '<w:color w:val="FF0000"/>') + run("new", color)))],
        [[("keep", U), ("new", I)]],
    )
    props = '<w:tcW w:w="2000" w:type="dxa"/>'
    pair(
        "property_siblings",
        [cell(p(run("old ") + ins("new")), props)],
        [cell(p(run("old new", "<w:b/>"), "<w:keepNext/>"), props)],
        [[("old ", U), ("new", I)]],
    )
    add(
        "table_properties",
        table([row([replacement("A", "B")])]),
        table(
            [row(values("B"))],
            '<w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tblGrid><w:gridCol w:w="2000"/></w:tblGrid>',
        ),
        [[("B", I)]],
    )
    add(
        "body_and_table",
        p(run("body ") + ins("new")) + table([row([replacement("A", "B")])]),
        p(run("body new")) + table([row(values("B"), ROW_FORMAT)]),
        [[("body ", U), ("new", I)], [("B", I)]],
    )
    nested_source = table([row([replacement("10", "12")])])
    nested_target = table([row(values("12"), ROW_FORMAT)])
    pair(
        "nested",
        [cell(p(run("12")) + nested_source + p(run("end"))), *values("12")],
        [cell(p(run("12")) + nested_target + p(run("end"))), *values("12")],
        [[("12", U)], [("12", I)], [("end", U)], [("12", U)]],
    )
    span = '<w:gridSpan w:val="2"/>'
    add(
        "row_grid_mismatch",
        table([row([replacement("10", "12")])]),
        table([row(values("12"), '<w:trPr><w:gridBefore w:val="1"/></w:trPr>')]),
        [[("12", I)]],
        missed=2,
    )
    top = '<w:vMerge w:val="restart"/>'
    bottom = "<w:vMerge/>"
    add(
        "merged",
        table(
            [
                row([cell(p(ins("12")), span + top), *values("keep")]),
                row([cell(p(run("")), span + bottom), *values("end")]),
            ]
        ),
        table(
            [
                row([cell(p(run("12")), span + top), *values("keep")], ROW_FORMAT),
                row([cell(p(run("")), span + bottom), *values("end")], ROW_FORMAT),
            ]
        ),
        [[("12", I)], [("keep", U)], [], [("end", U)]],
    )
    # Same physical cell count cannot certify a changed logical grid.
    pair(
        "merge_mismatch",
        [cell(p(ins("12")), span), *values("keep")],
        [cell(p(run("12"))), cell(p(run("keep")), span)],
        [[("12", I)], [("keep", U)]],
        missed=2,
    )
    pair(
        "vertical_merge_mismatch",
        [cell(p(ins("12")), top)],
        [cell(p(run("12")), bottom)],
        [[("12", I)]],
        missed=2,
    )
    # Row markers do not assign character insertion provenance to row text.
    add(
        "row_insert_marker",
        table([row(values("keep"), '<w:trPr><w:ins w:id="5"/></w:trPr>')]),
        table([row(values("keep"), ROW_FORMAT)]),
        [[("keep", U)]],
    )
    add(
        "row_insert_and_text",
        table([row([replacement("10", "12")], '<w:trPr><w:ins w:id="5"/></w:trPr>')]),
        table([row(values("12"), ROW_FORMAT)]),
        [[("12", I)]],
        missed=2,
    )
    add(
        "row_delete",
        table(
            [
                row(values("gone"), '<w:trPr><w:del w:id="5"/></w:trPr>'),
                row([replacement("10", "12")]),
            ]
        ),
        table([row(values("12"), ROW_FORMAT)]),
        [[("12", I)]],
        missed=2,
    )
    pair(
        "cell_revision",
        [cell(p(ins("12")), '<w:cellIns w:id="8"/>')],
        values("12"),
        [[("12", I)]],
        missed=2,
    )
    math_source = '<m:oMath><m:r><m:t>x+</m:t></m:r><w:ins w:id="7"><m:r><m:t>2</m:t></m:r></w:ins></m:oMath>'
    math_target = "<m:oMath><m:r><m:t>x+</m:t></m:r><m:r><m:t>2</m:t></m:r></m:oMath>"
    pair(
        "math", [cell(p(math_source))], [cell(p(math_target))], [[("x+", U), ("2", I)]]
    )
    add(
        "incompatible",
        table([row([replacement("10", "12")])]),
        table([row(values("unrelated"), ROW_FORMAT)]),
        [[("unrelated", U)]],
        invalid=True,
    )
    return result
