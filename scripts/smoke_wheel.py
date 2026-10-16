"""Install a wheel in a clean venv and compare installed/development conversion."""

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

from docx_color_cli import color_revisions

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
ROOT = Path(__file__).resolve().parents[1]


def fixture(path, *, accepted=False):
    inserted = "<w:r><w:t>inserted</w:t></w:r>"
    if not accepted:
        inserted = '<w:ins w:id="2">' + inserted + "</w:ins>"
    deleted = (
        ""
        if accepted
        else '<w:del w:id="3"><w:r><w:delText>deleted</w:delText></w:r></w:del>'
    )
    document = f'''<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:m="{M}"><w:body><w:p>
<w:bookmarkStart w:id="1" w:name="target"/>
<w:r><w:rPr><w:color w:val="123456"/></w:rPr><w:t>unchanged</w:t></w:r>
{inserted}
{deleted}
<w:fldSimple w:instr=' ADDIN ZOTERO_ITEM CSL_CITATION {{"citationID":"synthetic"}} '><w:r><w:t>citation</w:t></w:r></w:fldSimple>
<w:hyperlink r:id="link"><w:r><w:t>link</w:t></w:r></w:hyperlink>
<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>
<w:bookmarkEnd w:id="1"/>
</w:p></w:body></w:document>'''
    relationships = "http://schemas.openxmlformats.org/package/2006/relationships"
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr(
            "[Content_Types].xml",
            """<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            f'<Relationships xmlns="{relationships}"><Relationship Id="main" Type="{R}/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            f'<Relationships xmlns="{relationships}"><Relationship Id="link" Type="{R}/hyperlink" Target="https://example.org" TargetMode="External"/></Relationships>',
        )


def check_distributions(wheel, version):
    """Check release contents as well as build metadata; never ship private inputs."""
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert all(
            n.split("/")[0] == "docx_color_cli"
            or n.split("/")[0].endswith(".dist-info")
            for n in names
        )
        metadata_name = next(n for n in names if n.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        assert metadata["Name"] == "docx-color-cli"
        assert metadata["Version"] == version
        assert metadata["Requires-Python"] == ">=3.11"
        assert metadata["License-Expression"] == "MIT"
        assert metadata["Description-Content-Type"].split(";")[0] == "text/markdown"
        assert metadata.get_all("Requires-Dist") and metadata.get_payload().strip()
        assert "docx_color_cli/errors.py" in names
        assert "docx_color_cli/engine.py" in names
        assert "docx_color_cli/math_coloring.py" in names
        runtime = [
            n for n in names if n.startswith("docx_color_cli/") and n.endswith(".py")
        ]
        assert all(n.count("/") == 1 for n in runtime), (
            "Production modules must be flat"
        )
        assert not any("_legacy" in n for n in runtime)
        assert {Path(n).stem for n in runtime} == {
            "__init__",
            "api",
            "cli",
            "accepted",
            "extract",
            "projection",
            "anchors",
            "alignment",
            "math_coloring",
            "coloring",
            "validation",
            "engine",
            "pair",
            "errors",
            "package",
        }
        assert not any(n.endswith(".docx") or "/academic/" in n for n in names)
        assert not any(
            "/artifacts/" in n or "PRIVATE-" in n or n.endswith("_SUMMARY.json")
            for n in names
        )
    sdists = list(wheel.parent.glob("*.tar.gz"))
    assert len(sdists) == 1, "Pass a build directory containing exactly one sdist"
    with tarfile.open(sdists[0]) as archive:
        names = archive.getnames()
        allowed = {
            "src",
            "tests",
            "scripts",
            ".github",
            ".gitignore",
            "README.md",
            "README.zh-CN.md",
            "RELEASE.md",
            "RELEASE_NOTES_1.1.0.md",
            "LICENSE",
            "pyproject.toml",
            "uv.lock",
            "PKG-INFO",
            "release-provenance.json",
        }
        assert all(len(Path(n).parts) < 2 or Path(n).parts[1] in allowed for n in names)
        runtime = [
            n for n in names if "/src/docx_color_cli/" in n and n.endswith(".py")
        ]
        assert all(
            n.split("/src/docx_color_cli/", 1)[1].count("/") == 0 for n in runtime
        )
        assert not any("_legacy" in n for n in runtime)
        assert not any(n.endswith(".docx") or "/academic/" in n for n in names)
        assert not any(
            "/artifacts/" in n or "PRIVATE-" in n or n.endswith("_SUMMARY.json")
            for n in names
        )
        assert any(n.endswith("/README.zh-CN.md") for n in names)
        for required in (
            "RELEASE.md",
            "RELEASE_NOTES_1.1.0.md",
            "scripts/release.py",
            "tests/test_release.py",
            ".github/workflows/publish.yml",
        ):
            assert any(n.endswith("/" + required) for n in names), required


def assert_installed_location(location, venv):
    """Reject imports outside the independently installed wheel environment."""
    # macOS may return /private/var for an environment created through /var.
    # Resolve both paths, including links that could escape the environment.
    assert location.resolve(strict=True).is_relative_to(venv.resolve(strict=True)), (
        location
    )


def smoke(wheel, *, tracked_reference=None, accepted_reference=None):
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    check_distributions(wheel, version)
    with tempfile.TemporaryDirectory(prefix="docx-wheel-") as directory:
        work = Path(directory)
        venv = work / "venv"
        subprocess.run(
            ["uv", "venv", "--python", sys.executable, str(venv)], check=True
        )
        bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / ("python.exe" if os.name == "nt" else "python")
        command = bin_dir / ("docx-color.exe" if os.name == "nt" else "docx-color")
        alias = bin_dir / (
            "docx-color-cli.exe" if os.name == "nt" else "docx-color-cli"
        )
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), str(wheel.resolve())],
            check=True,
        )
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"PYTHONPATH", "VIRTUAL_ENV"}
        }

        def run(*args):
            return subprocess.check_output(
                [str(a) for a in args], cwd=work, env=env, text=True
            )

        location = Path(
            run(
                python,
                "-I",
                "-c",
                "import docx_color_cli; print(docx_color_cli.__file__)",
            ).strip()
        )
        assert_installed_location(location, venv)
        assert "ACCEPTED" in run(command, "--help") and "--check" not in run(
            command, "--help"
        )
        assert run(command, "--version").strip().endswith(" " + version)
        assert run(alias, "--version").strip().endswith(" " + version)
        assert "ACCEPTED" in run(alias, "--help")
        source, accepted, expected, actual = (
            work / name
            for name in ("input.docx", "accepted.docx", "expected.docx", "actual.docx")
        )
        fixture(source)
        fixture(accepted, accepted=True)
        before = (source.read_bytes(), accepted.read_bytes())
        color_revisions(source, accepted, expected)
        report = work / "result.json"
        run(command, source, accepted, actual, "--report", report)
        assert json.loads(report.read_text())["overall_status"] == "SUCCESS"
        run(
            python,
            "-I",
            "-c",
            "import sys, docx_color_cli; assert not any(n in sys.modules for n in ['pytest', 'ruff', 'main', 'docx_color_cli._legacy'])",
        )
        with ZipFile(expected) as left, ZipFile(actual) as right:
            assert left.namelist() == right.namelist()
            assert all(left.read(name) == right.read(name) for name in left.namelist())
            xml = right.read("word/document.xml")
            assert b"deleted" not in xml
            assert all(
                value in xml
                for value in (
                    b"FF0000",
                    b"123456",
                    b"inserted",
                    b"ZOTERO_ITEM",
                    b"hyperlink",
                    b"bookmarkStart",
                    b"oMath",
                )
            )
        assert (source.read_bytes(), accepted.read_bytes()) == before
        if tracked_reference is not None and accepted_reference is not None:
            tracked_reference = tracked_reference.resolve()
            accepted_reference = accepted_reference.resolve()
            hashes = (tracked_reference.read_bytes(), accepted_reference.read_bytes())
            local_output, installed_output = (
                work / "local-example.docx",
                work / "installed-example.docx",
            )
            local = color_revisions(tracked_reference, accepted_reference, local_output)
            example_report = work / "example-report.json"
            run(
                command,
                tracked_reference,
                accepted_reference,
                installed_output,
                "--report",
                example_report,
            )
            assert local_output.read_bytes() == installed_output.read_bytes()
            installed = json.loads(example_report.read_text())
            for key in (
                "extraction",
                "mapping",
                "completeness",
                "coloring",
                "integrity",
            ):
                assert local[key] == installed[key]
            assert (
                tracked_reference.read_bytes(),
                accepted_reference.read_bytes(),
            ) == hashes
            # Test-only stdlib oracle; never imported by the installed package.
            sys.path.insert(0, str(ROOT / "tests"))
            from helpers.public_example import verify_public_example

            verify_public_example(
                tracked_reference, accepted_reference, installed_output, installed
            )
            print(
                "Public example smoke PASS: publication=SUCCESS coloring=SUCCESS "
                "overall=SUCCESS colored=3075 unresolved=0 table_characters=34 "
                "unauthorized=0 fidelity=PASS; inputs unchanged; wheel parity=PASS"
            )
        print(f"Clean wheel smoke passed: {version}; installed import: {location}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--tracked", type=Path)
    parser.add_argument("--accepted", type=Path)
    args = parser.parse_args()
    if bool(args.tracked) != bool(args.accepted):
        parser.error("Supply both --tracked and --accepted, or neither")
    wheel = args.wheel
    if wheel.is_dir():
        wheels = list(wheel.glob("*.whl"))
        if len(wheels) != 1:
            parser.error("Build directory must contain exactly one wheel")
        wheel = wheels[0]
    smoke(wheel, tracked_reference=args.tracked, accepted_reference=args.accepted)
