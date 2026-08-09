from __future__ import annotations

from typing import Any


LEVEL_WEIGHT = {"unknown": 1.0, "low": 0.5, "medium": 1.0, "high": 1.5}


def analyze(state: dict) -> dict:
    hypotheses = [h for h in state["hypotheses"].values() if h["status"] == "active"]
    evidence = [e for e in state["evidence"].values() if e["status"] == "active"]
    diagnosticity = []
    for item in evidence:
        cells = [state["matrix"].get(f'{item["id"]}:{h["id"]}') for h in hypotheses]
        signatures = {(c or {}).get("rating", "not_assessed") for c in cells}
        if len(signatures) <= 1:
            label = "none"
        elif "inconsistent" in signatures and "consistent" in signatures:
            label = "high"
        elif "inconsistent" in signatures or "consistent" in signatures:
            label = "medium"
        else:
            label = "low"
        diagnosticity.append({"evidence_id": item["id"], "diagnosticity": label, "ratings": sorted(signatures)})
    summaries = []
    for hypothesis in hypotheses:
        contributions, raw, adjusted = [], 0, 0.0
        for item in evidence:
            cell = state["matrix"].get(f'{item["id"]}:{hypothesis["id"]}')
            if cell and cell["rating"] == "inconsistent":
                amount = cell["strength"]
                weight = LEVEL_WEIGHT[item["credibility"]] * LEVEL_WEIGHT[item["importance"]]
                raw += amount
                adjusted += amount * weight
                contributions.append({"evidence_id": item["id"], "strength": amount, "adjusted": amount * weight})
        summaries.append({"hypothesis_id": hypothesis["id"], "raw_inconsistency": raw, "adjusted_inconsistency": round(adjusted, 3), "contributions": contributions})
    summaries.sort(key=lambda row: (row["adjusted_inconsistency"], row["raw_inconsistency"], row["hypothesis_id"]))
    rank = 0
    prior = None
    for index, row in enumerate(summaries, 1):
        pair = (row["adjusted_inconsistency"], row["raw_inconsistency"])
        if pair != prior:
            rank = index
        row["heuristic_rank"] = rank
        prior = pair
    return {"rubric_version": 1, "warning": "Scores are heuristic aids, not probabilities or verdicts.", "hypotheses": summaries, "evidence": diagnosticity}


def gaps(state: dict) -> list[dict]:
    hypotheses = [h for h in state["hypotheses"].values() if h["status"] == "active"]
    evidence = [e for e in state["evidence"].values() if e["status"] == "active"]
    return [{"evidence_id": e["id"], "hypothesis_id": h["id"]} for e in evidence for h in hypotheses if f'{e["id"]}:{h["id"]}' not in state["matrix"] or state["matrix"][f'{e["id"]}:{h["id"]}']["rating"] == "not_assessed"]
