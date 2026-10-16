"""Release planning, PyPI verification and idempotent GitHub completion.

Only the `github` command mutates remote state. Tests use pure planning functions
and mocked HTTP/Git operations; no release is performed by the test suite.
"""

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import time
import tomllib
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

PROJECT = "docx-color-cli"
REPOSITORY = "colabomics/docx-color-cli"
PROVENANCE = "release-provenance.json"


def project_version(text):
    project = tomllib.loads(text)["project"]
    if project["name"] != PROJECT:
        raise ValueError(f"Expected project {PROJECT}")
    version = Version(project["version"])
    if version.local is not None:
        raise ValueError("PyPI releases cannot use local version identifiers")
    return str(version)


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def tag_versions(tags):
    versions = set()
    for tag in tags:
        if tag.startswith("v"):
            try:
                versions.add(Version(tag[1:]))
            except InvalidVersion:
                continue
    return versions


def plan(version, previous, tags, published, release_exists=False):
    """Return publish/recover/skip; refuse downgrades before any remote mutation."""
    current = Version(version)
    tagged = tag_versions(tags)
    released = {Version(v) for v in published}
    known = tagged | released
    if previous is not None:
        known.add(Version(previous))
    if known and current < max(known):
        raise ValueError(
            f"Version {current} is lower than {max(known)}; refusing release"
        )
    if current in released:
        if current in tagged and release_exists:
            return "skip", f"{current} is already published on PyPI and GitHub"
        return (
            "recover",
            f"{current} is already on PyPI; recover missing GitHub metadata only",
        )
    if current in tagged:
        return "skip", f"Tag v{current} already exists; no duplicate tag or upload"
    if previous is None or current == Version(previous):
        return "skip", "Version has not changed on main; no publication"
    return "publish", f"New version {current}; validation required before publication"


def get_json(url, *, github=False):
    headers = {"Accept": "application/json", "User-Agent": PROJECT + "-release"}
    if github:
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    try:
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise  # Network, authentication and service errors must never mean "new".


def release_info(version):
    return get_json(
        f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{quote('v' + version)}",
        github=True,
    )


def detect(before):
    version = project_version(Path("pyproject.toml").read_text())
    previous = None
    if before and set(before) != {"0"}:
        # A missing/unavailable before commit is an error, not permission to publish.
        previous = project_version(git("show", f"{before}:pyproject.toml"))
    payload = get_json(f"https://pypi.org/pypi/{PROJECT}/json")
    published = (
        []
        if payload is None
        else [v for v, files in payload["releases"].items() if files]
    )
    tags = git("tag", "--list").splitlines()
    exists = (
        release_info(version) is not None
        if Version(version) in tag_versions(tags)
        else False
    )
    action, reason = plan(version, previous, tags, published, exists)
    return {"version": version, "action": action, "reason": reason}


def record():
    """Embed the original source commit in the sdist for later partial recovery."""
    data = {
        "repository": REPOSITORY,
        "commit": git("rev-parse", "HEAD"),
        "version": project_version(Path("pyproject.toml").read_text()),
    }
    Path(PROVENANCE).write_text(json.dumps(data, indent=2) + "\n")


def source_commit(archive_bytes, version):
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        members = [
            m for m in archive.getmembers() if m.name.split("/")[1:] == [PROVENANCE]
        ]
        if len(members) != 1 or not members[0].isfile() or members[0].size > 4096:
            raise ValueError(
                "Published sdist lacks a unique release provenance record; manual recovery required"
            )
        data = json.load(archive.extractfile(members[0]))
    if data.get("repository") != REPOSITORY or data.get("version") != version:
        raise ValueError(
            "Published source provenance does not match this repository/version"
        )
    commit = data.get("commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid source commit in published provenance")
    return commit


def validate_files(payload, version, dist=None):
    if payload["info"]["name"] != PROJECT or Version(
        payload["info"]["version"]
    ) != Version(version):
        raise ValueError("PyPI package metadata does not match requested release")
    files = payload["urls"]
    if (
        not any(f["packagetype"] == "bdist_wheel" for f in files)
        or sum(f["packagetype"] == "sdist" for f in files) != 1
    ):
        raise ValueError(
            "PyPI release is incomplete: both wheel and one sdist are required; manual recovery required"
        )
    if dist is not None:
        local = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(dist).iterdir()
            if p.is_file()
        }
        remote = {f["filename"]: f["digests"]["sha256"] for f in files}
        if not local or local != remote:
            raise ValueError(
                "Published artifact filenames/digests differ from the validated build"
            )
    return next(f for f in files if f["packagetype"] == "sdist")


