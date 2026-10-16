"""Independent truth, negative controls, mutation sensitivity and safety checks."""

import ast
from pathlib import Path

import pytest
from helpers.corpus import UNCHANGED, cases, ins, p, package, run
from helpers.evaluate import evaluate_corpus
from helpers.fidelity import accuracy, compare, requested_color
from helpers.mutations import MUTATIONS, evaluate_mutations
from helpers.oracle import corroborate
from helpers.safety import STAGES, evaluate_safety


@pytest.fixture(scope="module")
def gold(tmp_path_factory):
    return evaluate_corpus(tmp_path_factory.mktemp("independent-gold"))[0]


@pytest.mark.parametrize("case_id", [c.ident for c in cases()])
def test_authored_gold_character_truth(gold, case_id):
    row = next(x for x in gold["cases"] if x["id"] == case_id)
    for color in ("default", "control"):
        result = row[color]
        assert result["fidelity"]["overall"] == "PASS"
        assert result["accuracy"]["FP"] == 0
        assert result["accuracy"]["FN"] == {
            "S12": 3,
            "S14": 3,
            "S15": 3,
            "S22": 4,
            "S25": 1,
        }.get(case_id, 0)
    assert row["level_b_against_gold"]["disagreements"] == 0
    assert row["input_hashes_unchanged"]


def test_existing_red_is_not_misattributed(gold):
    row = next(x for x in gold["cases"] if x["id"] == "S19")
    assert row["default"]["accuracy"] == {
        "TP": 4,
        "FP": 0,
        "FN": 0,
        "TN": 7,
        "inserted_already_target_noop": 6,
        "labeled_characters": 17,
        "precision": 1.0,
        "recall": 1.0,
        "false_positive_rate": 0.0,
        "false_negative_rate": 0.0,
    }
    assert row["control"]["accuracy"]["TP"] == 10
    assert row["control"]["accuracy"]["TN"] == 7


@pytest.fixture(scope="module")
def mutation_results(tmp_path_factory):
    return evaluate_mutations(tmp_path_factory.mktemp("independent-mutants"))


@pytest.mark.parametrize("name", MUTATIONS)
def test_independent_checker_detects_mutation(mutation_results, name):
    row = next(x for x in mutation_results["mutations"] if x["mutation"] == name)
    assert row["detected"], row


def test_reserialization_is_not_a_content_failure(mutation_results):
    assert mutation_results["neutral_reserialization_passes"]


@pytest.fixture(scope="module")
def safety_results(tmp_path_factory):
    return evaluate_safety(tmp_path_factory.mktemp("independent-safety"))


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("output_existed", [False, True])
@pytest.mark.parametrize("report_existed", [False, True])
def test_publication_contract(safety_results, stage, output_existed, report_existed):
    row = next(
        x
        for x in safety_results["cases"]
        if (x["stage"], x["output_existed"], x["report_existed"])
        == (stage, output_existed, report_existed)
    )
    assert row["input_hashes_unchanged"]
    assert row["temporary_files_cleaned"]
    assert row["prior_report_state_preserved"]
    if stage == "report_replace":
        assert not row["failure_raised"]
        assert row["published_docx_independently_valid"]
        assert row["publication"]["status"] == "DOCX_PUBLISHED_REPORT_FAILED"
    else:
        assert row["failure_raised"]
        assert row["prior_output_state_preserved"]
    assert row["status"] == "PASS"


def test_auxiliary_failure_is_exposed_in_every_success_receipt(safety_results):
    rows = [x for x in safety_results["cases"] if x["stage"] == "report_replace"]
    assert len(rows) == 4
    assert all(x["publication"]["report_status"] == "FAILED" for x in rows)
    assert all(x["publication"]["warnings"] for x in rows)
    assert safety_results["overall"] == "PASS"


def test_independent_modules_do_not_import_runtime():
    prohibited = {
        "alignment",
        "anchors",
        "projection",
        "coloring",
        "extract",
        "validation",
        "accepted",
        "main",
        "docx_color_cli",
    }
    for filename in ("fidelity.py", "oracle.py", "corpus.py"):
        tree = ast.parse((Path(__file__).parent / "helpers" / filename).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(n.name.split(".")[0] not in prohibited for n in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in prohibited


def test_level_b_refuses_duplicate_retained_run_identity(tmp_path):
    a = package(tmp_path / "a.docx", p(run("same")) + p(ins("same")))
    b = package(tmp_path / "b.docx", p(run("same")) + p(run("same")))
    labels, _, summary = corroborate(a, b)
    assert labels == {} and summary["labeled_characters"] == 0


def test_level_b_refuses_changed_run_identity(tmp_path):
    a = package(tmp_path / "a.docx", p(ins("new")))
    b = package(tmp_path / "b.docx", p(run("new", stamp="000000BB")))
    assert corroborate(a, b)[0] == {}


def test_metrics_detect_false_positive_despite_final_red(tmp_path):
    a = package(tmp_path / "a.docx", p(run("old")))
    b = package(tmp_path / "b.docx", p(run("old", '<w:color w:val="FF0000"/>')))
    result, before, after = compare(a, b, allowed=set())
    assert result["overall"] == "FAIL"
    metrics = accuracy(before, after, {k: UNCHANGED for k in before})
    assert metrics["FP"] == 3 and metrics["precision"] == 0


def test_metrics_do_not_count_unchanged_red_as_tool_activity(tmp_path):
    a = package(tmp_path / "a.docx", p(run("old", '<w:color w:val="FF0000"/>')))
    result, before, after = compare(a, a, allowed=set())
    assert result["actual_color_edits"] == 0
    metrics = accuracy(before, after, {k: UNCHANGED for k in before})
    assert metrics["TN"] == 3 and metrics["FP"] == 0 and metrics["precision"] is None


def test_local_sequence_path_has_independent_authored_labels(tmp_path):
    from test_insertion_mapping import verify_case

    field_a = '<w:fldSimple w:instr="PAGE">' + run("1") + "</w:fldSimple>"
    field_b = '<w:fldSimple w:instr="PAGE">' + run("2") + "</w:fldSimple>"
    # The mapper can identify the inserted word, but the supported pair policy
    # rejects the independently changed display character before publication.
    report = verify_case(
        tmp_path,
        p(run("LEFT")) + p(field_a + ins("new")) + p(run("RIGHT")),
        p(run("LEFT")) + p(field_b + run("new")) + p(run("RIGHT")),
        "LEFT2newRIGHT",
        {5, 6, 7},
        pair_rejected=True,
    )
    assert report["mapping"]["local_alignment_regions"] == 1


def test_unknown_provenance_never_yields_full_pass(tmp_path):
    a = package(tmp_path / "a.docx", p(run("old")))
    b = package(tmp_path / "b.docx", p(run("old", '<w:color w:val="FF0000"/>')))
    result, _, after = compare(a, b)
    assert result["content_fidelity"] == "PASS"
    assert result["overall"] == "PENDING_INDEPENDENT_PROVENANCE"
    assert result["unauthorized_color_characters"] is None
    assert all(c.color == requested_color("FF0000") for c in after.values())
