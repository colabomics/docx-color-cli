from zipfile import ZipFile

from helpers.fixtures import R_NS, W_NS, insert, p, rewrite, run
from lxml import etree

from docx_color_cli.cli import convert

STRICT_W = "http://purl.oclc.org/ooxml/wordprocessingml/main"
STRICT_R = "http://purl.oclc.org/ooxml/officeDocument/relationships"


def make_strict(source):
    with ZipFile(source) as z:
        data = {
            n: z.read(n)
            .replace(W_NS.encode(), STRICT_W.encode())
            .replace(R_NS.encode(), STRICT_R.encode())
            for n in z.namelist()
            if n.endswith((".xml", ".rels"))
        }
    rewrite(source, data)
    return source


def test_strict_namespace_preserved(docx, tmp_path):
    source = make_strict(docx("strict.docx", p(run("old") + insert("new"))))
    original = source.read_bytes()
    target = tmp_path / "out.docx"
    convert(source, target)
    with ZipFile(target) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        ns = "{" + STRICT_W + "}"
        assert root.tag == ns + "document"
        assert [n.text for n in root.iter(ns + "t")] == ["old", "new"]
        assert [n.get(ns + "val") for n in root.iter(ns + "color")] == [
            "000000",
            "FF0000",
        ]
        assert not list(root.iter(ns + "ins"))
        assert STRICT_R.encode() in z.read("_rels/.rels")
    assert source.read_bytes() == original


def test_strict_reference_comparison(docx, tmp_path):
    source = make_strict(docx("strict.docx", p(insert("new"))))
    reference = make_strict(docx("reference.docx", p(run("new"))))
    convert(source, tmp_path / "out.docx", reference=reference)