def verify(version, dist=None, attempts=1):
    payload = None
    for attempt in range(attempts):
        payload = get_json(f"https://pypi.org/pypi/{PROJECT}/{quote(version)}/json")
        if payload is not None:
            break
        if attempt + 1 < attempts:
            time.sleep(10)
    if payload is None:
        raise ValueError(f"PyPI does not show {PROJECT} {version}; tagging is blocked")
    sdist = validate_files(payload, version, dist)
    parsed = urlparse(sdist["url"])
    if parsed.scheme != "https" or parsed.netloc != "files.pythonhosted.org":
        raise ValueError("Unexpected PyPI artifact host")
    with urlopen(sdist["url"], timeout=30) as response:
        content = response.read(32 * 1024 * 1024 + 1)
    if (
        len(content) > 32 * 1024 * 1024
        or hashlib.sha256(content).hexdigest() != sdist["digests"]["sha256"]
    ):
        raise ValueError("Published sdist size/digest verification failed")
    commit = source_commit(content, version)
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "origin/main"], check=True
    )
    if project_version(git("show", f"{commit}:pyproject.toml")) != version:
        raise ValueError("Published source commit has a different project version")
    if dist is not None and commit != git("rev-parse", "HEAD"):
        raise ValueError("Published artifacts do not belong to this workflow commit")
    return commit


def complete_github(version, commit):
    """Only call after verify(). Never move a tag or edit/delete an existing release."""
    tag = "v" + version
    tags = git("tag", "--list").splitlines()
    if tag in tags:
        if git("rev-list", "-n", "1", tag) != commit:
            raise ValueError(
                f"Existing {tag} points to a different commit; manual recovery required"
            )
    else:
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=github-actions[bot]",
                "-c",
                "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                "tag",
                "-a",
                tag,
                commit,
                "-m",
                f"Release {tag}",
            ],
            check=True,
        )
        subprocess.run(["git", "push", "origin", f"refs/tags/{tag}"], check=True)
    if release_info(version) is not None:
        print(f"GitHub Release {tag} already exists; left unchanged")
        return
    notes = Path(os.environ.get("RUNNER_TEMP", ".")) / "docx-color-release-notes.md"
    notes.write_text(
        f"PyPI: https://pypi.org/project/{PROJECT}/{version}/\n\n"
        "Install:\n```bash\nuv tool install docx-color-cli\n```\n\n"
        "After saving the accepted copy in Word:\n```bash\n"
        "docx-color tracked.docx accepted.docx colored.docx\n```\n"
    )
    command = [
        "gh",
        "release",
        "create",
        tag,
        "--repo",
        REPOSITORY,
        "--verify-tag",
        "--title",
        tag,
        "--generate-notes",
        "--notes-file",
        str(notes),
    ]
    if Version(version).is_prerelease:
        command.append("--prerelease")
    subprocess.run(command, check=True)


def output(values):
    print(json.dumps(values, indent=2))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            stream.writelines(f"{key}={value}\n" for key, value in values.items())
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write(
                "\n"
                + "\n".join(f"- {key}: {value}" for key, value in values.items())
                + "\n"
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["detect", "record", "verify", "github"])
    parser.add_argument("--before", default=os.environ.get("BEFORE_SHA"))
    parser.add_argument("--version")
    parser.add_argument("--dist")
    args = parser.parse_args()
    try:
        if args.command == "detect":
            output(detect(args.before))
        elif args.command == "record":
            record()
        else:
            version = project_version(Path("pyproject.toml").read_text())
            if args.version != version:
                raise ValueError("Requested release differs from pyproject.toml")
            commit = verify(version, args.dist, attempts=6)
            if args.command == "github":
                complete_github(version, commit)
            output({"version": version, "commit": commit})
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Release failed: {error}\n")


if __name__ == "__main__":
    main()
