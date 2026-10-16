"""Validated revision-guided workflow and staged primary/auxiliary publication."""

import json
import re
import sys
import time
import tracemalloc
import unicodedata
from collections import Counter
from copy import copy
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile, ZipFile

from lxml import etree

from .accepted import Package
from .alignment import align
from .coloring import color, prepare
from .errors import ColoringError
from .extract import attach_offsets, extract
from .math_coloring import plan as plan_math
from .pair import validate_pair
from .projection import paragraphs
from .validation import digest, distinct_paths, expected_events, validate_output


def preflight_paths(paths):
    """Check aliases, overlapping file paths and destination types before staging.

    Creating sibling temporary files exercises directory write access. A later
    rename can still fail; this is not a cross-file transaction or a lock.
    """
    distinct_paths(paths)
    # samefile() cannot compare absent destinations. Case-insensitive and
    # Unicode-normalizing filesystems may otherwise let JSON replace the DOCX
    # after its successful publication. Refuse these spellings conservatively
    # on every platform, including case-sensitive filesystems.
    output, report = paths[2:]
    if output is not None and report is not None:
        names = [
            unicodedata.normalize("NFC", str(p.resolve())).casefold()
            for p in (output, report)
        ]
        if names[0] == names[1]:
            raise ValueError(
                "Output and report names must differ beyond case or Unicode spelling"
            )
    resolved = [p.resolve() for p in paths if p is not None]
    if any(a in b.parents for a in resolved for b in resolved if a != b):
        raise ValueError(
            "Input, output and report file paths must not contain one another"
        )
    for path in paths[2:]:
        if path is not None and (
            path.is_symlink() or path.exists() and not path.is_file()
        ):
            raise ValueError(
                "Output and report destinations must be regular files, not symlinks"
            )


