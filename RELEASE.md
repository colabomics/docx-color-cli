# Automatic PyPI publication

The `Publish` workflow runs on pushes to `main`. It reads
`project.version` from `pyproject.toml` at the pre-push commit and the new commit.

- Version changed: build the wheel and source distribution, then upload to PyPI.
- Version unchanged: skip building and publishing, even if other files changed.
- A newly created branch without a previous commit establishes the baseline and does not publish.

Publication does not wait for CI, tests, lint, Twine checks, a manual workflow
invocation, or `PYPI_RELEASE_ENABLED`. The ordinary CI workflow runs independently.
The current version stays unchanged until a maintainer edits it.

## Upload authentication

The upload uses PyPI Trusted Publishing (OIDC), with `id-token: write` limited to
the upload job. The `pypi` environment identifies the publisher; there is no
additional approval gate configured by this workflow.

The PyPI publisher identity must be:

| Field | Value |
| --- | --- |
| Owner | `colabomics` |
| Repository | `docx-color-cli` |
| Workflow | `publish.yml` |
| Environment | `pypi` |

GitHub environment settings and PyPI authentication are enforced by those services;
the workflow cannot bypass them. No long-lived PyPI token is used.

The workflow uploads only `*.whl` and `*.tar.gz`. It does not create Git tags or
GitHub Releases. Existing PyPI files cannot be overwritten; upload failures remain
visible in Actions. There is no pre-publication tag, version-order or PyPI lookup.

Changing the workflow alone does not retroactively publish an unchanged version.
The automatic rule takes effect when this workflow is on `main` and a subsequent
push changes `project.version`.
