"""Offline controls for version decisions and partial-release recovery."""

import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path
from urllib.error import HTTPError

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "release_helper", ROOT / "scripts/release.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.mark.parametrize(
    "version,previous,tags,published,exists,action",
    [
        ("0.4.0", "0.4.0", ["v0.4.0"], ["0.4.0"], True, "skip"),
        ("0.4.0", "0.4.0", [], [], False, "skip"),
        ("0.4.0", "0.3.0", ["v0.3.0"], ["0.3.0"], True, "publish"),
        ("0.4.0", "0.3.0", ["v0.4.0"], [], False, "skip"),
        ("0.4.0", "0.3.0", [], ["0.4.0"], False, "recover"),
        ("0.4.0", "0.4.0", ["v0.4.0"], ["0.4.0"], False, "recover"),
        ("0.10.0", "0.9.0", ["v0.9.0"], ["0.9.0"], False, "publish"),
        ("1.0rc2", "1.0rc1", ["v1.0rc1"], [], False, "publish"),
        ("1.0", "1.0rc2", ["v1.0rc2"], [], False, "publish"),
        ("1.0.post1", "1.0", [], ["1.0"], False, "publish"),
        ("1.0", "0.9", ["v1.0.0"], [], False, "skip"),
        ("0.4.0", None, [], [], False, "skip"),
        ("0.4.0", "0.3.0", ["unrelated-tag"], [], False, "publish"),
    ],
)
def test_version_decisions(version, previous, tags, published, exists, action):
    assert release.plan(version, previous, tags, published, exists)[0] == action


@pytest.mark.parametrize(
    "version,previous,tags,published",
    [
        ("0.3.0", "0.4.0", ["v0.4.0"], []),
        ("0.9.0", "0.9.0", [], ["0.10.0"]),
        ("1.0rc1", "1.0rc1", ["v1.0"], []),
        ("0.3.0", "0.3.0", ["v0.4.0"], ["0.3.0"]),
    ],
)
def test_downgrade_fails_even_if_version_already_published(
    version, previous, tags, published
):
    with pytest.raises(ValueError, match="lower"):
        release.plan(version, previous, tags, published)


def test_toml_not_text_matching():
    text = """# version = "9.9.9"
[project]
name = "docx-color-cli"
version = "0.4.0" # release
[tool.example]
version = "7.0.0"
"""
    assert release.project_version(text) == "0.4.0"


@pytest.mark.parametrize("version", ["invalid", "0.4+local"])
def test_invalid_pypi_version_rejected(version):
    with pytest.raises(ValueError):
        release.project_version(
            f'[project]\nname="docx-color-cli"\nversion="{version}"'
        )


@pytest.mark.parametrize("code", [401, 403, 429, 500])
def test_http_failure_is_not_permission_to_publish(monkeypatch, code):
    def fail(*args, **kwargs):
        raise HTTPError("https://pypi.org", code, "failure", {}, None)

    monkeypatch.setattr(release, "urlopen", fail)
    with pytest.raises(HTTPError):
        release.get_json("https://pypi.org/pypi/docx-color-cli/json")


def test_pypi_404_is_unpublished(monkeypatch):
    def fail(*args, **kwargs):
        raise HTTPError("https://pypi.org", 404, "not found", {}, None)

    monkeypatch.setattr(release, "urlopen", fail)
    assert release.get_json("https://pypi.org/pypi/docx-color-cli/json") is None


def archive(record):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as output:
        value = json.dumps(record).encode()
        member = tarfile.TarInfo("docx_color_cli-0.4.0/release-provenance.json")
        member.size = len(value)
        output.addfile(member, io.BytesIO(value))
    return buffer.getvalue()


def test_recovery_uses_published_commit():
    commit = "a" * 40
    data = {"repository": release.REPOSITORY, "version": "0.4.0", "commit": commit}
    assert release.source_commit(archive(data), "0.4.0") == commit


@pytest.mark.parametrize(
    "key,value",
    [("repository", "someone/else"), ("version", "0.3.0"), ("commit", "--dangerous")],
)
def test_recovery_rejects_mismatched_provenance(key, value):
    data = {"repository": release.REPOSITORY, "version": "0.4.0", "commit": "a" * 40}
    data[key] = value
    with pytest.raises(ValueError):
        release.source_commit(archive(data), "0.4.0")


def test_recovery_requires_provenance():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz"):
        pass
    with pytest.raises(ValueError, match="manual recovery"):
        release.source_commit(buffer.getvalue(), "0.4.0")


def test_verify_requires_both_distributions_and_exact_hashes(tmp_path):
    payload = {"info": {"name": release.PROJECT, "version": "0.4.0"}, "urls": []}
    for name, kind in [("package.whl", "bdist_wheel"), ("package.tar.gz", "sdist")]:
        (tmp_path / name).write_bytes(name.encode())
        payload["urls"].append(
            {
                "filename": name,
                "packagetype": kind,
                "digests": {"sha256": hashlib.sha256(name.encode()).hexdigest()},
            }
        )
    assert (
        release.validate_files(payload, "0.4.0", tmp_path)["filename"]
        == "package.tar.gz"
    )
    (tmp_path / "package.whl").write_bytes(b"changed")
    with pytest.raises(ValueError, match="digests"):
        release.validate_files(payload, "0.4.0", tmp_path)
    payload["urls"].pop()
    with pytest.raises(ValueError, match="incomplete"):
        release.validate_files(payload, "0.4.0")


