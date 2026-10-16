"""Real local filesystem behavior plus deterministic publication race faults."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from helpers.corpus import ins, p, package, run
from helpers.fidelity import compare, digest

from docx_color_cli import ColoringError, color_revisions, engine


def pair(folder):
    folder.mkdir(parents=True, exist_ok=True)
    return package(folder / "tracked.docx", p(ins("new"))), package(
        folder / "accepted.docx", p(run("new"))
    )


@pytest.mark.parametrize(
    "name,relative",
    [("ascii", True), ("with spaces", False), ("结果 文件", True), ("café-🚀", False)],
)
def test_paths_and_read_only_inputs(tmp_path, monkeypatch, name, relative):
    a, b = pair(tmp_path / name)
    before = digest(a), digest(b)
    modes = a.stat().st_mode, b.stat().st_mode
    a.chmod(0o444)
    b.chmod(0o444)
    out = a.parent / "new directory" / "结果.docx"
    try:
        if relative:
            monkeypatch.chdir(tmp_path)
            paths = [x.relative_to(tmp_path) for x in (a, b, out)]
        else:
            paths = [a, b, out]
        assert color_revisions(*paths)["overall_status"] == "SUCCESS"
        assert (
            compare(b, out, allowed={("word/document.xml", 0, i) for i in range(3)})[0][
                "overall"
            ]
            == "PASS"
        )
        assert (digest(a), digest(b)) == before
    finally:
        a.chmod(modes[0])
        b.chmod(modes[1])


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX mode-bit directory denial; Windows sharing denial tested separately",
)
def test_real_read_only_destination(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("Root bypasses POSIX mode-bit write denial")
    a, b = pair(tmp_path / "inputs")
    dest = tmp_path / "readonly"
    dest.mkdir()
    out = dest / "out.docx"
    out.write_bytes(b"previous")
    before = digest(a), digest(b)
    dest.chmod(0o555)
    try:
        with pytest.raises(ColoringError) as error:
            color_revisions(a, b, out)
        assert error.value.code == "OUTPUT_ERROR"
        assert out.read_bytes() == b"previous"
        assert list(dest.iterdir()) == [out]
        assert (digest(a), digest(b)) == before
    finally:
        dest.chmod(0o755)


def test_destination_open_in_another_process(tmp_path):
    a, b = pair(tmp_path)
    out = tmp_path / "out.docx"
    out.write_bytes(b"previous")
    hashes = digest(a), digest(b)
    code = "import sys; f=open(sys.argv[1],'rb'); print('ready',flush=True); input(); f.close()"
    child = subprocess.Popen(
        [sys.executable, "-c", code, str(out)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout.readline().strip() == "ready"
        if os.name == "nt":
            with pytest.raises(ColoringError) as error:
                color_revisions(a, b, out)
            assert error.value.code == "OUTPUT_ERROR"
            assert out.read_bytes() == b"previous"
        else:
            assert color_revisions(a, b, out)["publication_status"] == "SUCCESS"
            assert compare(b, out)[0]["content_fidelity"] == "PASS"
        assert (digest(a), digest(b)) == hashes
        assert {f.name for f in tmp_path.iterdir()} == {
            "tracked.docx",
            "accepted.docx",
            "out.docx",
        }
    finally:
        child.communicate("\n", timeout=10)
        assert child.returncode == 0


@pytest.mark.parametrize(
    "change", ["input", "destination-directory", "destination-input-alias"]
)
def test_changes_before_publication_abort(tmp_path, monkeypatch, change):
    a, b = pair(tmp_path)
    out = tmp_path / "out.docx"
    out.write_bytes(b"previous")
    accepted_hash = digest(b)
    real = engine.validate_output

    def changed(*args):
        result = real(*args)
        if change == "input":
            a.write_bytes(b"external writer changed input")
        else:
            out.unlink()
            if change == "destination-directory":
                out.mkdir()
            else:
                try:
                    out.hardlink_to(a)
                except OSError as exc:
                    pytest.skip(f"Hardlinks unavailable: {type(exc).__name__}")
        return result

    monkeypatch.setattr(engine, "validate_output", changed)
    with pytest.raises(ColoringError):
        color_revisions(a, b, out)
    assert digest(b) == accepted_hash
    if change == "input":
        assert a.read_bytes() == b"external writer changed input"
        assert out.read_bytes() == b"previous"
    elif change == "destination-directory":
        assert out.is_dir()
    else:
        assert out.samefile(a)
    assert {f.name for f in tmp_path.iterdir()} == {
        "tracked.docx",
        "accepted.docx",
        "out.docx",
    }


def test_cleanup_failure_cannot_hide_published_docx(tmp_path, monkeypatch):
    a, b = pair(tmp_path)
    hashes = digest(a), digest(b)
    out, report = tmp_path / "out.docx", tmp_path / "report.json"
    replace, unlink = Path.replace, Path.unlink

    def deny_report(self, target):
        if target == report:
            raise PermissionError("synthetic sharing violation")
        return replace(self, target)

    def deny_cleanup(self, *args, **kwargs):
        if self.suffix == ".json":
            raise PermissionError("synthetic cleanup denial")
        return unlink(self, *args, **kwargs)

    with monkeypatch.context() as m:
        m.setattr(Path, "replace", deny_report)
        m.setattr(Path, "unlink", deny_cleanup)
        result = color_revisions(a, b, out, report_path=report)
    assert result["publication_status"] == "SUCCESS"
    assert result["overall_status"] == "PARTIAL"
    assert {w["code"] for w in result["publication"]["warnings"]} == {
        "REPORT_PUBLISH_FAILED",
        "TEMP_CLEANUP_FAILED",
    }
    assert compare(b, out)[0]["content_fidelity"] == "PASS"
    assert (digest(a), digest(b)) == hashes
    residual = list(tmp_path.glob("*.json"))
    assert len(residual) == 1 and residual[0] != report
    residual[0].unlink()


@pytest.mark.parametrize(
    "output_name,report_name",
    [
        ("Output.docx", "output.docx"),
        ("é.docx", "e\u0301.docx"),
        ("New/Output.docx", "new/output.docx"),
    ],
)
@pytest.mark.parametrize("existed", [False, True])
def test_absent_or_existing_destination_spelling_aliases(
    tmp_path, monkeypatch, output_name, report_name, existed
):
    """Two absent spellings can alias on APFS/NTFS; never let JSON replace DOCX."""
    a, b = pair(tmp_path)
    out, report = tmp_path / output_name, tmp_path / report_name
    if existed:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"previous output")
    before = {
        str(f.relative_to(tmp_path)): f.read_bytes()
        for f in tmp_path.rglob("*")
        if f.is_file()
    }
    monkeypatch.setattr(
        engine,
        "Package",
        lambda *a, **k: pytest.fail("Refuse spelling aliases before reading documents"),
    )
    with pytest.raises(ColoringError) as error:
        color_revisions(a, b, out, report_path=report)
    assert error.value.code == "OUTPUT_ERROR"
    assert {
        str(f.relative_to(tmp_path)): f.read_bytes()
        for f in tmp_path.rglob("*")
        if f.is_file()
    } == before


def test_unicode_output_in_ascii_pipe_reports_published_success(tmp_path):
    a, b = pair(tmp_path)
    out = tmp_path / "结果.docx"
    before = digest(a), digest(b)
    result = subprocess.run(
        [sys.executable, "-m", "docx_color_cli.cli", str(a), str(b), str(out)],
        env={**os.environ, "PYTHONIOENCODING": "ascii"},
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert b"Status:\n  SUCCESS" in result.stdout.replace(b"\r\n", b"\n")
    assert b"Traceback" not in result.stderr
    assert rb"\u7ed3\u679c.docx" in result.stdout
    assert (
        compare(b, out, allowed={("word/document.xml", 0, i) for i in range(3)})[0][
            "overall"
        ]
        == "PASS"
    )
    assert (digest(a), digest(b)) == before
