"""Publication behavior, including observable auxiliary-output failures."""

import json
from pathlib import Path

import pytest
from helpers.corpus import ins, p, package, run
from helpers.fidelity import compare, digest

from docx_color_cli.cli import main
from docx_color_cli.engine import convert


@pytest.fixture
def receipts(monkeypatch):
    from docx_color_cli import cli

    rows = []
    original = cli.color_revisions

    def recorded(*args, **kwargs):
        result = original(*args, **kwargs)
        rows.append(result)
        return result

    monkeypatch.setattr(cli, "color_revisions", recorded)
    return rows


def inputs(tmp_path):
    return (
        package(tmp_path / "tracked.docx", p(ins("new"))),
        package(tmp_path / "accepted.docx", p(run("new"))),
    )


@pytest.mark.parametrize("output_exists", [False, True])
@pytest.mark.parametrize("report_exists", [False, True])
def test_both_files_staged_and_verified_before_commit(
    tmp_path, monkeypatch, output_exists, report_exists
):
    from docx_color_cli import engine as sut

    tracked, accepted = inputs(tmp_path)
    output, report = tmp_path / "out.docx", tmp_path / "report.json"
    if output_exists:
        output.write_bytes(b"previous docx")
    if report_exists:
        report.write_bytes(b"previous report")
    before = [digest(tracked), digest(accepted)]
    events = []
    validate, write, read, replace = (
        sut.validate_output,
        Path.write_text,
        Path.read_text,
        Path.replace,
    )

    def checked(*args):
        result = validate(*args)
        events.append("docx-validated")
        return result

    def staged(self, *args, **kwargs):
        result = write(self, *args, **kwargs)
        if self.suffix == ".json":
            events.append("json-staged")
        return result

    def verified(self, *args, **kwargs):
        result = read(self, *args, **kwargs)
        if self.suffix == ".json":
            events.append("json-readback")
        return result

    def committed(self, target):
        assert self.parent == Path(target).parent
        assert events[:3] == ["docx-validated", "json-staged", "json-readback"]
        if Path(target) == output:
            assert (
                output.read_bytes() == b"previous docx"
                if output_exists
                else not output.exists()
            )
            events.append("docx-committed")
        else:
            assert events[-1] == "docx-committed"
            assert json.loads(read(self))["publication"]["output_sha256"] == digest(
                output
            )
            events.append("json-committed")
        return replace(self, target)

    monkeypatch.setattr(sut, "validate_output", checked)
    monkeypatch.setattr(Path, "write_text", staged)
    monkeypatch.setattr(Path, "read_text", verified)
    monkeypatch.setattr(Path, "replace", committed)
    result = convert(tracked, accepted, output, report_path=report)
    assert events == [
        "docx-validated",
        "json-staged",
        "json-readback",
        "docx-committed",
        "json-committed",
    ]
    assert json.loads(read(report)) == result
    assert result["publication"] == {
        "status": "SUCCESS",
        "docx_published": True,
        "report_status": "PUBLISHED",
        "report_published": True,
        "output_sha256": digest(output),
        "warnings": [],
    }
    assert [digest(tracked), digest(accepted)] == before
    assert {x.name for x in tmp_path.iterdir()} == {
        "tracked.docx",
        "accepted.docx",
        "out.docx",
        "report.json",
    }


@pytest.mark.parametrize("output_exists", [False, True])
@pytest.mark.parametrize("report_exists", [False, True])
def test_cli_report_commit_failure_is_explicit_docx_success(
    tmp_path, monkeypatch, capsys, output_exists, report_exists, receipts
):
    tracked, accepted = inputs(tmp_path)
    output, report = tmp_path / "out.docx", tmp_path / "report.json"
    if output_exists:
        output.write_bytes(b"previous docx")
    if report_exists:
        report.write_bytes(b"previous report")
    before = [digest(tracked), digest(accepted)]
    replace = Path.replace

    def fail_report(self, target):
        if Path(target) == report:
            raise PermissionError("SENSITIVE_ERROR_PAYLOAD")
        return replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_report)
    assert (
        main([str(tracked), str(accepted), str(output), "--report", str(report)]) == 0
    )
    captured = capsys.readouterr()
    assert "PARTIAL" in captured.out
    receipt = receipts[0]["publication"]
    assert receipt["docx_published"] and not receipt["report_published"]
    assert receipt["status"] == "DOCX_PUBLISHED_REPORT_FAILED"
    assert receipt["output_sha256"] == digest(output)
    assert receipt["warnings"][0]["code"] == "REPORT_PUBLISH_FAILED"
    assert "DOCX was published" in captured.err
    assert "may be stale" in captured.err
    assert "SENSITIVE_ERROR_PAYLOAD" not in captured.out + captured.err
    assert (
        report.read_bytes() == b"previous report"
        if report_exists
        else not report.exists()
    )
    assert (
        compare(
            accepted, output, allowed={("word/document.xml", 0, i) for i in range(3)}
        )[0]["overall"]
        == "PASS"
    )
    assert [digest(tracked), digest(accepted)] == before
    assert {x.name for x in tmp_path.iterdir()} == {
        "tracked.docx",
        "accepted.docx",
        "out.docx",
    } | ({"report.json"} if report_exists else set())