def test_existing_tag_and_release_are_never_modified(monkeypatch):
    monkeypatch.setattr(
        release, "git", lambda *args: "v0.4.0" if args[0] == "tag" else "a" * 40
    )
    monkeypatch.setattr(release, "release_info", lambda _: {"id": 42})

    def forbidden(*args, **kwargs):
        pytest.fail("existing release must not be changed")

    monkeypatch.setattr(release.subprocess, "run", forbidden)
    release.complete_github("0.4.0", "a" * 40)


def test_existing_tag_with_wrong_commit_fails(monkeypatch):
    monkeypatch.setattr(
        release, "git", lambda *args: "v0.4.0" if args[0] == "tag" else "b" * 40
    )
    with pytest.raises(ValueError, match="different commit"):
        release.complete_github("0.4.0", "a" * 40)


def test_annotated_tag_precedes_release_and_has_original_commit(monkeypatch, tmp_path):
    monkeypatch.setattr(release, "git", lambda *args: "")
    monkeypatch.setattr(release, "release_info", lambda _: None)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    calls = []
    monkeypatch.setattr(
        release.subprocess, "run", lambda args, **kwargs: calls.append(args)
    )
    release.complete_github("0.4.0", "a" * 40)
    assert calls[0][-6:] == ["tag", "-a", "v0.4.0", "a" * 40, "-m", "Release v0.4.0"]
    assert calls[1] == ["git", "push", "origin", "refs/tags/v0.4.0"]
    assert calls[2][:4] == ["gh", "release", "create", "v0.4.0"]
    assert "--verify-tag" in calls[2] and "--generate-notes" in calls[2]
    assert not any("--force" in call for call in calls)


def test_workflow_security_and_ci_gates():
    # BaseLoader preserves the YAML "on" key instead of interpreting it as a bool.
    ci = yaml.load(
        (ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader
    )
    publish = yaml.load(
        (ROOT / ".github/workflows/publish.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert ci["on"]["push"]["branches"] == ["main"]
    assert ci["on"]["pull_request"]["branches"] == ["main"]
    assert ci["jobs"]["test"]["strategy"]["matrix"]["python"] == [
        "3.11",
        "3.12",
        "3.13",
    ]
    assert list(publish["on"]) == ["push"]
    assert publish["on"]["push"]["branches"] == ["main"]
    assert publish["concurrency"]["cancel-in-progress"] == "false"
    jobs = publish["jobs"]
    assert jobs["validate"]["uses"] == "./.github/workflows/ci.yml"
    assert jobs["build"]["needs"] == ["detect", "validate"]
    assert jobs["publish"]["needs"] == ["detect", "build"]
    assert jobs["publish"]["permissions"] == {"id-token": "write"}
    assert jobs["publish"]["environment"]["name"] == "pypi"
    assert "refs/heads/main" in jobs["publish"]["if"]
    assert jobs["github-release"]["permissions"] == {"contents": "write"}
    publisher = next(
        step
        for step in jobs["publish"]["steps"]
        if step.get("uses", "").startswith("pypa/")
    )
    assert publisher["uses"] == "pypa/gh-action-pypi-publish@release/v1"
    assert "password" not in publisher.get("with", {})
    assert "needs.publish.result" in jobs["github-release"]["if"]


def test_failed_tag_push_prevents_github_release(monkeypatch):
    monkeypatch.setattr(release, "git", lambda *args: "")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[:2] == ["git", "push"]:
            raise release.subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(release.subprocess, "run", run)
    with pytest.raises(release.subprocess.CalledProcessError):
        release.complete_github("0.4.0", "a" * 40)
    assert len(calls) == 2
    assert not any(call[0] == "gh" for call in calls)


def test_published_verification_uses_digest_and_ancestor_guard(monkeypatch):
    commit = "a" * 40
    content = archive(
        {"repository": release.REPOSITORY, "version": "0.4.0", "commit": commit}
    )
    payload = {
        "info": {"name": release.PROJECT, "version": "0.4.0"},
        "urls": [
            {"filename": "a.whl", "packagetype": "bdist_wheel"},
            {
                "filename": "a.tar.gz",
                "packagetype": "sdist",
                "url": "https://files.pythonhosted.org/a.tar.gz",
                "digests": {"sha256": hashlib.sha256(content).hexdigest()},
            },
        ],
    }
    monkeypatch.setattr(release, "get_json", lambda *args: payload)
    monkeypatch.setattr(release, "urlopen", lambda *args, **kwargs: io.BytesIO(content))
    monkeypatch.setattr(
        release,
        "git",
        lambda *args: '[project]\nname="docx-color-cli"\nversion="0.4.0"',
    )
    calls = []
    monkeypatch.setattr(
        release.subprocess, "run", lambda args, **kwargs: calls.append(args)
    )
    assert release.verify("0.4.0") == commit
    assert calls == [["git", "merge-base", "--is-ancestor", commit, "origin/main"]]
    payload["urls"][1]["digests"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest"):
        release.verify("0.4.0")


def test_detect_reads_previous_commit_and_filters_empty_pypi_versions(
    monkeypatch, tmp_path
):
    project = '[project]\nname="docx-color-cli"\nversion="0.4.0"'
    (tmp_path / "pyproject.toml").write_text(project)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        release,
        "git",
        lambda *args: (
            project.replace("0.4.0", "0.3.0") if args[0] == "show" else "v0.3.0"
        ),
    )
    monkeypatch.setattr(
        release, "get_json", lambda *args: {"releases": {"0.3.0": [{}], "0.4.0": []}}
    )
    assert release.detect("a" * 40)["action"] == "publish"
