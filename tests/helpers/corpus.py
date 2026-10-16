"""Level A: explicit, authored truth; never derived from tracked XML or a mapper.

These are synthetic OOXML packages, NOT Microsoft Word-produced references.
Every expected display character is declared INSERTED or UNCHANGED, even when
the POC refuses to map it. Refusal therefore contributes a real false negative.
"""

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from helpers.fidelity import M, W

R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
INSERTED, UNCHANGED = "INSERTED", "UNCHANGED"


def run(text, props="", stamp="000000AA"):
    return (
        f'<w:r w:rsidR="{stamp}">'
        + (f"<w:rPr>{props}</w:rPr>" if props else "")
        + f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
    )


def ins(text, ident="1", props=""):
    return f'<w:ins w:id="{ident}" w:author="Synthetic Author {ident}" w:date="2026-01-01T00:00:00Z">{run(text, props)}</w:ins>'


def delete(text):
    return (
        '<w:del w:id="9"><w:r><w:delText xml:space="preserve">'
        + escape(text)
        + "</w:delText></w:r></w:del>"
    )


def p(content, props=""):
    return "<w:p>" + (f"<w:pPr>{props}</w:pPr>" if props else "") + content + "</w:p>"


def cell(content, props=""):
    return (
        "<w:tc>" + (f"<w:tcPr>{props}</w:tcPr>" if props else "") + content + "</w:tc>"
    )


def table(rows, columns=1):
    return (
        "<w:tbl><w:tblGrid>"
        + '<w:gridCol w:w="2400"/>' * columns
        + "</w:tblGrid>"
        + rows
        + "</w:tbl>"
    )


def field():
    return (
        '<w:fldSimple w:instr="ADDIN ZOTERO_ITEM synthetic">'
        + run("[1]")
        + "</w:fldSimple>"
    )


def package(path, body, extra=None):
    members = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="bin" ContentType="application/octet-stream"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="main" Type="{R}/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": f'<w:document xmlns:w="{W[1:-1]}" xmlns:m="{M[1:-1]}" xmlns:r="{R}"><w:body>{body}</w:body></w:document>',
        "customXml/unchanged.xml": '<audit preserve="yes"/>',
        **(extra or {}),
    }
    with ZipFile(path, "w") as archive:
        for name, data in sorted(members.items()):
            info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    return Path(path)


@dataclass
class Case:
    ident: str
    name: str
    tracked: str
    accepted: str
    expected: list

    def truth(self):
        result = {}
        for pi, spans in enumerate(self.expected):
            offset = 0
            for value, label in spans:
                for _ in value:
                    result["word/document.xml", pi, offset] = label
                    offset += 1
        return result

    def manifest(self):
        return {
            "id": self.ident,
            "name": self.name,
            "evidence": "LEVEL_A_AUTHORED_SYNTHETIC_NOT_WORD_GROUND_TRUTH",
            "paragraphs": [
                {
                    "text": "".join(t for t, _ in spans),
                    "labels": [label for t, label in spans for _ in t],
                }
                for spans in self.expected
            ],
        }


