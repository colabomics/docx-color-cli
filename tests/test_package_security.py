"""Bounded adversarial synthetic packages; no real manuscript or network access."""

from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from helpers.corpus import ins, p, package, run
from helpers.fidelity import digest
from helpers.fixtures import rewrite

from docx_color_cli import ColoringError, color_revisions
from docx_color_cli import package as opc


@pytest.mark.parametrize(
    "member",
    [
        "../outside.bin",
        "/absolute.bin",
        "C:/drive.bin",
        "..\\outside.bin",
        "customXml/./item.xml",
        "customXml//item.xml",
    ],
)
def test_unsafe_zip_names_refused_before_decompression(tmp_path, monkeypatch, member):
    a = package(tmp_path / "a.docx", p(ins("new")))
    b = package(tmp_path / "b.docx", p(run("new")))
    with ZipFile(a, "a") as z:
        z.writestr(member, b"<data/>")
    out = tmp_path / "out.docx"
    out.write_bytes(b"prior")
    hashes = digest(a), digest(b)
    monkeypatch.setattr(
        ZipFile, "testzip", lambda *a: pytest.fail("must not decompress unsafe archive")
    )
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, out)
    assert error.value.code == "INVALID_DOCX"
    assert out.read_bytes() == b"prior"
    assert (digest(a), digest(b)) == hashes
    assert {f.name for f in tmp_path.iterdir()} == {"a.docx", "b.docx", "out.docx"}


@pytest.mark.parametrize("limit", ["ratio", "members", "total", "xml"])
def test_expansion_budget_precedes_decompression(tmp_path, monkeypatch, limit):
    a = package(tmp_path / "a.docx", p(ins("new")))
    b = package(tmp_path / "b.docx", p(run("new")))
    if limit == "ratio":
        with ZipFile(a, "a", compression=ZIP_DEFLATED) as z:
            z.writestr("customXml/repetition.bin", b"0" * (2 * 1024 * 1024))
    else:
        # Exercise real guards at small limits without allocating enormous inputs.
        monkeypatch.setattr(
            opc,
            {
                "members": "MAX_ZIP_MEMBERS",
                "total": "MAX_ZIP_BYTES",
                "xml": "MAX_XML_BYTES",
            }[limit],
            1,
        )
    before = digest(a), digest(b)
    monkeypatch.setattr(
        ZipFile, "testzip", lambda *a: pytest.fail("budget must precede decompression")
    )
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, tmp_path / "out.docx")
    assert error.value.code == "UNSUPPORTED_CONTENT"
    assert (digest(a), digest(b)) == before
    assert {f.name for f in tmp_path.iterdir()} == {"a.docx", "b.docx"}


@pytest.mark.parametrize("entity", ["file", "http", "internal"])
def test_dtd_entities_are_rejected_without_payload_leak(tmp_path, entity):
    secret = tmp_path / "secret.txt"
    secret.write_text("LOCAL_SECRET_NEVER_DISCLOSE", encoding="utf-8")
    declaration = {
        "file": f'SYSTEM "{secret.as_uri()}"',
        "http": 'SYSTEM "http://127.0.0.1:1/no-network"',
        "internal": '"ENTITY_PAYLOAD_NEVER_DISCLOSE"',
    }[entity]
    a = package(tmp_path / "a.docx", p(ins("new")))
    b = package(tmp_path / "b.docx", p(run("new")))
    rewrite(
        a,
        {
            "customXml/unchanged.xml": f"<!DOCTYPE data [<!ENTITY probe {declaration}>]><data>&probe;</data>".encode()
        },
    )
    before = digest(a), digest(b)
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, tmp_path / "out.docx")
    assert error.value.code == "INVALID_DOCX"
    assert "SECRET" not in str(error.value) and "PAYLOAD" not in str(error.value)
    assert not (tmp_path / "out.docx").exists()
    assert (digest(a), digest(b)) == before


@pytest.mark.parametrize(
    "target",
    [
        "../../outside.bin",
        "https://example.test/internal",
        "file:///tmp/secret",
        "..\\outside.bin",
    ],
)
def test_invalid_internal_relationships_cannot_publish(tmp_path, target):
    a = package(tmp_path / "a.docx", p(ins("new")))
    b = package(tmp_path / "b.docx", p(run("new")))
    rewrite(
        a,
        {
            "word/_rels/document.xml.rels": (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="bad" Type="image" Target="'
                + target
                + '"/></Relationships>'
            ).encode()
        },
    )
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, tmp_path / "out.docx")
    assert error.value.code == "INVALID_DOCX"
    assert not (tmp_path / "out.docx").exists()
