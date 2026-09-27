from __future__ import annotations

import json
import csv
import os
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from langley.cli import app
from langley.store import Store
import pytest


runner = CliRunner()


def invoke(project: Path, *args: str, ok: bool = True) -> dict:
    result = runner.invoke(app, ["--project-dir", str(project), *args])
    data = json.loads(result.output)
    if ok:
        assert result.exit_code == 0, result.output
        assert data["status"] in {"ok", "warning"}
    return data


def initialize(project: Path) -> None:
    invoke(project, "init", "--title", "Outage", "--question", "What caused it?")
    invoke(project, "hypothesis", "add", "--name", "Database", "--description", "Connection saturation")
    invoke(project, "hypothesis", "add", "--name", "Deploy", "--description", "Bad deployment")
    invoke(project, "evidence", "add", "--label", "Connections maxed", "--kind", "observation", "--credibility", "high", "--importance", "high")


def test_agent_first_envelope_and_next(tmp_path):
    outside = invoke(tmp_path, "next")
    assert outside["data"]["phase"] == "setup"
    assert outside["data"]["action"]["argv"][0:3] == ["langley", "--project-dir", str(tmp_path.resolve())]
    assert outside["data"]["action"]["argv"][3] == "init"
    assert outside["data"]["action"]["cwd"] == str(tmp_path.resolve())
    initialize(tmp_path)
    status = invoke(tmp_path, "status")
    assert status["data"]["phase"] == "matrix"
    assert status["next_steps"][0]["argv"] == ["langley", "--project-dir", str(tmp_path.resolve()), "matrix", "next"]
    assert set(status) == {"schema_version", "command", "argv", "status", "project_root", "revision", "data", "artifacts", "warnings", "errors", "next_steps"}


def actions_in(payload):
    actions = list(payload.get("next_steps", []))
    data = payload.get("data", {})
    if isinstance(data.get("action"), dict):
        actions.append(data["action"])
    actions.extend(data.get("alternatives", []))
    return actions


def assert_portable_actions(payload, project):
    root = str(project.resolve())
    assert payload["project_root"] == root
    for action in actions_in(payload):
        assert action["cwd"] == root
        assert Path(action["cwd"]).is_absolute()
        if action["argv"][0] == "langley":
            assert action["argv"][1:3] == ["--project-dir", root]
        for value in action["argv"]:
            if ".langley" in value:
                assert Path(value).is_absolute()


