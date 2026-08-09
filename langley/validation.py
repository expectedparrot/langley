from __future__ import annotations

from .analysis import analyze, gaps


def validate(store) -> list[dict]:
    state, issues = store.state(), store.verify()
    active_h = [h for h in state["hypotheses"].values() if h["status"] == "active"]
    if len(active_h) < 2:
        issues.append({"code": "TOO_FEW_HYPOTHESES", "severity": "error", "message": "At least two active hypotheses are required."})
    for gap in gaps(state):
        issues.append({"code": "MATRIX_GAP", "severity": "error", "context": gap})
    current = [c for c in state["conclusions"].values() if c["status"] == "current"]
    if current:
        conclusion = current[-1]
        covered = {row["hypothesis_id"] for row in conclusion["hypotheses"]}
        missing = {h["id"] for h in active_h} - covered
        if missing:
            issues.append({"code": "CONCLUSION_INCOMPLETE", "severity": "error", "context": {"missing": sorted(missing)}})
        tested = {eid for s in state["sensitivities"].values() for change in s["changes"] for eid in [change.get("evidence_id")] if eid}
        untested = set(conclusion["critical_evidence_ids"]) - tested
        if untested:
            issues.append({"code": "LINCHPIN_UNTESTED", "severity": "error", "context": {"evidence_ids": sorted(untested)}})
        if not state["indicators"]:
            issues.append({"code": "NO_INDICATORS", "severity": "error", "message": "At least one future indicator is required."})
    return issues


def phase(state: dict) -> str:
    h = [x for x in state["hypotheses"].values() if x["status"] == "active"]
    e = [x for x in state["evidence"].values() if x["status"] == "active"]
    if len(h) < 2: return "hypotheses"
    if not e: return "evidence"
    if gaps(state): return "matrix"
    if not state["conclusions"]: return "conclusion"
    current = [c for c in state["conclusions"].values() if c["status"] == "current"]
    if current and current[-1]["critical_evidence_ids"] and not state["sensitivities"]: return "sensitivity"
    if not state["indicators"]: return "indicators"
    return "report-ready"
