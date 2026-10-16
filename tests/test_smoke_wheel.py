"""Wheel isolation checks must handle filesystem aliases without accepting leaks."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "smoke_helper", Path(__file__).resolve().parents[1] / "scripts/smoke_wheel.py"
)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


@pytest.fixture
def environment_paths(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlinks unavailable: {error}")
    package = Path("venv/lib/site-packages/docx_color_cli/__init__.py")
    (real / package).parent.mkdir(parents=True)
    (real / package).write_text("")
    return real, alias, package


@pytest.mark.parametrize("location_alias", [False, True])
@pytest.mark.parametrize("venv_alias", [False, True])
def test_same_environment_accepts_resolved_and_alias_paths(
    environment_paths, location_alias, venv_alias
):
    real, alias, package = environment_paths
    location = (alias if location_alias else real) / package
    venv = (alias if venv_alias else real) / "venv"
    smoke.assert_installed_location(location, venv)


@pytest.mark.parametrize("directory", ["checkout", "venv-other"])
def test_import_outside_environment_is_rejected(tmp_path, directory):
    location = tmp_path / directory / "docx_color_cli/__init__.py"
    location.parent.mkdir(parents=True)
    location.write_text("")
    venv = tmp_path / "venv"
    venv.mkdir()
    with pytest.raises(AssertionError):
        smoke.assert_installed_location(location, venv)


def test_symlink_inside_environment_cannot_hide_checkout_import(environment_paths):
    real, alias, package = environment_paths
    checkout = real / "checkout"
    checkout.mkdir()
    (checkout / "__init__.py").write_text("")
    leak = real / "venv/leaked-package"
    leak.symlink_to(checkout, target_is_directory=True)
    with pytest.raises(AssertionError):
        smoke.assert_installed_location(
            alias / "venv/leaked-package/__init__.py", alias / "venv"
        )


@pytest.mark.parametrize("missing", [None, "wheel", "sdist"])
def test_ci_selects_only_distributions(tmp_path, monkeypatch, missing):
    import subprocess

    import yaml

    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text()
    )
    step = next(
        s
        for s in workflow["jobs"]["test"]["steps"]
        if s.get("name") == "Build distributions and validate metadata"
    )
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / ".gitignore").write_text("*")
    (dist / "unrelated.txt").write_text("not a distribution")
    if missing != "wheel":
        (dist / "example.whl").write_bytes(b"fixture")
    if missing != "sdist":
        (dist / "example.tar.gz").write_bytes(b"fixture")
    calls = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append((args, kw)))
    if missing:
        with pytest.raises(RuntimeError, match="wheel and one source distribution"):
            exec(step["run"], {})
        assert len(calls) == 1  # Build attempted; metadata success cannot be faked.
    else:
        exec(step["run"], {})
        assert calls == [
            (["uv", "build"], {"check": True}),
            (
                [
                    "uv",
                    "run",
                    "--no-sync",
                    "twine",
                    "check",
                    "--strict",
                    str(Path("dist/example.whl")),
                    str(Path("dist/example.tar.gz")),
                ],
                {"check": True},
            ),
        ]


def test_public_oracle_labels_literal_revisions_and_repeated_cells():
    from xml.etree import ElementTree as ET

    from helpers.corpus import W, cell, delete, ins, p, run, table
    from helpers.public_example import PART, insertion_coordinates

    def root(body):
        return ET.fromstring(f'<w:document xmlns:w="{W[1:-1]}">{body}</w:document>')

    tracked = root(
        table(
            "<w:tr>"
            + cell(p(run("12")))
            + cell(p(delete("10") + ins("12")))
            + "</w:tr>"
        )
    )
    accepted = root(table("<w:tr><w:tblPrEx/>" + cell(p(run("12"))) * 2 + "</w:tr>"))
    assert insertion_coordinates(tracked, accepted) == {(PART, 1, 0), (PART, 1, 1)}
    with pytest.raises(AssertionError):
        insertion_coordinates(tracked, root(p(run("1212"))))
    with pytest.raises(AssertionError):
        insertion_coordinates(
            tracked,
            root(table("<w:tr>" + cell(p(run("12"))) + cell(p(run("13"))) + "</w:tr>")),
        )
