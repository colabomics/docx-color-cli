"""Publication uses bounded equivalence; the independent oracle stays strict."""

import json
from pathlib import Path

import pytest
from helpers.content import validate_docx as independent_validate
from helpers.fixtures import insert, p, run, story

from docx_color_cli.cli import check, convert, convert_output, main
from docx_color_cli.validation import validate_docx


@pytest.fixture
def pair(docx):
    def body(ident, content):
        return p(
            f'<w:bookmarkStart w:id="{ident}" w:name="target"/>'
            + content
            + f'<w:bookmarkEnd w:id="{ident}"/>'
        )

    source = docx(
        "tracked.docx",
        body(42, insert("new")),
        {"word/settings.xml": story("settings", '<w:zoom w:percent="179"/>')},
    )
    reference = docx(
        "reference.docx",
        body(0, run("new")),
        {"word/settings.xml": story("settings", '<w:zoom w:percent="118"/>')},
    )
    return source, reference


@pytest.mark.parametrize("api", [convert, convert_output, check])
def test_semantic_default_and_explicit_strict(pair, tmp_path, api):
    source, reference = pair
    args = (source,) if api is check else (source, tmp_path / "out.docx")
    result = api(*args, reference=reference)
    comparison = result["reference_validation"]
    assert comparison["mode"] == "semantic"
    assert comparison["ok"]
    assert any("bookmark identity mapping" in w for w in comparison["warnings"])
    before = {f: f.read_bytes() for f in tmp_path.iterdir()}
    with pytest.raises(ValueError, match="Content validation failed"):
        api(*args, reference=reference, reference_mode="strict")
    assert {f: f.read_bytes() for f in tmp_path.iterdir()} == before
    if api is not check:
        assert not validate_docx(args[1], reference).ok
        assert independent_validate(args[1], reference, semantic=True).ok


def test_cli_reports_equivalences(pair, tmp_path, capsys):
    source, reference = pair
    target, report = tmp_path / "out.docx", tmp_path / "report.json"
    main(
        [
            str(source),
            str(target),
            "--reference",
            str(reference),
            "--report",
            str(report),
        ]
    )
    captured = capsys.readouterr()
    assert "bookmark identity mapping" in captured.err
    assert "view zoom" in captured.err
    assert json.loads(report.read_text())["reference_validation"]["mode"] == "semantic"
    before = {f: f.read_bytes() for f in tmp_path.iterdir()}
    with pytest.raises(SystemExit) as exc:
        main(
            [
                str(source),
                str(target),
                "--reference",
                str(reference),
                "--reference-mode",
                "strict",
                "--report",
                str(report),
            ]
        )
    assert exc.value.code == 1
    assert {f: f.read_bytes() for f in tmp_path.iterdir()} == before
    main([str(source), "--check", "--reference", str(reference)])
    assert "view zoom" in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["semantic", "strict"])
def test_reference_mode_requires_reference(docx, mode):
    source = docx("in.docx", p(run("x")))
    with pytest.raises(SystemExit) as exc:
        main([str(source), "--reference-mode", mode])
    assert exc.value.code == 2


def test_invalid_api_mode_does_not_publish(pair, tmp_path):
    source, reference = pair
    with pytest.raises(ValueError, match="reference_mode"):
        convert(
            source, tmp_path / "out.docx", reference=reference, reference_mode="typo"
        )
    assert not (tmp_path / "out.docx").exists()


@pytest.mark.parametrize("content", ["wrong", "new "])
def test_semantic_default_rejects_content_changes(pair, docx, tmp_path, content):
    source, _ = pair
    reference = docx("wrong.docx", p(run(content)))
    output = docx("out.docx", p(run("previous")))
    before = {f: f.read_bytes() for f in tmp_path.iterdir()}
    with pytest.raises(ValueError, match="Content validation failed"):
        convert(source, output, reference=reference)
    assert {f: f.read_bytes() for f in tmp_path.iterdir()} == before


def test_local_word_pair(tmp_path):
    # User supplied: accepted and saved in Word. Word version is not provided.
    # Private documents stay ignored; this test never copies them into fixtures.
    examples = Path(__file__).resolve().parents[1] / "examples"
    source = examples / "complex_tracked.docx"
    reference = examples / "complex_reference.docx"
    if not source.is_file() or not reference.is_file():
        pytest.skip("Local examples Word tracked/reference pair is not present")
    before = source.read_bytes(), reference.read_bytes()
    output = tmp_path / "out.docx"
    result = convert(source, output, reference=reference)
    assert result["reference_validation"]["ok"]
    assert independent_validate(output, reference, semantic=True).ok
    assert not validate_docx(output, reference).ok
    assert (source.read_bytes(), reference.read_bytes()) == before
