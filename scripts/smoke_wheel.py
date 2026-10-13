"""Install a wheel in a clean venv and compare installed/development conversion."""

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

from docx_color_cli.cli import convert

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def fixture(path):
    document = f'''<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:m="{M}"><w:body><w:p>
<w:bookmarkStart w:id="1" w:name="target"/>
<w:r><w:t>unchanged</w:t></w:r>
<w:ins w:id="2"><w:r><w:t>inserted</w:t></w:r></w:ins>
<w:del w:id="3"><w:r><w:delText>deleted</w:delText></w:r></w:del>
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
        metadata_name = next(n for n in names if n.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        assert metadata["Name"] == "docx-color-cli"
        assert metadata["Version"] == version
        assert metadata["Requires-Python"] == ">=3.11"
        assert metadata["License-Expression"] == "MIT"
        assert metadata["Description-Content-Type"].split(";")[0] == "text/markdown"
        assert metadata.get_all("Requires-Dist") and metadata.get_payload().strip()
        assert "docx_color_cli/errors.py" in names
        assert not any(n.endswith(".docx") or "/academic/" in n for n in names)
    sdists = list(wheel.parent.glob("*.tar.gz"))
    assert len(sdists) == 1, "Pass a build directory containing exactly one sdist"
    with tarfile.open(sdists[0]) as archive:
        names = archive.getnames()
        assert not any(n.endswith(".docx") or "/academic/" in n for n in names)
        for required in (
            "RELEASE.md",
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


def smoke(wheel):
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
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
        assert "--check" in run(command, "--help")
        assert run(command, "--version").strip().endswith(" " + version)
        assert run(alias, "--version").strip().endswith(" " + version)
        source, expected, actual = (
            work / name for name in ("input.docx", "expected.docx", "actual.docx")
        )
        fixture(source)
        before = source.read_bytes()
        convert(source, expected)
        run(command, source, actual)
        run(command, source, "--check")
        with ZipFile(expected) as left, ZipFile(actual) as right:
            assert left.namelist() == right.namelist()
            assert all(left.read(name) == right.read(name) for name in left.namelist())
            xml = right.read("word/document.xml")
            assert b"deleted" not in xml
            assert all(
                value in xml
                for value in (
                    b"FF0000",
                    b"000000",
                    b"inserted",
                    b"ZOTERO_ITEM",
                    b"hyperlink",
                    b"bookmarkStart",
                    b"oMath",
                )
            )
        assert source.read_bytes() == before
        print(f"Clean wheel smoke passed: {version}; installed import: {location}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    smoke(parser.parse_args().wheel)