def test_actions_are_portable_for_unicode_paths_and_distinct_projects(tmp_path):
    caller = tmp_path / "unrelated caller"
    caller.mkdir()
    first = tmp_path / "projects" / "ACH Study α"
    second = tmp_path / "projects" / "ACH Study β"
    invoke(first, "init", "--title", "First", "--question", "What happened?")
    invoke(second, "init", "--title", "Second", "--question", "Another question")

    first_next = invoke(first, "next")
    first_guide = invoke(first, "guide")
    first_status = invoke(first, "status")
    second_next = invoke(second, "next")
    for payload in (first_next, first_guide, first_status):
        assert_portable_actions(payload, first)
    assert_portable_actions(second_next, second)
    assert first_next["data"]["action"]["argv"] != second_next["data"]["action"]["argv"]

    # Execute the returned project selector unchanged while the process is rooted
    # in an unrelated caller directory; only append the action's required content.
    action = first_next["data"]["action"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1])
    result = subprocess.run(
        [sys.executable, "-m", "langley", *action["argv"][1:], "--name", "Extra", "--description", "Third alternative"],
        cwd=caller, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(invoke(first, "hypothesis", "list")["data"]["hypotheses"]) == 1
    assert invoke(second, "hypothesis", "list")["data"]["hypotheses"] == []


def test_complete_manual_workflow_and_report(tmp_path):
    initialize(tmp_path)
    row = tmp_path / "row.json"
    row.write_text(json.dumps({"assessments": [
        {"hypothesis_id": "h001", "rating": "consistent", "strength": 3, "rationale": "Expected under saturation."},
        {"hypothesis_id": "h002", "rating": "inconsistent", "strength": 2, "rationale": "No deployment signature."},
    ]}))
    invoke(tmp_path, "matrix", "set", "--evidence", "e001", "--input", str(row))
    analysis = invoke(tmp_path, "matrix", "analyze")["data"]
    assert analysis["hypotheses"][0]["hypothesis_id"] == "h001"
    assert "not probabilities" in analysis["warning"]

    conclusion = tmp_path / "conclusion.json"
    conclusion.write_text(json.dumps({
        "summary": "Database saturation is least inconsistent.", "confidence": "moderate",
        "hypotheses": [
            {"hypothesis_id": "h001", "rank": 1, "likelihood": "likely", "rationale": "Fits e001."},
            {"hypothesis_id": "h002", "rank": 2, "likelihood": "unlikely", "rationale": "Conflicts with e001."},
        ], "critical_evidence_ids": ["e001"], "critical_assumptions": [], "residual_uncertainty": "Limited evidence."
    }))
    invoke(tmp_path, "conclusion", "draft", "--input", str(conclusion))
    sensitivity = tmp_path / "sensitivity.json"
    sensitivity.write_text(json.dumps({"reason": "e001 may be wrong", "changes": [{"operation": "exclude_evidence", "evidence_id": "e001"}], "result": {"ranking_changed": True}}))
    invoke(tmp_path, "sensitivity", "run", "--name", "Remove e001", "--input", str(sensitivity))
    indicator = tmp_path / "indicator.json"
    indicator.write_text(json.dumps({"description": "Failures recur at low connection use", "observable_in": "telemetry", "supports": ["h002"], "weakens": ["h001"], "threshold": "five minutes"}))
    invoke(tmp_path, "indicator", "add", "--input", str(indicator))
    valid = invoke(tmp_path, "validate", "--strict")
    assert valid["data"]["valid"] is True
    report = invoke(tmp_path, "report", "generate", "--name", "final")
    paths = report["data"]["paths"]
    assert {"report.md", "analysis.json", "matrix.csv", "manifest.json"} == set(paths)
    assert Path(paths["report.md"]).is_file()


def test_revision_conflict_and_event_chain(tmp_path):
    invoke(tmp_path, "init", "--title", "T", "--question", "Q")
    result = runner.invoke(app, ["--project-dir", str(tmp_path), "--if-revision", "9", "hypothesis", "add", "--name", "A", "--description", "B"])
    payload = json.loads(result.output)
    assert result.exit_code == 4
    assert payload["errors"][0]["code"] == "REVISION_CONFLICT"
    assert invoke(tmp_path, "validate")["data"]["issues"][0]["code"] == "TOO_FEW_HYPOTHESES"


def test_matrix_requires_complete_row(tmp_path):
    initialize(tmp_path)
    row = tmp_path / "bad.json"
    row.write_text(json.dumps({"assessments": [{"hypothesis_id": "h001", "rating": "neutral", "rationale": "Does not distinguish."}]}))
    payload = invoke(tmp_path, "matrix", "set", "--evidence", "e001", "--input", str(row), ok=False)
    assert payload["errors"][0]["code"] == "MATRIX_ROW_INCOMPLETE"


def test_evidence_help_is_non_mutating_and_explains_absence(tmp_path):
    result = runner.invoke(app, ["--project-dir", str(tmp_path), "evidence", "add", "--help"], terminal_width=140)
    assert result.exit_code == 0
    assert not (tmp_path / ".langley").exists()
    text = " ".join(result.output.split())
    for option in ("--expected-if", "--observability-rationale", "--search-performed"):
        assert option in text
    assert "Required for absence" in text
    for kind in ("observation", "argument", "assumption", "absence", "context"):
        assert kind in text


@pytest.mark.parametrize("missing", ["--expected-if", "--observability-rationale", "--search-performed"])
def test_absence_failure_has_nonzero_exit_and_does_not_mutate(tmp_path, missing):
    initialize(tmp_path)
    before = Store(tmp_path).revision
    fields = {
        "--expected-if": "h001, h002",
        "--observability-rationale": "The complete release log records every deployment.",
        "--search-performed": "Searched the release log for the outage window.",
    }
    args = ["--project-dir", str(tmp_path), "evidence", "add", "--label", "No deployment", "--kind", "absence"]
    for key, value in fields.items():
        if key != missing:
            args.extend([key, value])
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    assert payload["errors"][0]["code"] == "VALIDATION_ERROR"
    assert "id" not in payload["data"]
    assert Store(tmp_path).revision == before
    assert len(Store(tmp_path).state()["evidence"]) == 1


def test_absence_contract_records_expected_hypotheses(tmp_path):
    initialize(tmp_path)
    result = invoke(tmp_path, "evidence", "add", "--label", "No deployment", "--kind", "absence",
                    "--expected-if", "h001, h002", "--observability", "high",
                    "--observability-rationale", "Every deployment appears in the release log.",
                    "--search-performed", "Searched the release log for the outage window.")
    assert result["data"]["expected_if"] == ["h001", "h002"]
    assert result["data"]["observability"] == "high"


def test_report_matrix_excludes_archived_evidence_but_preserves_audit(tmp_path):
    initialize(tmp_path)
    invoke(tmp_path, "evidence", "add", "--label", "Superseded claim", "--kind", "observation")
    invoke(tmp_path, "evidence", "archive", "e002", "--reason", "Source corrected the claim.")
    report = invoke(tmp_path, "report", "generate", "--name", "audit", "--draft")
    paths = report["data"]["paths"]
    with Path(paths["matrix.csv"]).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["evidence_id"] for row in rows] == ["e001"]
    state = json.loads(Path(paths["analysis.json"]).read_text())["state"]
    assert state["evidence"]["e002"]["status"] == "archived"
    assert len(Store(tmp_path).state()["evidence"]) == 2
