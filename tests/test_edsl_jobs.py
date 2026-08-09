from __future__ import annotations

import pytest

from langley import edsl_jobs


pytest.importorskip("edsl")


def context():
    project = {"id": "project-1", "question": "What caused the outage?", "scope": "production"}
    state = {
        "revision": 3,
        "hypotheses": {
            "h001": {"id": "h001", "name": "Database", "description": "Saturation", "status": "active"},
            "h002": {"id": "h002", "name": "Deploy", "description": "Bad release", "status": "active"},
        },
        "evidence": {"e001": {"id": "e001", "label": "Connections maxed", "details": "At 14:02", "status": "active"}},
    }
    return project, state


@pytest.mark.parametrize("kind,target", [("hypotheses",None),("evidence",None),("matrix-row","e001"),("red-team",None),("indicators",None)])
def test_jobs_are_model_free_and_portable(tmp_path, kind, target):
    from edsl import Jobs
    project, state = context()
    jobs = edsl_jobs.build(kind, project, state, "j001", target=target)
    assert len(jobs.models) == 0
    assert dict(jobs.scenarios[0])["langley_project_id"] == "project-1"
    output = tmp_path / f"{kind}.jobs.ep"
    edsl_jobs.save(jobs, output)
    loaded = Jobs.git.load(output)
    assert loaded.survey.question_names == jobs.survey.question_names
    assert len(loaded.models) == 0


def test_results_ingest_as_proposals_and_accept_materializes(tmp_path):
    from edsl import Agent, Model, Results, Scenario
    from edsl.results import Result
    from typer.testing import CliRunner
    from langley.cli import app

    runner = CliRunner()
    project_dir = tmp_path / "project"
    init = runner.invoke(app, ["--project-dir", str(project_dir), "init", "--title", "T", "--question", "Q"])
    assert init.exit_code == 0
    generated = runner.invoke(app, ["--project-dir", str(project_dir), "job", "generate", "hypotheses"])
    assert generated.exit_code == 0, generated.output
    payload = __import__("json").loads(generated.output)
    jobs = __import__("edsl").Jobs.git.load(payload["data"]["jobs_path"])
    results = Results(survey=jobs.survey, data=[Result(
        agent=Agent(name="critic"), scenario=Scenario(dict(jobs.scenarios[0])),
        model=Model("test"), iteration=0,
        answer={"hypotheses": ["Database | Saturation caused failures | critic", "Deploy | A bad release caused failures | critic"]},
    )])
    result_path = project_dir / ".langley" / "jobs" / "j001" / "results.ep"
    results.git.save(result_path)
    ingested = runner.invoke(app, ["--project-dir", str(project_dir), "job", "ingest", "j001", "--from", str(result_path)])
    assert ingested.exit_code == 0, ingested.output
    proposals = __import__("json").loads(ingested.output)["data"]["proposal_ids"]
    assert len(proposals) == 2
    accepted = runner.invoke(app, ["--project-dir", str(project_dir), "proposal", "accept", proposals[0], "--reason", "Reviewed"])
    assert accepted.exit_code == 0, accepted.output
    sibling = runner.invoke(app, ["--project-dir", str(project_dir), "proposal", "accept", proposals[1], "--reason", "Reviewed"])
    assert sibling.exit_code == 0, sibling.output
    state = __import__("json").loads(runner.invoke(app, ["--project-dir", str(project_dir), "hypothesis", "list"]).output)
    assert state["data"]["hypotheses"][0]["proposal_id"] == proposals[0]