def cases():
    mark = '<w:rPr><w:del w:id="8"/></w:rPr>'
    formula = "<m:oMath><m:r><m:t>x²</m:t></m:r></m:oMath>"
    red, blue = '<w:color w:val="FF0000"/>', '<w:color w:val="0000FF"/>'
    return [
        Case(
            "S01",
            "single insertion",
            p(run("A ") + ins("new") + run(" word.")),
            p(run("A new word.")),
            [[("A ", UNCHANGED), ("new", INSERTED), (" word.", UNCHANGED)]],
        ),
        Case(
            "S02",
            "multiple insertions/authors",
            p(ins("one", "1") + run(" and ") + ins("two", "2")),
            p(run("one and two")),
            [[("one", INSERTED), (" and ", UNCHANGED), ("two", INSERTED)]],
        ),
        Case(
            "S03",
            "deletion",
            p(run("A") + delete("obsolete") + run("B")),
            p(run("AB")),
            [[("AB", UNCHANGED)]],
        ),
        Case(
            "S04",
            "replacement",
            p(run("A ") + delete("bad") + ins("good")),
            p(run("A good")),
            [[("A ", UNCHANGED), ("good", INSERTED)]],
        ),
        Case(
            "S05",
            "repeated words",
            p(run("word ") + ins("word") + run(" word")),
            p(run("word word word")),
            [[("word ", UNCHANGED), ("word", INSERTED), (" word", UNCHANGED)]],
        ),
        Case(
            "S06",
            "repeated sentences",
            p(run("Same. ") + ins("Same.") + run(" Same.")),
            p(run("Same. Same. Same.")),
            [[("Same. ", UNCHANGED), ("Same.", INSERTED), (" Same.", UNCHANGED)]],
        ),
        Case(
            "S07",
            "multiple identical insertions",
            p(ins("x", "1") + run(" x ") + ins("x", "2")),
            p(run("x x x")),
            [[("x", INSERTED), (" x ", UNCHANGED), ("x", INSERTED)]],
        ),
        Case(
            "S08",
            "mixed old and new",
            p(run("old") + ins("NEW") + run("old")),
            p(run("oldNEWold")),
            [[("old", UNCHANGED), ("NEW", INSERTED), ("old", UNCHANGED)]],
        ),
        Case(
            "S09",
            "merged runs",
            p(
                run("a")
                + '<w:ins w:id="1">'
                + run("n")
                + run("ew")
                + "</w:ins>"
                + run("z")
            ),
            p(run("anewz")),
            [[("a", UNCHANGED), ("new", INSERTED), ("z", UNCHANGED)]],
        ),
        Case(
            "S10",
            "split runs",
            p(run("a") + ins("new") + run("z")),
            p(run("an") + run("e") + run("wz")),
            [[("a", UNCHANGED), ("new", INSERTED), ("z", UNCHANGED)]],
        ),
        Case(
            "S11",
            "paragraph merge",
            p(run("LEFT"))
            + p(run("a") + ins("new"), mark)
            + p(run("z"))
            + p(run("RIGHT")),
            p(run("LEFT")) + p(run("anewz")) + p(run("RIGHT")),
            [
                [("LEFT", UNCHANGED)],
                [("a", UNCHANGED), ("new", INSERTED), ("z", UNCHANGED)],
                [("RIGHT", UNCHANGED)],
            ],
        ),
        Case(
            "S12",
            "paragraph deletion",
            p(delete("gone"), mark) + p(ins("new")),
            p(run("new")),
            [[("new", INSERTED)]],
        ),
        Case(
            "S13",
            "table cell",
            table("<w:tr>" + cell(p(run("cell ") + ins("new"))) + "</w:tr>"),
            table("<w:tr>" + cell(p(run("cell new"))) + "</w:tr>"),
            [[("cell ", UNCHANGED), ("new", INSERTED)]],
        ),
        Case(
            "S14",
            "deleted row",
            table(
                '<w:tr><w:trPr><w:del w:id="8"/></w:trPr>'
                + cell(p(run("gone")))
                + "</w:tr><w:tr>"
                + cell(p(run("cell ") + ins("new")))
                + "</w:tr>"
            ),
            table("<w:tr>" + cell(p(run("cell new"))) + "</w:tr>"),
            [[("cell ", UNCHANGED), ("new", INSERTED)]],
        ),
        Case(
            "S15",
            "deleted column",
            table(
                "<w:tr>"
                + cell(p(run("gone")), '<w:cellDel w:id="8"/>')
                + cell(p(run("cell ") + ins("new")))
                + "</w:tr>",
                2,
            ),
            table("<w:tr>" + cell(p(run("cell new"))) + "</w:tr>"),
            [[("cell ", UNCHANGED), ("new", INSERTED)]],
        ),
        Case(
            "S16",
            "equation adjacent",
            p(formula + ins(" new")),
            p(formula + run(" new")),
            [[("x²", UNCHANGED), (" new", INSERTED)]],
        ),
        Case(
            "S17",
            "field adjacent",
            p(field() + ins(" new")),
            p(field() + run(" new")),
            [[("[1]", UNCHANGED), (" new", INSERTED)]],
        ),
        Case(
            "S18",
            "hyperlink display",
            p(
                '<w:hyperlink w:anchor="target">'
                + run("old")
                + ins("new")
                + "</w:hyperlink>"
            ),
            p('<w:hyperlink w:anchor="target">' + run("oldnew") + "</w:hyperlink>"),
            [[("old", UNCHANGED), ("new", INSERTED)]],
        ),
        Case(
            "S19",
            "existing red and other colors",
            p(
                run("oldred", red)
                + run("-")
                + ins("newred", "1", red)
                + ins("blue", "2", blue)
            ),
            p(run("oldred", red) + run("-") + run("newred", red) + run("blue", blue)),
            [[("oldred-", UNCHANGED), ("newredblue", INSERTED)]],
        ),
        Case(
            "S20",
            "Unicode and Chinese",
            p(run("结果α") + ins("中文e\u0301🚀") + run("。")),
            p(run("结果α中文e\u0301🚀。")),
            [[("结果α", UNCHANGED), ("中文e\u0301🚀", INSERTED), ("。", UNCHANGED)]],
        ),
        Case(
            "S21",
            "whitespace punctuation",
            p(run("a") + ins("  ，! ") + run("b")),
            p(run("a  ，! b")),
            [[("a", UNCHANGED), ("  ，! ", INSERTED), ("b", UNCHANGED)]],
        ),
        Case(
            "S22",
            "identical paragraphs",
            p(run("same")) + p(ins("same")),
            p(run("same")) * 2,
            [[("same", UNCHANGED)], [("same", INSERTED)]],
        ),
        Case(
            "S23",
            "move revisions",
            p('<w:moveFrom w:id="7">' + run("moved") + "</w:moveFrom>")
            + p('<w:moveTo w:id="8">' + run("moved") + "</w:moveTo>")
            + p(ins("new")),
            p(run("moved")) + p(run("new")),
            [[("moved", UNCHANGED)], [("new", INSERTED)]],
        ),
        Case(
            "S24",
            "inserted then deleted",
            p(
                '<w:ins w:id="1">'
                + run("n")
                + delete("gone")
                + run("ew")
                + "</w:ins>"
                + run(" old")
            ),
            p(run("new old")),
            [[("new", INSERTED), (" old", UNCHANGED)]],
        ),
        Case(
            "S25",
            "complex ambiguity",
            p(
                '<w:del w:id="9"><w:r><w:fldChar w:fldCharType="begin"/></w:r></w:del>'
                + ins("x")
                + run("x")
            ),
            p(run("xx")),
            [[("x", INSERTED), ("x", UNCHANGED)]],
        ),
    ]


def materialize(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for case in cases():
        target = directory / case.ident
        target.mkdir(exist_ok=True)
        package(target / "tracked.docx", case.tracked)
        package(target / "accepted.docx", case.accepted)
        (target / "expected.json").write_text(
            json.dumps(case.manifest(), indent=2, ensure_ascii=False) + "\n"
        )
    return [c.manifest() for c in cases()]