def convert(
    tracked_path,
    accepted_path,
    output_path,
    *,
    inserted_color="FF0000",
    report_path=None,
):
    paths = [
        Path(p) if p is not None else None
        for p in (tracked_path, accepted_path, output_path, report_path)
    ]
    tracked_path, accepted_path, output_path, report_path = paths
    try:
        preflight_paths(paths)
    except (ValueError, OSError) as exc:
        if tracked_path.resolve() == accepted_path.resolve() or (
            tracked_path.exists()
            and accepted_path.exists()
            and tracked_path.samefile(accepted_path)
        ):
            raise ColoringError(
                "INVALID_DOCUMENT_PAIR",
                "Tracked and Accepted must be separate files with their respective revision states.",
            ) from exc
        raise ColoringError(
            "OUTPUT_ERROR",
            "Output/report must be distinct regular files, separate from both inputs and from each other's directories.",
        ) from exc
    if output_path.suffix.lower() != ".docx":
        raise ColoringError("OUTPUT_ERROR", "Output path must end in .docx")
    if not isinstance(inserted_color, str) or not re.fullmatch(
        "[0-9a-fA-F]{6}", inserted_color
    ):
        raise ColoringError(
            "INVALID_COLOR",
            "Color must contain exactly six hexadecimal digits without #.",
        )
    rgb = inserted_color.upper()
    hashes = {}
    for role, path in (("tracked", tracked_path), ("accepted", accepted_path)):
        try:
            hashes[role] = digest(path)
        except OSError as exc:
            raise ColoringError(
                "INVALID_DOCX",
                f"The {role} input does not exist or is not a readable DOCX file.",
            ) from exc
    started = time.perf_counter()
    tracemalloc.start()
    temp = report_temp = None
    report = None
    published = False
    phase = "INPUT"
    try:
        tracked, accepted = Package(tracked_path), Package(accepted_path, accepted=True)
        records, extraction = extract(tracked)
        projected = paragraphs(tracked, records)
        attach_offsets(records, projected)
        pair_validation = validate_pair(projected, accepted.paragraphs)
        phase = "PROCESSING"
        extracted = time.perf_counter()
        mappings, evidence = align(
            projected, accepted.paragraphs, records, accepted_xml=accepted.xml
        )
        math_controls, math_report = plan_math(
            projected, accepted.paragraphs, records, mappings
        )
        selected = prepare(mappings, accepted.paragraphs)
        aligned = time.perf_counter()
        expected = expected_events(accepted, selected, rgb, math_controls)
        coloring, changed_roots = color(selected, rgb, math_controls)
        changed = {name for name, root in accepted.xml.items() if root in changed_roots}
        phase = "OUTPUT"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            dir=output_path.parent, suffix=".docx", delete=False
        ) as stream:
            temp = Path(stream.name)
        with ZipFile(temp, "w") as archive:
            archive.comment = accepted.comment
            for info in accepted.infos:
                data = (
                    etree.tostring(
                        accepted.xml[info.filename],
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    )
                    if info.filename in changed
                    else accepted.data[info.filename]
                )
                written = copy(info)
                archive.writestr(written, data)
                # zipfile fills zero external_attr with POSIX defaults on write.
                # Restore the authoritative central-directory value before close.
                written.external_attr = info.external_attr
        colored = time.perf_counter()
        phase = "FIDELITY"
        integrity = validate_output(temp, accepted, expected, changed)
        if (
            digest(tracked_path) != hashes["tracked"]
            or digest(accepted_path) != hashes["accepted"]
        ):
            raise ValueError("An input file changed during processing")
        integrity["input_hashes_unchanged"] = True
        counts = Counter(m.status for m in mappings)
        eligible = [m for m in mappings if m.eligible]
        eligible_mapped = sum(m.status in {"EXACT", "ALIGNED"} for m in eligible)
        by_key = {r.key: r for r in records.values()}
        ordinary = [m for m in mappings if by_key[m.origin].kind == "ORDINARY"]
        ordinary_mapped = sum(m.status in {"EXACT", "ALIGNED"} for m in ordinary)
        ended = time.perf_counter()
        peak = tracemalloc.get_traced_memory()[1]
        report = {
            "architecture": "revision-guided-coloring",
            "input_sha256": hashes,
            "files": {
                "tracked": tracked_path.name,
                "accepted": accepted_path.name,
                "output": str(output_path.absolute()),
            },
            "pair_validation": pair_validation,
            "uncolored_candidates": remaining_categories(projected, mappings),
            "extraction": {
                **extraction,
                "eligible_inserted_characters": len(eligible),
                "ordinary_inserted_characters": len(ordinary),
                "inline_text_in_complex_insertions": sum(
                    by_key[m.origin].kind == "COMPLEX" for m in eligible
                ),
                "mathematical_inserted_characters": sum(
                    by_key[m.origin].kind == "MATHEMATICAL" for m in eligible
                ),
                "ordinary_text_insertions": extraction["insertion_kinds"].get(
                    "ORDINARY", 0
                ),
                "unsupported_complex_insertions": sum(
                    extraction["insertion_kinds"].get(k, 0)
                    for k in (
                        "COMPLEX",
                        "MATHEMATICAL",
                        "MOVED",
                        "TABLE_STRUCTURE",
                        "UNSUPPORTED_PART",
                    )
                ),
                "projected_insertion_character_candidates": len(mappings),
                "unresolved_projection_reasons": dict(
                    Counter(reason for p in projected for reason in p.unresolved)
                ),
                "unresolved_projection_paragraphs": sum(
                    bool(p.unresolved) for p in projected
                ),
            },
            "mapping": {
                **{
                    s.lower() + "_characters": counts[s]
                    for s in (
                        "EXACT",
                        "ALIGNED",
                        "AMBIGUOUS",
                        "UNMAPPED",
                        "UNSUPPORTED",
                    )
                },
                "eligible_status_counts": dict(Counter(m.status for m in eligible)),
                "eligible_uniquely_mapped_characters": eligible_mapped,
                "ordinary_uniquely_mapped_characters": ordinary_mapped,
                "ordinary_insertion_coverage": ordinary_mapped / len(ordinary)
                if ordinary
                else None,
                "insertion_character_coverage": eligible_mapped / len(eligible)
                if eligible
                else None,
                **evidence,
            },
            "mathematics": math_report,
            "completeness": {
                "status": "PARTIAL"
                if any(m.status not in {"EXACT", "ALIGNED"} for m in mappings)
                or math_report["uncolored_inserted_controls"]
                else "COMPLETE",
                "ordinary_characters_uncolored": len(ordinary) - ordinary_mapped,
                "eligible_characters_uncolored": len(eligible) - eligible_mapped,
                "other_projected_candidates_uncolored": sum(
                    not m.eligible and m.status not in {"EXACT", "ALIGNED"}
                    for m in mappings
                ),
            },
            "coloring": {
                **coloring,
                "inserted_characters_not_colored": len(mappings)
                - coloring["characters_colored"],
                "correctly_colored_characters_against_mapping": coloring[
                    "characters_colored"
                ],
                "incorrectly_colored_unchanged_characters_independent": None,
                "independently_verified_false_coloring_count": None,
                "accuracy_note": "Plan invariants are verified. Real insertion-origin accuracy requires independent correspondence labels.",
            },
            "integrity": integrity,
            "performance": {
                "extraction_seconds": extracted - started,
                "alignment_seconds": aligned - extracted,
                "coloring_and_write_seconds": colored - aligned,
                "validation_seconds": ended - colored,
                "total_seconds": ended - started,
                "peak_python_allocated_bytes": peak,
            },
            "mapping_evidence_counts": dict(Counter(m.evidence for m in mappings)),
            "changed_xml_parts": sorted(changed),
            # This success receipt is staged privately. It is only installed
            # after the DOCX commit; failed JSON publication returns a warning
            # receipt in memory and leaves any previous JSON file unchanged.
            "publication": {
                "status": "SUCCESS",
                "docx_published": True,
                "report_status": "PUBLISHED"
                if report_path is not None
                else "NOT_REQUESTED",
                "report_published": report_path is not None,
                "output_sha256": digest(temp),
                "warnings": [],
            },
        }
        result_statuses(report)
        phase = "OUTPUT"
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                dir=report_path.parent, suffix=".json", delete=False
            ) as stream:
                report_temp = Path(stream.name)
            report_temp.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
            if json.loads(report_temp.read_text(encoding="utf-8")) != report:
                raise ValueError("Staged JSON report verification failed")
        # Last fallible pre-publication checks, after BOTH files are prepared.
        preflight_paths(paths)
        if (
            digest(tracked_path) != hashes["tracked"]
            or digest(accepted_path) != hashes["accepted"]
        ):
            raise ValueError("An input file changed before publication")
        if digest(temp) != report["publication"]["output_sha256"]:
            raise ValueError("Staged DOCX changed before publication")
        temp.replace(output_path)
        published = True
        temp = None
        if report_temp is not None:
            try:
                report_temp.replace(report_path)
                report_temp = None
            except OSError as exc:
                report["publication"].update(
                    status="DOCX_PUBLISHED_REPORT_FAILED",
                    report_status="FAILED",
                    report_published=False,
                )
                report["publication"]["warnings"].append(
                    {
                        "code": "REPORT_PUBLISH_FAILED",
                        "error_type": type(exc).__name__,
                        "errno": exc.errno,
                    }
                )
        return report
    except ColoringError:
        raise
    except (OSError, ValueError, BadZipFile, etree.XMLSyntaxError) as exc:
        code = (
            "INVALID_DOCX"
            if phase == "INPUT"
            else "OUTPUT_ERROR"
            if phase == "OUTPUT" or isinstance(exc, OSError)
            else "INTERNAL_ERROR"
        )
        message = {
            "INVALID_DOCX": "Input is not a valid supported DOCX package. Check ZIP, XML and package relationships.",
            "OUTPUT_ERROR": "Cannot stage or publish output/report. Check the destination directory, permissions and available space.",
            "INTERNAL_ERROR": "Processing or content-fidelity validation failed; output was not published.",
        }[code]
        raise ColoringError(code, message) from exc
    finally:
        tracemalloc.stop()
        for pending in (temp, report_temp):
            if pending is not None:
                try:
                    pending.unlink(missing_ok=True)
                except OSError as exc:
                    # Cleanup must not turn a committed, validated DOCX into
                    # an opaque failure. Expose the residual file for recovery.
                    if published:
                        report["publication"]["warnings"].append(
                            {
                                "code": "TEMP_CLEANUP_FAILED",
                                "temporary_file": str(pending),
                                "error_type": type(exc).__name__,
                            }
                        )
                    else:
                        print(
                            f"docx-color warning: temporary-file cleanup failed: {pending}",
                            file=sys.stderr,
                        )
        # No input reads or other fallible verification after the DOCX commit.
        # Inputs were checked immediately before it and are never written.
        if not published and (
            digest(tracked_path) != hashes["tracked"]
            or digest(accepted_path) != hashes["accepted"]
        ):
            raise ValueError("Input integrity check failed")
        if published:
            result_statuses(report)


