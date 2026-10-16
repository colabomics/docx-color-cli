"""Independently authored, generic field and hyperlink character truth.

Only invented labels, example.com URLs and standard Word field primitives appear.
No document-specific text, revision history or object layout is reproduced.
"""

from html import escape

from .corpus import Case, ins, p, run

NEW, OLD = "INSERTED", "UNCHANGED"
URI = "https://example.com/"


def frame(content, ident="BADC0FFE"):
    return (
        '<w:p xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" w14:paraId="'
        + ident
        + '">'
        + content
        + "</w:p>"
    )


def insertion(content):
    return '<w:ins w:id="101">' + content + "</w:ins>"


def field(code, content):
    return (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve">'
        + escape(code)
        + "</w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        + content
        + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )


def link(content, attrs=""):
    return '<w:hyperlink r:id="web"' + attrs + ">" + content + "</w:hyperlink>"


def relationships(uri=URI):
    return {
        "word/_rels/document.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="web" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="'
        + escape(uri, quote=True)
        + '" TargetMode="External"/></Relationships>'
    }


def cases():
    rows = []

    def add(ident, source, target, spans, *, omit=False, uri=URI):
        c = Case(ident, ident.replace("_", " "), source, target, [spans])
        missed = sum(len(t) for t, label in spans if label == NEW) if omit else 0
        rows.append((c, missed, uri))

    result = run("label")
    code = ' HYPERLINK "https://example.com/" '
    add(
        "field_container",
        frame(
            run("Start ") + insertion(run("add ") + field(" QUOTE ", result) + run("!"))
        ),
        frame(run("Start add ") + field(" QUOTE ", result) + run("!")),
        [("Start ", OLD), ("add label!", NEW)],
    )
    add(
        "field_result_only",
        frame(run("Start ") + field(" QUOTE ", run("kept ") + ins("added"))),
        frame(run("Start ") + field(" QUOTE ", run("kept added"))),
        [("Start kept ", OLD), ("added", NEW)],
    )
    add(
        "field_adjacent_only",
        frame(field(" QUOTE ", result) + ins(" end")),
        frame(field(" QUOTE ", result) + run(" end")),
        [("label", OLD), (" end", NEW)],
    )
    add(
        "field_deleted_result",
        frame(
            field(
                " QUOTE ",
                '<w:del w:id="3"><w:r><w:delText>discard</w:delText></w:r></w:del>'
                + ins("replacement"),
            )
        ),
        frame(field(" QUOTE ", run("replacement"))),
        [("replacement", NEW)],
    )
    add(
        "field_repeated_display",
        frame(run("tag ") + insertion(field(" QUOTE ", run("tag"))) + run(" tag")),
        frame(run("tag ") + field(" QUOTE ", run("tag")) + run(" tag")),
        [("tag ", OLD), ("tag", NEW), (" tag", OLD)],
    )
    add(
        "field_insert_then_delete",
        frame(
            insertion(
                run("A")
                + '<w:del w:id="3"><w:r><w:delText>discard</w:delText></w:r></w:del>'
                + field(" QUOTE ", run("B"))
            )
        ),
        frame(run("A") + field(" QUOTE ", run("B"))),
        [("AB", NEW)],
    )
    add(
        "simple_field_result",
        frame(
            '<w:fldSimple w:instr="QUOTE">'
            + ins("Z")
            + "</w:fldSimple>"
            + run(" fixed")
        ),
        frame(
            '<w:fldSimple w:instr="QUOTE">'
            + run("Z")
            + "</w:fldSimple>"
            + run(" fixed")
        ),
        [("Z", NEW), (" fixed", OLD)],
    )
    add(
        "native_link_insert",
        frame(link(run("old ") + ins("site"))),
        frame(link(run("old site"))),
        [("old ", OLD), ("site", NEW)],
    )
    add(
        "link_representation",
        frame(
            run("Begin ")
            + insertion(run("Open ") + field(code, run("portal")) + run("."))
        ),
        frame(run("Begin Open ") + link(run("portal")) + run(".")),
        [("Begin ", OLD), ("Open portal.", NEW)],
    )
    add(
        "link_retained_display",
        frame(ins("Open ") + field(code, run("portal"))),
        frame(run("Open ") + link(run("portal"))),
        [("Open ", NEW), ("portal", OLD)],
    )
    add(
        "link_visit_switch",
        frame(insertion(field(code + r"\h ", run("portal")))),
        frame(link(run("portal"), ' w:history="1"')),
        [("portal", NEW)],
        omit=True,
    )
    add(
        "link_target_mismatch",
        frame(insertion(field(code, run("portal")))),
        frame(link(run("portal"))),
        [("portal", NEW)],
        omit=True,
        uri="https://example.com/other",
    )
    add(
        "link_tooltip_switch",
        frame(insertion(field(code + r'\o "tip" ', run("portal")))),
        frame(link(run("portal"))),
        [("portal", NEW)],
        omit=True,
    )
    add(
        "link_anchor_attribute",
        frame(insertion(field(code, run("portal")))),
        frame(link(run("portal"), ' w:anchor="section"')),
        [("portal", NEW)],
        omit=True,
    )
    add(
        "link_multiple_fields",
        frame(
            insertion(field(code, run("first")) + run(" ") + field(code, run("second")))
        ),
        frame(link(run("first")) + run(" ") + link(run("second"))),
        [("first second", NEW)],
        omit=True,
    )
    add(
        "link_nested_field",
        frame(insertion(field(code, field(" QUOTE ", run("nested"))))),
        frame(link(run("nested"))),
        [("nested", NEW)],
        omit=True,
    )
    add(
        "link_interval_mismatch",
        frame(insertion(run("same ") + field(code, run("same")))),
        frame(link(run("same")) + run(" same")),
        [("same same", NEW)],
        omit=True,
    )
    add(
        "link_field_locked",
        frame(
            insertion(
                field(code, run("portal")).replace(
                    'w:fldCharType="begin"', 'w:fldCharType="begin" w:fldLock="true"'
                )
            )
        ),
        frame(link(run("portal"))),
        [("portal", NEW)],
        omit=True,
    )
    change = (
        '<w:rPrChange w:id="9"><w:rPr><w:color w:val="AA3300"/></w:rPr></w:rPrChange>'
    )
    props = '<w:color w:val="2244AA"/><w:b/>'
    add(
        "format_only",
        frame(run("kept", props + change)),
        frame(run("kept", props)),
        [("kept", OLD)],
    )
    add(
        "insert_and_format",
        frame(insertion(run("added", props + change))),
        frame(run("added", props)),
        [("added", NEW)],
    )
    add(
        "native_link_format_only",
        frame(link(run("kept", props + change))),
        frame(link(run("kept", props))),
        [("kept", OLD)],
    )
    add(
        "existing_colors",
        frame(
            run("red", '<w:color w:val="FF0000"/>')
            + insertion(run("red", '<w:color w:val="FF0000"/>'))
        ),
        frame(run("red", '<w:color w:val="FF0000"/>') * 2),
        [("red", OLD), ("red", NEW)],
    )
    cell_a = frame(insertion(field(" QUOTE ", run("cell label"))))
    cell_b = frame(field(" QUOTE ", run("cell label")))

    def table(content):
        return (
            '<w:tbl><w:tblGrid><w:gridCol w:w="1200"/></w:tblGrid><w:tr><w:tc>'
            + content
            + "</w:tc></w:tr></w:tbl>"
        )

    add("field_in_cell", table(cell_a), table(cell_b), [("cell label", NEW)])
    shared = field(" QUOTE ", run("entry"))
    c = Case(
        "repeated_field_paragraphs",
        "identical field paragraphs without anchors",
        p(shared) + p(insertion(shared)),
        p(shared) + p(shared),
        [[("entry", OLD)], [("entry", NEW)]],
    )
    rows.append((c, 5, URI))
    return rows
