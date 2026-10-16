"""Migrated acceptance retention guards, injected into the current pipeline."""

from copy import deepcopy
from zipfile import ZipFile

import pytest
from helpers.fixtures import insert, p, run

from docx_color_cli import ColoringError, color_revisions, engine
from docx_color_cli.projection import W


@pytest.mark.parametrize(
    "damage", ["lost", "duplicate", "reordered", "paragraph", "cell"]
)
def test_content_or_boundary_loss_cannot_publish(docx, tmp_path, monkeypatch, damage):
    source_body = p(run("first")) + p(insert("second"))
    accepted_body = p(run("first")) + p(run("second"))
    if damage == "cell":

        def table(content):
            return (
                "<w:tbl><w:tr><w:tc>"
                + content.replace("</w:p><w:p>", "</w:p></w:tc><w:tc><w:p>")
                + "</w:tc></w:tr></w:tbl>"
            )

        source_body, accepted_body = table(source_body), table(accepted_body)
    a, b = docx("a.docx", source_body), docx("b.docx", accepted_body)
    out = tmp_path / "out.docx"
    out.write_bytes(b"previous")
    before = {f: f.read_bytes() for f in tmp_path.iterdir()}
    original = engine.color

    def corrupt(*args):
        result, roots = original(*args)
        root = next(iter(roots))
        if damage in {"paragraph", "cell"}:
            nodes = list(root.iter(W + ("p" if damage == "paragraph" else "tc")))
            for child in list(nodes[1]):
                nodes[0].append(child)
            nodes[1].getparent().remove(nodes[1])
        else:
            node = list(root.iter(W + "r"))[-1]
            parent = node.getparent()
            if damage == "lost":
                parent.remove(node)
            elif damage == "duplicate":
                parent.append(deepcopy(node))
            else:
                list(root.iter(W + "p"))[0].insert(0, node)
        return result, roots

    monkeypatch.setattr(engine, "color", corrupt)
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, out)
    assert error.value.code == "INTERNAL_ERROR"
    assert {f: f.read_bytes() for f in tmp_path.iterdir()} == before


@pytest.mark.parametrize(
    "damage",
    ["residual", "broken-field", "bad-relationship", "missing-member", "changed-text"],
)
@pytest.mark.parametrize("existing", [False, True])
def test_staged_package_corruption_cannot_publish(
    docx, tmp_path, monkeypatch, damage, existing
):
    a = docx("a.docx", p(insert("original")))
    b = docx("b.docx", p(run("original")))
    out = tmp_path / "out.docx"
    if existing:
        out.write_bytes(b"previous")
    before = {f: f.read_bytes() for f in tmp_path.iterdir()}
    write = ZipFile.writestr

    def corrupt(self, info, data, *args, **kwargs):
        name = info.filename if hasattr(info, "filename") else info
        if name == "word/document.xml":
            if damage == "missing-member":
                return
            if damage == "changed-text":
                data = data.replace(b"original", b"altered")
            nodes = {
                "residual": '<w:ins w:id="1"/>',
                "broken-field": '<w:r><w:fldChar w:fldCharType="end"/></w:r>',
                "bad-relationship": '<w:hyperlink r:id="absent"/>',
            }
            if damage in nodes:
                data = data.replace(b"</w:p>", nodes[damage].encode() + b"</w:p>")
        return write(self, info, data, *args, **kwargs)

    monkeypatch.setattr(ZipFile, "writestr", corrupt)
    with pytest.raises(ColoringError):
        color_revisions(a, b, out)
    assert {f: f.read_bytes() for f in tmp_path.iterdir()} == before
