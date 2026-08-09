from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from langley.cli import app


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
    assert outside["data"]["action"]["argv"][0:2] == ["langley", "init"]
    initialize(tmp_path)
    status = invoke(tmp_path, "status")
    assert status["data"]["phase"] == "matrix"
    assert status["next_steps"][0]["argv"] == ["langley", "matrix", "next"]
    assert set(status) == {"schema_version", "command", "argv", "status", "project_root", "revision", "data", "artifacts", "warnings", "errors", "next_steps"}


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