@pytest.mark.parametrize("existed", [False, True])
def test_cli_report_staging_failure_keeps_original_targets(
    tmp_path, monkeypatch, capsys, existed
):
    tracked, accepted = inputs(tmp_path)
    output, report = tmp_path / "out.docx", tmp_path / "report.json"
    if existed:
        output.write_bytes(b"previous docx")
        report.write_bytes(b"previous report")
    before = [digest(tracked), digest(accepted)]
    write = Path.write_text

    def fail_report(self, *args, **kwargs):
        if self.suffix == ".json":
            raise OSError("report staging failed")
        return write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_report)
    assert (
        main([str(tracked), str(accepted), str(output), "--report", str(report)]) == 1
    )
    captured = capsys.readouterr()
    assert not captured.out and "DOCX not published" in captured.err
    assert output.read_bytes() == b"previous docx" if existed else not output.exists()
    assert report.read_bytes() == b"previous report" if existed else not report.exists()
    assert [digest(tracked), digest(accepted)] == before
    assert {x.name for x in tmp_path.iterdir()} == {"tracked.docx", "accepted.docx"} | (
        {"out.docx", "report.json"} if existed else set()
    )


@pytest.mark.parametrize("existed", [False, True])
def test_report_is_optional(tmp_path, existed):
    tracked, accepted = inputs(tmp_path)
    output = tmp_path / "out.docx"
    if existed:
        output.write_bytes(b"previous docx")
    result = convert(tracked, accepted, output)
    assert result["publication"]["status"] == "SUCCESS"
    assert result["publication"]["report_status"] == "NOT_REQUESTED"
    assert result["publication"]["output_sha256"] == digest(output)
    assert {x.name for x in tmp_path.iterdir()} == {
        "tracked.docx",
        "accepted.docx",
        "out.docx",
    }


@pytest.mark.parametrize("target", ["output", "report"])
def test_directory_destination_refused_before_publication(tmp_path, target):
    tracked, accepted = inputs(tmp_path)
    output, report = tmp_path / "out.docx", tmp_path / "report.json"
    (output if target == "output" else report).mkdir()
    names = {x.name for x in tmp_path.iterdir()}
    with pytest.raises(ValueError, match="regular files"):
        convert(tracked, accepted, output, report_path=report)
    assert {x.name for x in tmp_path.iterdir()} == names


def test_nested_output_file_paths_are_rejected_without_creating_them(tmp_path):
    tracked, accepted = inputs(tmp_path)
    output = tmp_path / "out.docx"
    with pytest.raises(ValueError, match="distinct regular files"):
        convert(tracked, accepted, output, report_path=output / "report.json")
    assert not output.exists()


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
@pytest.mark.parametrize("victim", ["tracked", "accepted", "output"])
def test_report_alias_cannot_overwrite_input_or_docx(tmp_path, alias, victim):
    import os

    tracked, accepted = inputs(tmp_path)
    output = tmp_path / "out.docx"
    output.write_bytes(b"previous docx")
    source = {"tracked": tracked, "accepted": accepted, "output": output}[victim]
    report = source if alias == "same" else tmp_path / "report.json"
    if alias == "symlink":
        report.symlink_to(source)
    elif alias == "hardlink":
        os.link(source, report)
    before = [digest(x) for x in (tracked, accepted, output)]
    with pytest.raises(ValueError, match="distinct regular files"):
        convert(tracked, accepted, output, report_path=report)
    assert before == [digest(x) for x in (tracked, accepted, output)]


def test_cleanup_denial_cannot_hide_committed_docx(
    tmp_path, monkeypatch, capsys, receipts
):
    tracked, accepted = inputs(tmp_path)
    output, report = tmp_path / "out.docx", tmp_path / "report.json"
    before = [digest(tracked), digest(accepted)]
    replace, unlink = Path.replace, Path.unlink

    def fail_report(self, target):
        if Path(target) == report:
            raise PermissionError("injected rename denial")
        return replace(self, target)

    def deny_cleanup(self, *args, **kwargs):
        if self.suffix == ".json" and self != report:
            raise PermissionError("injected cleanup denial")
        return unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "replace", fail_report)
    monkeypatch.setattr(Path, "unlink", deny_cleanup)
    assert (
        main([str(tracked), str(accepted), str(output), "--report", str(report)]) == 0
    )
    captured = capsys.readouterr()
    assert "PARTIAL" in captured.out
    receipt = receipts[0]["publication"]
    assert receipt["docx_published"]
    assert [w["code"] for w in receipt["warnings"]] == [
        "REPORT_PUBLISH_FAILED",
        "TEMP_CLEANUP_FAILED",
    ]
    residual = Path(receipt["warnings"][1]["temporary_file"])
    assert residual.is_file() and "TEMP_CLEANUP_FAILED" in captured.err
    assert receipt["output_sha256"] == digest(output)
    assert [digest(tracked), digest(accepted)] == before
    unlink(residual)  # Remove this test's synthetic file after simulated denial.


def test_staged_docx_cannot_change_between_validation_and_publication(
    tmp_path, monkeypatch
):
    tracked, accepted = inputs(tmp_path)
    output, report = tmp_path / "out.docx", tmp_path / "report.json"
    output.write_bytes(b"previous docx")
    report.write_bytes(b"previous report")
    before = [digest(tracked), digest(accepted)]
    write = Path.write_text

    def corrupt_staged_docx(self, *args, **kwargs):
        result = write(self, *args, **kwargs)
        if self.suffix == ".json" and self != report:
            pending = [
                f
                for f in tmp_path.glob("*.docx")
                if f not in {tracked, accepted, output}
            ]
            assert len(pending) == 1
            pending[0].write_bytes(b"injected staged artifact corruption")
        return result

    monkeypatch.setattr(Path, "write_text", corrupt_staged_docx)
    with pytest.raises(ValueError, match="Cannot stage or publish"):
        convert(tracked, accepted, output, report_path=report)
    assert output.read_bytes() == b"previous docx"
    assert report.read_bytes() == b"previous report"
    assert [digest(tracked), digest(accepted)] == before
    assert {f.name for f in tmp_path.iterdir()} == {
        "tracked.docx",
        "accepted.docx",
        "out.docx",
        "report.json",
    }
