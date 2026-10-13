import json
from pathlib import Path

import pytest
from helpers.assertions import assert_integrity, paragraphs
from helpers.fixtures import paragraph

from docx_color_cli import cli
from docx_color_cli.errors import ConversionError, PublicationError


@pytest.mark.parametrize("existing", [True, False])
@pytest.mark.parametrize("failure", ["docx-replace", "report-write", "report-replace"])
def test_publication_failures_preserve_correct_artifacts(
    docx, tmp_path, monkeypatch, existing, failure
):
    source = docx("source.docx", paragraph("new output"))
    target = tmp_path / "out.docx"
    report = tmp_path / "report.json"
    if existing:
        docx("out.docx", paragraph("previous"))
        report.write_text('{"previous": true}', encoding="utf-8")
    before = {f: f.read_bytes() for f in tmp_path.iterdir()}
    replace, write = Path.replace, Path.write_text

    def injected_replace(self, destination):
        if (
            failure == "docx-replace"
            and destination == target
            or failure == "report-replace"
            and destination == report
        ):
            raise PermissionError("injected publication failure")
        return replace(self, destination)

    def injected_write(self, *args, **kwargs):
        if failure == "report-write" and self.suffix == ".json":
            raise PermissionError("injected report staging failure")
        return write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "replace", injected_replace)
    monkeypatch.setattr(Path, "write_text", injected_write)
    with pytest.raises(ConversionError) as caught:
        cli.convert(source, target, _report=report)
    error = caught.value
    assert error.cause_type == "PermissionError"
    assert source.read_bytes() == before[source]
    if existing:
        assert report.read_bytes() == before[report]
    else:
        assert not report.exists()
    if failure == "report-replace":
        assert isinstance(error, PublicationError) and error.output_published
        assert error.destination == str(report)
        assert_integrity(target)
        assert paragraphs(target) == ["new output"]
        before[target] = target.read_bytes()
    elif failure == "docx-replace":
        assert isinstance(error, PublicationError) and not error.output_published
        assert error.destination == str(target)
    assert {f: f.read_bytes() for f in tmp_path.iterdir()} == before


def test_docx_publication_failure_emits_no_success(docx, tmp_path, monkeypatch, capsys):
    source = docx("source.docx", paragraph("keep"))

    def fail(*args, **kwargs):
        raise PermissionError("cannot publish")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(SystemExit) as caught:
        cli.main([str(source), "--report", str(tmp_path / "report.json")])
    assert caught.value.code == 1
    result = capsys.readouterr()
    assert not result.out
    assert "Cannot publish DOCX" in result.err and "Traceback" not in result.err
    assert list(tmp_path.iterdir()) == [source]


def test_report_published_only_after_valid_docx(docx, tmp_path, monkeypatch):
    source = docx("source.docx", paragraph("keep"))
    target, report = tmp_path / "out.docx", tmp_path / "report.json"
    replace = Path.replace

    def observe(self, destination):
        if destination == report:
            assert_integrity(target)
            assert paragraphs(target) == ["keep"]
        return replace(self, destination)

    monkeypatch.setattr(Path, "replace", observe)
    stats = cli.convert(source, target, _report=report)
    assert json.loads(report.read_text()) == stats
