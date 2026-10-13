# Releasing docx-color-cli

`pyproject.toml` is the single source of truth for the version. Releases use GitHub
Actions and PyPI Trusted Publishing (OIDC), with no PyPI API token.

## Normal release

After the one-time setup below, update only the version in `pyproject.toml`, for
example from `0.3.0` to `0.4.0`, then commit and push:

```bash
git add pyproject.toml
git commit -m "chore: release v0.4.0"
git push origin main
```

No tag, manual workflow dispatch, or manual PyPI upload is needed. For a version-only
change, CI uses `uv sync` to refresh the root project's lock metadata in its
checkout; you do not need to edit a second version constant or commit a generated
lock update. Dependency changes should still include an updated `uv.lock`.

The `Publish` workflow runs on every push to `main`. It reads the current and
pre-push versions with Python `tomllib` and compares Git tags and nonempty PyPI
releases with `packaging.version.Version` (PEP 440):

| State | Action |
| --- | --- |
| Version unchanged, no incomplete release | Run normal CI; do not publish or tag |
| Version increased and absent from Git/PyPI | Validate, build, publish, verify, tag and create a release |
| Version lower than the previous main version or any known release | Fail; publish nothing |
| Version already on PyPI | Never upload duplicate artifacts; skip or recover missing GitHub metadata |
| Tag already exists but PyPI version is absent | Skip; report the existing tag, investigate manually |
| First push with no previous commit | Skip initial publication; a later version bump is required |

Adding these workflows alone does not publish the unchanged current version.
Invalid versions and local-version identifiers are rejected. Prereleases use PEP
440 ordering and are marked as prereleases on GitHub.

## Validation and publication order

1. Detect the version and reject downgrades. PyPI/network errors fail closed.
2. Run the reusable CI workflow: Python 3.11–3.13 on Linux/macOS/Windows, Ruff lint
   and formatting, complete pytest suite, package build, strict Twine metadata
   checks and clean-wheel installation/conversion.
3. Record the source commit in a generated `release-provenance.json`, build the
   wheel and sdist, validate metadata and smoke-test the release wheel.
4. Transfer those exact distributions to the dedicated publishing job.
5. Recheck PyPI immediately before upload to avoid duplicating a version published
   during validation. Publish using `pypa/gh-action-pypi-publish@release/v1` and OIDC in environment
   `pypi`. This job alone receives `id-token: write`.
6. Verify PyPI contains both distributions. For a fresh publication, compare every
   filename and SHA-256 against the tested artifacts. Download the sdist from PyPI,
   verify its hash, and read its source commit without extracting the archive.
7. Confirm that commit belongs to `main` and has the same project version.
8. Create and push annotated tag `v<version>` at that source commit, then create a
   GitHub Release with generated commit-history notes, the PyPI link and install
   commands. Only this completion job receives `contents: write`.

Publication and tagging happen in the same workflow execution. The workflow does
not depend on tags created by `GITHUB_TOKEN` triggering another workflow. Releases
are serialized with concurrency group `pypi-release`, without canceling an active
release. Normal push/PR CI has read-only permissions and cannot publish.

GitHub may replace a queued concurrency run with a newer queued run. If several
version bumps are pushed rapidly, inspect the Actions history; the pipeline may
publish only the latest queued version. Do not stack release bumps before the
previous release completes.

## One-time PyPI configuration

Configure a Trusted Publisher in the existing project's **Publishing** settings,
or create a **pending publisher** in your PyPI account if the project does not yet
exist:

| PyPI field | Value |
| --- | --- |
| Project name (pending publisher) | `docx-color-cli` |
| Owner | `colabomics` |
| Repository | `docx-color-cli` |
| Workflow filename | `publish.yml` |
| Environment | `pypi` |

You must own the existing PyPI project, or be able to register that project name.
Do not add `PYPI_API_TOKEN` or a publishing password to GitHub secrets. The
publisher workflow must match these settings exactly. See PyPI's official
[Trusted Publisher setup](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
and [publishing guidance](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## One-time GitHub configuration

- Enable Actions and allow the official `actions/*` actions plus
  `pypa/gh-action-pypi-publish`.
- Create repository environment **pypi** and restrict deployment branches to
  **main** (do not allow arbitrary branches or tags).
- For fully automatic releases, do not require a manual reviewer on that
  environment. Adding reviewers intentionally turns publication into an approval
  step.
- Permit the workflow's scoped OIDC permission and `contents: write` for the
  GitHub completion job. No personal access token is required.
- Ensure repository tag rules allow GitHub Actions to create `v*` tags. The
  workflow will not force-push or bypass a rule automatically.
- Protect `main` and require all CI matrix checks before merging; review changes
  to workflows and release scripts carefully. No `pull_request_target` workflow
  is used.

The regular CI workflow and release validation may both run on a release commit.
The release uses its own reusable CI dependency, so unrelated or stale CI results
cannot authorize publication.

## Diagnosing failures and partial releases

Open **Actions → Publish → the failing run** and read the job log and summary.
Fix the cause, then choose **Re-run all jobs** so detection observes current Git
and PyPI state again. Re-running only a failed publish job can reuse an old
`publish` decision and is not the recommended recovery path.

- **Tests/lint/build/metadata/smoke failure:** no publication occurs. Fix the issue
  and rerun, or push the fix and rerun the original release run after ensuring its
  source is suitable. If the fix changes source code, use a new version bump to
  release the corrected commit; an ordinary unchanged-version push does not
  initiate a new publication.
- **OIDC rejection:** check the exact owner, repository, `publish.yml`, environment
  and PyPI project ownership; then rerun all jobs.
- **PyPI published, tag/release missing:** rerun all jobs. Detection selects
  recovery, reruns CI, skips upload, and reads the original source commit from the
  published sdist. Missing GitHub metadata is created at that commit, even if
  `main` has advanced with the same version. Existing tags/releases are never
  overwritten or deleted. Verification/tagging failure is reported as a partial
  release, not full success.
- **Only some artifacts reached PyPI:** automatic recovery refuses an incomplete
  wheel/sdist pair. An owner must inspect the retained `distributions` workflow
  artifact and PyPI files. Do not blindly upload or rebuild a released version;
  the straightforward recovery is to fix the issue and release a new version.
- **Artifacts differ from the validated build, provenance is missing, or a tag
  points elsewhere:** automatic completion refuses. Inspect the original run,
  published artifacts and source history manually. Legacy releases without a
  provenance record require an owner to establish the original commit before
  manually creating missing metadata. Never move an existing tag automatically.
- **PyPI version not immediately visible:** verification retries lookup for about
  a minute. If it still fails, publication may have succeeded; rerun all jobs to
  verify and recover.
- **Network/authentication/rate-limit errors:** the workflow stops. A failed
  request is never interpreted as an unpublished version.

Workflow artifacts are retained for 30 days. Once both PyPI and GitHub metadata
exist, rerunning the workflow exits successfully without changing either.

## Local checks

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
uv run twine check --strict dist/*
uv run python scripts/smoke_wheel.py dist/*.whl
```

Run the smoke test with only one target wheel (or pass its exact path if `dist/`
contains older builds). It installs the wheel into a new temporary environment,
runs `docx-color --help` and `--version` outside the checkout, verifies the import
comes from that environment, and compares installed and development conversion
results. Local builds do not publish or create release tags. Do not run
`scripts/release.py github` locally as a validation command: it mutates GitHub.
