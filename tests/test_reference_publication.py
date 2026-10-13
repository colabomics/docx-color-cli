import pytest
from helpers.assertions import assert_integrity
from helpers.fixtures import insert, p, run

from docx_color_cli.cli import convert, main


def test_reference_checked_before_publication(docx, tmp_path):
    source = docx("in.docx", p(insert("new")))
    reference = docx("reference.docx", p(run("wrong")))
    target = docx("out.docx", p(run("old output")))
    before = {f: f.read_bytes() for f in (source, reference, target)}
    with pytest.raises(ValueError, match="Content validation failed"):
        convert(source, target, reference=reference)
    assert all(f.read_bytes() == data for f, data in before.items())
    assert set(tmp_path.iterdir()) == set(before)


def test_reference_cli_success(docx, tmp_path, capsys):
    source = docx("in.docx", p(insert("new")))
    reference = docx("reference.docx", p(run("new")))
    target = tmp_path / "out.docx"
    main([str(source), str(target), "--reference", str(reference)])
    assert "Saved:" in capsys.readouterr().out
    assert_integrity(target)


@pytest.mark.parametrize("collision", ["output", "report"])
def test_reference_must_not_be_overwritten(docx, tmp_path, collision):
    source = docx("in.docx", p(run("new")))
    reference = docx("reference.docx", p(run("new")))
    before = reference.read_bytes()
    kwargs = {"reference": reference}
    if collision == "report":
        kwargs["_report"] = reference
    with pytest.raises(ValueError, match="paths must differ"):
        convert(
            source,
            reference if collision == "output" else tmp_path / "out.docx",
            **kwargs,
        )
    assert reference.read_bytes() == before


def test_cli_reference_failure_preserves_report_and_output(docx, tmp_path, capsys):
    source = docx("in.docx", p(insert("new")))
    reference = docx("ref.docx", p(run("different")))
    output = docx("out.docx", p(run("previous")))
    report = tmp_path / "report.json"
    report.write_text('{"previous": true}', encoding="utf-8")
    before = {f: f.read_bytes() for f in (source, reference, output, report)}
    with pytest.raises(SystemExit) as error:
        main(
            [
                str(source),
                str(output),
                "--reference",
                str(reference),
                "--report",
                str(report),
            ]
        )
    assert error.value.code == 1
    stderr = capsys.readouterr().err
    assert "Content validation failed" in stderr
    assert "Traceback" not in stderr
    assert all(f.read_bytes() == data for f, data in before.items())
    assert set(tmp_path.iterdir()) == set(before)
