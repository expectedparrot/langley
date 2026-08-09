from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import LangleyError


def imports():
    try:
        from edsl import Agent, AgentList, Jobs, Scenario, ScenarioList, Survey
        from edsl.questions import QuestionDict, QuestionList
    except ImportError as exc:
        raise LangleyError("DEPENDENCY_ERROR", "EDSL is required for job generation and ingestion.", hint="Reinstall Langley with its declared dependencies.") from exc
    return Agent, AgentList, Jobs, Scenario, ScenarioList, Survey, QuestionDict, QuestionList


def _agents(path: Path | None, persona: str):
    Agent, AgentList, *_ = imports()
    if path:
        try:
            return AgentList.git.load(path) if path.suffix == ".ep" else AgentList.from_dict(__import__("json").loads(path.read_text()))
        except Exception as exc:
            raise LangleyError("EDSL_ERROR", f"Could not load AgentList: {exc}", context={"path": str(path)}) from exc
    return AgentList([Agent(name="langley_analyst", traits={"persona": persona})])


def build(job_type: str, project: dict, state: dict, job_id: str, *, target: str | None = None, agents_path: Path | None = None):
    Agent, AgentList, Jobs, Scenario, ScenarioList, Survey, QuestionDict, QuestionList = imports()
    hypotheses = [h for h in state["hypotheses"].values() if h["status"] == "active"]
    evidence = [e for e in state["evidence"].values() if e["status"] == "active"]
    htext = "\n".join(f'{h["id"]}: {h["name"]} — {h["description"]}' for h in hypotheses) or "(none)"
    etext = "\n".join(f'{e["id"]}: {e["label"]}' for e in evidence) or "(none)"
    common = {"langley_project_id": project["id"], "langley_revision": state["revision"], "langley_job_id": job_id, "job_type": job_type, "question": project["question"], "scope": project.get("scope", ""), "hypothesis_context": htext, "evidence_context": etext, "target_id": target or ""}
    questions = []
    persona = "Careful ACH analyst who seeks disconfirming evidence"
    if job_type == "hypotheses":
        questions = [QuestionList(question_name="hypotheses", question_text="Question: {{ question }}\nScope: {{ scope }}\nExisting alternatives:\n{{ hypothesis_context }}\nPropose distinct reasonable competing hypotheses. Keep plausible unproven alternatives. Format each as NAME | DESCRIPTION | PROVENANCE.", max_list_items=7)]
    elif job_type == "evidence":
        questions = [QuestionList(question_name="evidence", question_text="Question: {{ question }}\nHypotheses:\n{{ hypothesis_context }}\nList observations, arguments, assumptions, and expected-but-absent observations that would distinguish them. Do not invent facts. Format: KIND | LABEL | RELEVANT HYPOTHESES | WHY DIAGNOSTIC.", max_list_items=12)]
    elif job_type == "matrix-row":
        if target not in state["evidence"]: raise LangleyError("NOT_FOUND", f"Unknown evidence {target}.")
        item = state["evidence"][target]
        common["target_evidence"] = f'{item["label"]}\n{item.get("details", "")}'
        for h in hypotheses:
            questions.append(QuestionDict(question_name=f'assess_{h["id"]}', question_text=f'Evidence: {{{{ target_evidence }}}}\nAll hypotheses:\n{{{{ hypothesis_context }}}}\nAssess specifically {h["id"]}. Compare across the full set. Consistency does not prove a hypothesis.', answer_keys=["rating", "strength", "rationale", "assumptions", "confidence"], value_types=[str, int, str, list[str], str], value_descriptions=["consistent, inconsistent, neutral, or not_applicable", "1, 2, or 3; use 1 for neutral/not_applicable", "Concrete reasoning", "Assumptions behind the judgment", "low, medium, or high"]))
    elif job_type == "red-team":
        questions = [QuestionList(question_name="challenges", question_text="Question: {{ question }}\nHypotheses:\n{{ hypothesis_context }}\nEvidence:\n{{ evidence_context }}\nChallenge the tentative assessment. Identify alternate interpretations, source weaknesses, missing hypotheses, deception possibilities, and sensitivity tests. Format each as TARGET | CHALLENGE | TEST.", max_list_items=10)]
        persona = "Adversarial but constructive ACH red-team analyst"
    elif job_type == "indicators":
        questions = [QuestionList(question_name="indicators", question_text="Question: {{ question }}\nHypotheses:\n{{ hypothesis_context }}\nSuggest observable future milestones that support or weaken specific hypotheses. Format: DESCRIPTION | OBSERVABLE IN | SUPPORTS | WEAKENS | THRESHOLD.", max_list_items=10)]
    else: raise LangleyError("VALIDATION_ERROR", f"Unknown job type {job_type}.")
    scenario = Scenario(common)
    return Jobs(survey=Survey(questions)).by(_agents(agents_path, persona)).by(ScenarioList([scenario]))


def save(jobs: Any, output: Path) -> Any:
    if output.exists(): raise LangleyError("ALREADY_EXISTS", f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    return jobs.git.save(output)


def load_results(path: Path):
    try:
        from edsl import Results
        return Results.git.load(path) if path.suffix == ".ep" else Results.from_dict(__import__("json").loads(path.read_text()))
    except Exception as exc:
        raise LangleyError("EDSL_ERROR", f"Could not load Results: {exc}", context={"path": str(path)}) from exc
