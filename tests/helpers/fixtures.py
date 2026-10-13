"""Synthetic OPC fixtures with explicit, human-authored expected content.

No fixture builder interprets revisions or imports the conversion algorithm.
"""

from base64 import b64decode
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZipFile

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W = "{" + W_NS + "}"
M = "{" + M_NS + "}"
NSMAP = {"w": W_NS, "r": R_NS, "m": M_NS}
PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jf1sAAAAASUVORK5CYII="
)


def run(text, props=""):
    return f'<w:r>{"<w:rPr>" + props + "</w:rPr>" if props else ""}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def paragraph(text):
    return f"<w:p>{run(text)}</w:p>"


def p(content, props=""):
    return f"<w:p>{'<w:pPr>' + props + '</w:pPr>' if props else ''}{content}</w:p>"


def revision(kind, content, rid="1"):
    return f'<w:{kind} w:id="{rid}" w:author="Synthetic Test" w:date="2026-01-01T00:00:00Z">{content}</w:{kind}>'


def insert(text):
    return revision("ins", run(text))


def delete(text):
    return revision(
        "del", f'<w:r><w:delText xml:space="preserve">{escape(text)}</w:delText></w:r>'
    )


def story(kind, content):
    return f'<w:{kind} xmlns:w="{W_NS}" xmlns:r="{R_NS}" xmlns:m="{M_NS}">{content}</w:{kind}>'


def relationships(entries):
    children = []
    for rid, kind, target, external in entries:
        children.append(
            f"<Relationship Id={quoteattr(rid)} Type={quoteattr(R_NS + '/' + kind)} Target={quoteattr(target)}"
            + (' TargetMode="External"' if external else "")
            + "/>"
        )
    return (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(children)
        + "</Relationships>"
    )


def write_docx(path, body, parts=None):
    path = Path(path)
    document = (
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}" xmlns:m="{M_NS}" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f"<w:body>{body}</w:body></w:document>"
    )
    members = {"word/document.xml": document, **(parts or {})}
    entries = []
    overrides = [("word/document.xml", "document.main")]
    known = {
        "footnotes": "footnotes",
        "endnotes": "endnotes",
        "comments": "comments",
        "styles": "styles",
        "numbering": "numbering",
        "settings": "settings",
        "fontTable": "fontTable",
    }
    for name in members:
        stem = Path(name).stem
        kind = (
            "header"
            if stem.startswith("header")
            else "footer"
            if stem.startswith("footer")
            else known.get(stem)
        )
        if name.startswith("word/") and name.endswith(".xml") and kind:
            entries.append(("auto" + str(len(entries)), kind, name[5:], False))
            overrides.append((name, kind))
    members.setdefault("word/_rels/document.xml.rels", relationships(entries))
    members.setdefault(
        "_rels/.rels",
        relationships([("office", "officeDocument", "word/document.xml", False)]),
    )
    ct = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Default Extension="bin" ContentType="application/octet-stream"/>'
    ct += "".join(
        f'<Override PartName="/{name}" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml"/>'
        for name, kind in overrides
    )
    members.setdefault("[Content_Types].xml", ct + "</Types>")
    with ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def rewrite(path, changes):
    """Mutate synthetic packages only. None removes a member for negative tests."""
    with ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members.update(changes)
    with ZipFile(path, "w") as archive:
        for name, data in members.items():
            if data is not None:
                archive.writestr(name, data)


def field(code, result):
    return (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r><w:instrText xml:space="preserve">{escape(code)}</w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        + result
        + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )


def fraction():
    return '<m:oMath><m:f><m:fPr><m:type m:val="bar"/></m:fPr><m:num><m:r><m:t>x</m:t></m:r></m:num><m:den><m:r><m:t>y</m:t></m:r></m:den></m:f></m:oMath>'


def image_run():
    return """<w:r><w:drawing><wp:inline><wp:extent cx="9525" cy="9525"/>
    <wp:docPr id="1" name="Synthetic image"/><a:graphic>
    <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
    <pic:pic><pic:nvPicPr><pic:cNvPr id="1" name="pixel.png"/><pic:cNvPicPr/></pic:nvPicPr>
    <pic:blipFill><a:blip r:embed="image1"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
    <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="9525" cy="9525"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>
    </a:graphicData></a:graphic></wp:inline></w:drawing></w:r>"""
