"""Supported three-file CLI and public API; no legacy acceptance calls."""

import json
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest
from helpers.corpus import ins, p, package, run
from helpers.fidelity import compare, digest

from docx_color_cli import ColoringError, color_revisions, engine
from docx_color_cli.cli import main


def inputs(tmp_path):
    return package(tmp_path / "tracked.docx", p(run("old ") + ins("new"))), package(
        tmp_path / "accepted.docx", p(run("old new"))
    )


@pytest.mark.parametrize("flag", ["--help", "--version"])
def test_cli_information(flag, capsys):
    with pytest.raises(SystemExit) as error:
        main([flag])
    assert error.value.code == 0
    text = capsys.readouterr().out
    assert (
        ("TRACKED ACCEPTED OUTPUT" in text)
        if flag == "--help"
        else text.strip().endswith(version("docx-color-cli"))
    )


@pytest.mark.parametrize("arguments", [["old.docx"], ["old.docx", "output.docx"]])
def test_legacy_invocation_is_actionable_and_does_not_run(
    arguments, capsys, monkeypatch
):
    monkeypatch.setattr(
        engine, "Package", lambda *a, **k: pytest.fail("must not read documents")
    )
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
    text = capsys.readouterr().err
    assert "TRACKED ACCEPTED OUTPUT" in text and "Word" in text


@pytest.mark.parametrize(
    "flag", ["--no-strict", "--check", "--unchanged-color", "--reference"]
)
def test_retired_or_unrelated_options_rejected(flag, capsys):
    with pytest.raises(SystemExit) as error:
        main(["a.docx", "b.docx", "c.docx", flag])
    assert error.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_installed_module_from_another_directory(tmp_path):
    a, b = inputs(tmp_path)
    out = tmp_path / "nested/out.docx"
    report = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "docx_color_cli.cli",
            str(a),
            str(b),
            str(out),
            "--report",
            str(report),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and "SUCCESS" in result.stdout
    data = json.loads(report.read_text())
    assert (
        data["publication_status"]
        == data["coloring_status"]
        == data["overall_status"]
        == "SUCCESS"
    )
    assert data["coloring"]["characters_colored"] == 3
    assert data["publication"]["output_sha256"] == digest(out)
    assert (
        compare(b, out, allowed={("word/document.xml", 0, i) for i in range(4, 7)})[0][
            "overall"
        ]
        == "PASS"
    )


@pytest.mark.parametrize("role", ["tracked", "accepted"])
@pytest.mark.parametrize("damage", ["missing", "invalid-zip", "invalid-xml"])
def test_invalid_inputs_preserve_prior_output(tmp_path, role, damage, capsys):
    a, b = inputs(tmp_path)
    path = a if role == "tracked" else b
    if damage == "missing":
        path.unlink()
    elif damage == "invalid-zip":
        path.write_bytes(b"not ZIP")
    else:
        from helpers.fixtures import rewrite

        rewrite(path, {"word/document.xml": b"<private-secret invalid>"})
    out = tmp_path / "out.docx"
    out.write_bytes(b"prior valid output")
    assert main([str(a), str(b), str(out)]) == 1
    captured = capsys.readouterr()
    assert (
        "INVALID_DOCX" in captured.err
        and "Traceback" not in captured.err
        and "private-secret" not in captured.err
    )
    assert out.read_bytes() == b"prior valid output"


def test_mismatched_pair_even_with_common_heading_fails(tmp_path):
    a = package(tmp_path / "a.docx", p(run("Shared heading")) + p(ins("alpha")))
    b = package(tmp_path / "b.docx", p(run("Shared heading")) + p(run("unrelated β")))
    out = tmp_path / "out.docx"
    out.write_bytes(b"prior")
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, out)
    assert error.value.code == "INVALID_DOCUMENT_PAIR"
    assert error.value.result["overall_status"] == "FAILED"
    assert out.read_bytes() == b"prior"