def result_statuses(report):
    """Keep primary publication, coloring completeness and auxiliary warnings distinct."""
    report["publication_status"] = "SUCCESS"
    report["coloring_status"] = (
        "PARTIAL" if report["completeness"]["status"] == "PARTIAL" else "SUCCESS"
    )
    report["overall_status"] = (
        "PARTIAL"
        if report["coloring_status"] == "PARTIAL" or report["publication"]["warnings"]
        else "SUCCESS"
    )
    warnings = []
    if report["coloring_status"] == "PARTIAL":
        warnings.append(
            {
                "code": "UNSUPPORTED_CONTENT",
                "message": "Coloring is incomplete. Unmapped candidates were left unchanged; inspect the report and review the output.",
            }
        )
    for warning in report["publication"]["warnings"]:
        warning = dict(warning)
        warning["message"] = (
            "Validated DOCX was published, but the auxiliary report was not. Any previous report is unchanged and may be stale; compare its output hash."
            if warning["code"] == "REPORT_PUBLISH_FAILED"
            else "DOCX was published, but a temporary file could not be removed; see the publication receipt."
        )
        warnings.append(warning)
    report["warnings"] = warnings


def remaining_categories(source, mappings):
    """Descriptive candidate counts, not a new survival or accuracy denominator."""
    from .projection import W

    counts = Counter()
    for m in mappings:
        if m.status in {"EXACT", "ALIGNED"}:
            continue
        node, _ = source[m.source].locations[m.offset]
        if m.eligible:
            kind = "eligible_text"
        elif any(n.tag == W + "moveFrom" for n in node.iterancestors()):
            kind = "move_source_candidates"
        elif node.tag in {W + "tab", W + "br", W + "cr"}:
            kind = "non_text_controls"
        else:
            kind = "other_unresolved_provenance"
        counts[kind] += 1
    return {
        k: counts[k]
        for k in (
            "eligible_text",
            "move_source_candidates",
            "non_text_controls",
            "other_unresolved_provenance",
        )
    }
