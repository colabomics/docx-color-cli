"""Check mode must exercise conversion and staged-package validation without publishing."""

import subprocess
import sys
from pathlib import Path

import pytest
from helpers.fixtures import insert, p, paragraph, rewrite, run

from docx_color_cli import cli
from docx_color_cli.errors import ConversionError


@pytest.mark.parametrize(
    "body",
    [
        p(run("unchanged") + insert("new")),
        p(
            '<w:fldSimple w:instr="HYPERLINK &quot;https://example.org&quot;">'
            + run("link")
            + "</w:fldSimple>"
        ),
        p(
            '<w:bookmarkStart w:id="1" w:name="target"/>'
            + run("target")
            + '<w:bookmarkEnd w:id="1"/>'
        ),
        p("<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>"),
    ],
)
def test_check_success_without_publication(docx, tmp_path, monkeypatch, capsys, body):
    source = docx("source.docx", body)
    existing = docx("source_colored.docx", paragraph("previous output"))
    before = {f: f.read_bytes() for f in (source, existing)}

    def forbidden(*args, **kwargs):
        pytest.fail("check must never publish a file")

    monkeypatch.setattr(Path, "replace", forbidden)
    cli.main([str(source), "--check"])
    captured = capsys.readouterr()
    assert "Check passed:" in captured.out
    assert "Saved:" not in captured.out
    assert not captured.err
    assert {f: f.read_bytes() for f in tmp_path.iterdir()} == before


@pytest.mark.parametrize(
    "case",
    ["unsupported", "bad-zip", "bad-xml", "field", "table", "math", "relationship"],
)
def test_check_invalid_input_exits_without_output(docx, tmp_path, case):
    bodies = {
        "unsupported": p(run("keep"), '<w:rPr><w:del w:id="1"/></w:rPr>'),
        "field": p('<w:r><w:fldChar w:fldCharType="end"/></w:r>'),
        "table": "<w:tbl><w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr>"
        + paragraph("keep")
        + "</w:tc></w:tr></w:tbl>",
        "math": p(
            "<m:oMath><m:f><m:num><m:r><m:t>x</m:t></m:r></m:num></m:f></m:oMath>"
        ),
        "relationship": p(
            '<w:hyperlink r:id="missing">' + run("link") + "</w:hyperlink>"
        ),
    }
    source = docx("source.docx", bodies.get(case, paragraph("keep")))
    if case == "bad-zip":
        source.write_bytes(b"not a zip")
    elif case == "bad-xml":
        rewrite(source, {"word/document.xml": b"<broken>"})
    before = source.read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "docx_color_cli.cli", str(source), "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert result.stderr and "Traceback" not in result.stderr
    assert not result.stdout
    assert source.read_bytes() == before
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize("option", ["output", "report"])
def test_check_rejects_publication_arguments(docx, tmp_path, capsys, option):
    source = docx("source.docx", paragraph("keep"))
    args = (
        [str(tmp_path / "out.docx")]
        if option == "output"
        else ["--report", str(tmp_path / "report.json")]
    )
    with pytest.raises(SystemExit) as error:
        cli.main([str(source), "--check", *args])
    assert error.value.code == 2
    assert "--check cannot be combined" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize("matches", [True, False])
def test_check_reference_and_temporary_cleanup(docx, tmp_path, monkeypatch, matches):
    source = docx("source.docx", p(insert("new")))
    reference = docx("reference.docx", paragraph("new" if matches else "different"))
    before = {f: f.read_bytes() for f in (source, reference)}
    temporary = cli.TemporaryDirectory
    directories = []

    def local_directory(**kwargs):
        result = temporary(dir=tmp_path, **kwargs)
        directories.append(Path(result.name))
        return result

    monkeypatch.setattr(cli, "TemporaryDirectory", local_directory)
    if matches:
        assert cli.check(source, reference=reference)["reference_validated"] == 1
    else:
        with pytest.raises(ConversionError, match="Content validation failed"):
            cli.check(source, reference=reference)
    assert directories and all(not d.exists() for d in directories)
    assert {f: f.read_bytes() for f in tmp_path.iterdir()} == before


def test_check_runs_retention_guard(docx, tmp_path, monkeypatch):
    source = docx("source.docx", paragraph("keep"))
    original_modify = cli.modify

    def corrupt(root, *args):
        original_modify(root, *args)
        root.find(
            ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
        ).text = "lost"

    monkeypatch.setattr(cli, "modify", corrupt)
    with pytest.raises(ConversionError, match="retained content changed"):
        cli.check(source)
    assert list(tmp_path.iterdir()) == [source]


def test_check_cli_success_exit(docx):
    source = docx("source.docx", paragraph("keep"))
    result = subprocess.run(
        [sys.executable, "-m", "docx_color_cli.cli", str(source), "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert not result.stderr
    assert not source.with_name("source_colored.docx").exists()