def test_unaccepted_reference_is_invalid_pair(tmp_path):
    a, b = inputs(tmp_path)
    b = package(b, p(ins("old new")))
    with pytest.raises(ColoringError, match="Accept all changes") as error:
        color_revisions(a, b, tmp_path / "out.docx")
    assert error.value.code == "INVALID_DOCUMENT_PAIR"


@pytest.mark.parametrize("target", ["tracked", "accepted"])
@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_input_aliases_rejected_before_processing(tmp_path, monkeypatch, target, alias):
    a, b = inputs(tmp_path)
    original = a if target == "tracked" else b
    out = original if alias == "same" else tmp_path / "alias.docx"
    if alias != "same":
        try:
            out.symlink_to(original) if alias == "symlink" else out.hardlink_to(
                original
            )
        except OSError as exc:
            pytest.skip(f"Filesystem aliases unavailable: {type(exc).__name__}")
    before = [digest(a), digest(b)]
    monkeypatch.setattr(
        engine,
        "Package",
        lambda *a, **k: pytest.fail("must reject aliases before parsing"),
    )
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, out)
    assert error.value.code == "OUTPUT_ERROR"
    assert [digest(a), digest(b)] == before


@pytest.mark.parametrize("color", ["#FF0000", "GG0000", "FFF", "1234567", "", None])
def test_invalid_color(tmp_path, color):
    a, b = inputs(tmp_path)
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, tmp_path / "out.docx", color)
    assert error.value.code == "INVALID_COLOR"
    assert not (tmp_path / "out.docx").exists()


def test_custom_color(tmp_path):
    a, b = inputs(tmp_path)
    out = tmp_path / "out.docx"
    assert main([str(a), "--color", "00aa0f", str(b), str(out)]) == 0
    assert (
        compare(
            b,
            out,
            allowed={("word/document.xml", 0, i) for i in range(4, 7)},
            rgb="00AA0F",
        )[0]["overall"]
        == "PASS"
    )


def test_partial_coverage_is_not_complete(tmp_path, capsys):
    a = package(tmp_path / "a.docx", p(run("same")) + p(ins("same")))
    b = package(tmp_path / "b.docx", p(run("same")) * 2)
    out = tmp_path / "out.docx"
    report = tmp_path / "report.json"
    assert main([str(a), str(b), str(out), "--report", str(report)]) == 0
    result = json.loads(report.read_text())
    assert result["publication_status"] == "SUCCESS"
    assert result["coloring_status"] == result["overall_status"] == "PARTIAL"
    assert result["completeness"]["eligible_characters_uncolored"] == 4
    assert "incomplete" in capsys.readouterr().err
    assert compare(b, out, allowed=set())[0]["overall"] == "PASS"


def test_report_failure_after_docx_is_explicit_partial(tmp_path, monkeypatch, capsys):
    a, b = inputs(tmp_path)
    out = tmp_path / "out.docx"
    report = tmp_path / "report.json"
    report.write_bytes(b"old report")
    original = Path.replace

    def replace(self, target):
        if Path(target) == report:
            raise PermissionError("injected")
        return original(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    assert main([str(a), str(b), str(out), "--report", str(report)]) == 0
    captured = capsys.readouterr()
    assert (
        "PARTIAL" in captured.out
        and "DOCX was published" in captured.err
        and "stale" in captured.err
    )
    assert report.read_bytes() == b"old report"
    assert out.exists()
    assert {p.name for p in tmp_path.iterdir()} == {
        "tracked.docx",
        "accepted.docx",
        "out.docx",
        "report.json",
    }


def test_generated_content_corruption_is_not_published(tmp_path, monkeypatch):
    from docx_color_cli.projection import W

    a, b = inputs(tmp_path)
    out = tmp_path / "out.docx"
    out.write_bytes(b"prior")
    original = engine.color

    def damaged(*args):
        result, roots = original(*args)
        next(iter(roots)).find(".//" + W + "t").text = "corrupted"
        return result, roots

    monkeypatch.setattr(engine, "color", damaged)
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, out)
    assert error.value.code == "INTERNAL_ERROR"
    assert out.read_bytes() == b"prior"


