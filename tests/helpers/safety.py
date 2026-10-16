"""Publication-contract fault injection on synthetic files only.

Phase 4: DOCX is primary. Pre-commit failures preserve both prior targets;
late auxiliary-report publication failure is an explicit successful DOCX result.
"""

from itertools import product
from pathlib import Path
from unittest.mock import patch

from helpers.corpus import ins, p, package, run
from helpers.fidelity import compare, digest

STAGES = (
    "validation",
    "zip_write",
    "report_prepare",
    "report_write",
    "report_readback",
    "late_input_hash",
    "output_replace",
    "report_replace",
)


def evaluate_safety(directory, *, sut=None):
    if sut is None:
        from docx_color_cli import engine as sut

    results = []
    for stage, output_existed, report_existed in product(
        STAGES, (False, True), (False, True)
    ):
        folder = (
            Path(directory)
            / stage
            / f"docx-{int(output_existed)}-report-{int(report_existed)}"
        )
        folder.mkdir(parents=True, exist_ok=True)
        tracked = package(folder / "tracked.docx", p(ins("new")))
        accepted = package(folder / "accepted.docx", p(run("new")))
        output, report = folder / "existing.docx", folder / "existing.json"
        for target, existed, payload in (
            (output, output_existed, b"prior-user-output"),
            (report, report_existed, b"prior-user-report"),
        ):
            if existed:
                target.write_bytes(payload)
            else:
                target.unlink(missing_ok=True)  # Only this harness's synthetic target.
        inputs = [digest(tracked), digest(accepted)]
        prior = {x.name for x in folder.iterdir()}
        original_replace, original_write = Path.replace, Path.write_text
        original_temporary, original_digest = sut.NamedTemporaryFile, sut.digest
        state = {"report_staged": False}

        def fail(*args, **kwargs):
            raise OSError("synthetic injected failure")

        def replace(
            self,
            target,
            *,
            stage=stage,
            output=output,
            report=report,
            original_replace=original_replace,
        ):
            if Path(target) == (output if stage == "output_replace" else report):
                raise OSError("synthetic injected publication failure")
            return original_replace(self, target)

        def write(
            self,
            *args,
            stage=stage,
            report=report,
            original_write=original_write,
            state=state,
            **kwargs,
        ):
            if self.suffix == ".json" and self != report:
                if stage == "report_write":
                    raise OSError("synthetic injected report-write failure")
                if stage == "report_readback":
                    return original_write(self, "{}", **kwargs)
                state["report_staged"] = True
            return original_write(self, *args, **kwargs)

        def temporary(*args, original_temporary=original_temporary, **kwargs):
            if kwargs.get("suffix") == ".json":
                raise OSError("synthetic injected report-temp failure")
            return original_temporary(*args, **kwargs)

        def checked_digest(
            path, *, tracked=tracked, state=state, original_digest=original_digest
        ):
            if Path(path) == tracked and state["report_staged"]:
                return "0" * 64  # Simulate a concurrent change without writing inputs.
            return original_digest(path)

        if stage == "validation":
            injection = patch.object(sut, "validate_output", fail)
        elif stage == "zip_write":
            injection = patch.object(sut.ZipFile, "writestr", fail)
        elif stage == "report_prepare":
            injection = patch.object(sut, "NamedTemporaryFile", temporary)
        elif stage in {"report_write", "report_readback", "late_input_hash"}:
            injection = patch.object(Path, "write_text", write)
        else:
            injection = patch.object(Path, "replace", replace)
        raised, result = False, None
        with (
            injection,
            patch.object(
                sut,
                "digest",
                checked_digest if stage == "late_input_hash" else original_digest,
            ),
        ):
            try:
                result = sut.convert(tracked, accepted, output, report_path=report)
            except (OSError, ValueError):
                raised = True
        preserved = (
            output.read_bytes() == b"prior-user-output"
            if output_existed
            else not output.exists()
        )
        report_ok = (
            report.read_bytes() == b"prior-user-report"
            if report_existed
            else not report.exists()
        )
        publication = result["publication"] if result else None
        late = stage == "report_replace"
        valid = (
            compare(
                accepted,
                output,
                allowed={("word/document.xml", 0, i) for i in range(3)},
            )[0]["overall"]
            == "PASS"
            if late and output.exists()
            else False
        )
        expected_files = prior | ({output.name} if late else set())
        clean = expected_files == {x.name for x in folder.iterdir()}
        hashes_ok = inputs == [digest(tracked), digest(accepted)]
        contract_ok = (
            (
                not raised
                and publication is not None
                and publication["status"] == "DOCX_PUBLISHED_REPORT_FAILED"
                and publication["docx_published"]
                and not publication["report_published"]
                and publication["output_sha256"] == digest(output)
                and any(
                    w["code"] == "REPORT_PUBLISH_FAILED"
                    for w in publication["warnings"]
                )
                and valid
            )
            if late
            else raised and preserved and result is None
        )
        results.append(
            {
                "stage": stage,
                "output_existed": output_existed,
                "report_existed": report_existed,
                "failure_raised": raised,
                "prior_output_state_preserved": preserved,
                "prior_report_state_preserved": report_ok,
                "temporary_files_cleaned": clean,
                "input_hashes_unchanged": hashes_ok,
                "publication": publication,
                "published_docx_independently_valid": valid if late else None,
                "status": "PASS"
                if contract_ok and clean and hashes_ok and report_ok
                else "FAIL",
            }
        )
    return {
        "contract": "DOCX primary; pre-commit failure preserves targets; late report failure returns explicit DOCX success with warning",
        "overall": "PASS" if all(x["status"] == "PASS" for x in results) else "FAIL",
        "cases": results,
    }
