# Release validation and explicit publication

Ordinary source pushes and pull requests run CI only. **They cannot publish.**
The `Publish` workflow now accepts only a deliberate `workflow_dispatch` event
on `main`, with an exact version and an upload request that defaults to **false**.
It runs the complete nine-job OS/Python matrix before building distributions.

This checkout is an unreleased breaking CLI/API migration, still numbered 1.0.1.
Do not upload it as a replacement for an existing 1.0.1 release. Version selection,
commits, pushes, tags and publication require a separate reviewed decision.

## Required owner configuration (not performed by local validation)

Before enabling any upload, a repository/PyPI owner must:

1. Review the workflow and source changes; protect `main` with required PR review
   and all nine CI checks. Restrict repository write/admin access and review all
   changes to publishing workflows and scripts.
2. Create or inspect the GitHub environment **pypi**. Restrict deployment branches
   to **main**; configure trusted required reviewers, prevent self-review and
   disable administrator bypass where available. If the repository plan cannot
   enforce the required protections, keep uploads disabled.
3. Verify the existing PyPI project's Trusted Publisher against this exact tuple:

   | Field | Required value |
   | --- | --- |
   | Owner | `colabomics` |
   | Repository | `docx-color-cli` |
   | Workflow filename | `publish.yml` |
   | Environment | `pypi` |

   An owner must explicitly authorize adding/changing a publisher if one is not
   already configured. This phase does not register or activate one. The workflow
   uses OIDC; it does not reference a long-lived PyPI token or password. Existing
   repository credentials were not inspected, deleted or changed.
4. Only after checking protections and successful cross-platform results, set
   repository variable **PYPI_RELEASE_ENABLED** to the exact string `true`.
   Leave it absent/false for validation-only operation. This extra gate does not
   replace environment approval or repository access controls.

Manual dispatch requires repository write access, but that is not sufficient
protection by itself. GitHub environment reviewers and branch restrictions must
be configured in repository settings; a YAML environment name does not prove
those controls exist. See [GitHub manual workflow access](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
and [environment protections](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

PyPI recommends isolating OIDC upload from build execution and using dedicated
protected environments. Here only the upload job gets `id-token: write`; it has
just artifact download and the official upload action, with no checkout or build.
See [PyPI's security model](https://docs.pypi.org/trusted-publishers/security-model/)
and [Trusted Publisher configuration](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).

## Future intentional release procedure

After separate authorization to release a reviewed version:

1. Obtain passing macOS, Ubuntu and Windows checks on Python 3.11, 3.12 and 3.13
   for the exact source commit. Confirm privacy, benchmark and installation checks.
2. An authorized maintainer opens **Actions → Publish → Run workflow**, selects
   `main` and enters the exact version from the reviewed `pyproject.toml`.
3. Leave `publish` false for build-only validation. A dry run does not request
   OIDC, upload, create tags or create GitHub Release metadata.
4. For an explicitly authorized upload, select `publish` true. The build refuses
   a mismatched version, an already published version or a downgrade. Network
   failures are not interpreted as permission to upload. The repository enable
   variable and independent **pypi** environment approval are both required.
5. Review the exact source SHA and validated artifacts before environment approval.
   Never approve an unexpected workflow or a different source revision.

The workflow no longer automatically creates Git tags or GitHub Releases. Those
are separate intentional actions. Do not run `scripts/release.py github` as a
validation command; it is a retained maintenance tool that mutates remote metadata.
Legacy automatic detection/recovery helpers remain tested but are not on the
workflow's trigger path.

## Interrupted or failed publication

DOCX publication and package publication are separate concerns. For package release:

- Validation/build failure: no upload is authorized.
- Disabled repository gate: build artifacts may exist, but the upload job is skipped.
- Environment approval/identity failure: inspect the environment and exact publisher
  tuple. Do not add an API token as a workaround.
- Upload interruption or duplicate-version race: assume publication may be partial;
  inspect PyPI and the run's retained distributions before any retry. Do not blindly
  rebuild/upload the same version, use `skip-existing`, overwrite published files,
  or move tags. A new version may be necessary after owner review.

Artifacts are retained for 30 days. Concurrency group `pypi-release` serializes
release requests without canceling an active release. Repository administrators
can change workflows/protections; no YAML can defend against a malicious owner.
Action version tags are still trusted upstream references, not pinned commit SHAs.

## Local offline checks

```bash
uv sync
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv build
uv run twine check --strict dist/docx_color_cli-1.0.1-py3-none-any.whl dist/docx_color_cli-1.0.1.tar.gz
uv run python scripts/smoke_wheel.py dist
```

Use a build directory containing one wheel and one sdist; substitute filenames
only after a separately approved version change. The smoke script accepts a
build directory so Windows does not depend on shell wildcard expansion. It creates
an isolated environment and runs both commands outside the checkout. These local
checks do not contact an upload endpoint, publish, tag, push or create a release.