def test_report_never_contains_document_payload(tmp_path):
    secret = "manuscript-private-text"
    author = "private-author"
    url = "https://private.example/secret"
    source = p(
        ins(secret).replace("Synthetic Author 1", author)
        + f'<w:fldSimple w:instr="HYPERLINK &quot;{url}&quot;">'
        + run("link")
        + "</w:fldSimple>"
    )
    target = p(
        run(secret)
        + f'<w:fldSimple w:instr="HYPERLINK &quot;{url}&quot;">'
        + run("link")
        + "</w:fldSimple>"
    )
    a = package(tmp_path / "a.docx", source)
    b = package(tmp_path / "b.docx", target)
    report = tmp_path / "report.json"
    result = color_revisions(a, b, tmp_path / "out.docx", report_path=report)
    assert json.loads(report.read_text()) == result
    assert not any(s in report.read_text() for s in (secret, author, url, "<w:"))


def test_strict_ooxml_is_explicitly_unsupported(tmp_path):
    from zipfile import ZipFile

    from helpers.fixtures import rewrite

    a, b = inputs(tmp_path)
    with ZipFile(a) as z:
        raw = z.read("word/document.xml")
    rewrite(
        a,
        {
            "word/document.xml": raw.replace(
                b"http://schemas.openxmlformats.org/wordprocessingml/2006/main",
                b"http://purl.oclc.org/ooxml/wordprocessingml/main",
            )
        },
    )
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, tmp_path / "out.docx")
    assert error.value.code == "UNSUPPORTED_CONTENT"


def test_same_input_file_is_not_a_document_pair(tmp_path):
    a, _ = inputs(tmp_path)
    with pytest.raises(ColoringError) as error:
        color_revisions(a, a, tmp_path / "out.docx")
    assert error.value.code == "INVALID_DOCUMENT_PAIR"


def test_output_parent_file_is_a_clear_output_error(tmp_path):
    a, b = inputs(tmp_path)
    block = tmp_path / "block"
    block.write_bytes(b"keep")
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, block / "out.docx")
    assert error.value.code == "OUTPUT_ERROR"
    assert block.read_bytes() == b"keep"


def test_output_must_be_docx(tmp_path):
    """Retain the old output-extension safety assertion on the supported API."""
    a, b = inputs(tmp_path)
    before = digest(a), digest(b)
    out = tmp_path / "out.txt"
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, out)
    assert error.value.code == "OUTPUT_ERROR"
    assert not out.exists()
    assert (digest(a), digest(b)) == before


@pytest.mark.parametrize("victim", ["tracked", "accepted", "output"])
@pytest.mark.parametrize("alias", ["same", "relative", "symlink", "hardlink"])
def test_report_aliases_preserve_all_files(tmp_path, monkeypatch, victim, alias):
    """Report aliases must not overwrite either input or an existing output."""
    a, b = inputs(tmp_path)
    out = tmp_path / "out.docx"
    out.write_bytes(b"previous output")
    original = {"tracked": a, "accepted": b, "output": out}[victim]
    report = original
    if alias == "relative":
        monkeypatch.chdir(tmp_path)
        report = Path(original.name)
    elif alias in {"symlink", "hardlink"}:
        report = tmp_path / "alias.json"
        try:
            report.symlink_to(original) if alias == "symlink" else report.hardlink_to(
                original
            )
        except OSError as exc:
            pytest.skip(f"Filesystem aliases unavailable: {type(exc).__name__}")
    before = {f: f.read_bytes() for f in tmp_path.iterdir()}
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, out, report_path=report)
    assert error.value.code == "OUTPUT_ERROR"
    assert {f: f.read_bytes() for f in tmp_path.iterdir()} == before
