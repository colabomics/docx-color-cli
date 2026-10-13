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
