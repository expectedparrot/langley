from __future__ import annotations

import csv
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import typer

from . import __version__
from .analysis import analyze, gaps
from .errors import LangleyError
from .output import emit, envelope, fail
from .schemas import Actor, CellInput, ConclusionInput, EvidenceInput, HypothesisInput, IndicatorInput, MatrixRowInput, SensitivityInput
from .store import Store, digest, now, write_json
from .validation import phase, validate

app = typer.Typer(no_args_is_help=True, invoke_without_command=True, help="Agent-first Analysis of Competing Hypotheses CLI.")
hypothesis_app, evidence_app, matrix_app = typer.Typer(), typer.Typer(), typer.Typer()
conclusion_app, sensitivity_app, indicator_app = typer.Typer(), typer.Typer(), typer.Typer()
report_app, job_app, job_generate_app, proposal_app, docs_app = typer.Typer(), typer.Typer(), typer.Typer(), typer.Typer(), typer.Typer()
job_app.add_typer(job_generate_app, name="generate")
for name, sub in [("hypothesis", hypothesis_app), ("evidence", evidence_app), ("matrix", matrix_app), ("conclusion", conclusion_app), ("sensitivity", sensitivity_app), ("indicator", indicator_app), ("report", report_app), ("job", job_app), ("proposal", proposal_app), ("docs", docs_app)]:
    app.add_typer(sub, name=name)


class Runtime:
    project_dir: Path | None = None
    human = False
    actor = Actor()
    if_revision: int | None = None


runtime = Runtime()


@app.callback()
def callback(project_dir: Path | None = typer.Option(None, "--project-dir"), human: bool = typer.Option(False, "--human"), actor_type: str = typer.Option(os.getenv("LANGLEY_ACTOR_TYPE", "agent"), "--actor-type"), actor_name: str = typer.Option(os.getenv("LANGLEY_ACTOR_NAME", "unknown"), "--actor-name"), if_revision: int | None = typer.Option(None, "--if-revision"), version: bool = typer.Option(False, "--version", is_eager=True)):
    if version:
        typer.echo(__version__); raise typer.Exit()
    runtime.project_dir, runtime.human = project_dir, human
    runtime.actor = Actor(type=actor_type, name=actor_name)
    runtime.if_revision = if_revision


def store() -> Store:
    return Store(runtime.project_dir or Path.cwd(), explicit=runtime.project_dir is not None)


def argv(command: str) -> list[str]: return command.split() if command.startswith("langley ") else ["langley", *command.split()]
def finish(command: str, data: Any, *, warnings=None, next_steps=None) -> None:
    s = store(); emit(envelope(command, argv(command), data=data, root=s.root, revision=s.revision if s.exists else None, warnings=warnings, next_steps=next_steps), runtime.human)
def guard(command: str, function):
    try: return function()
    except LangleyError as exc: fail(command, argv(command), exc, root=store().root, revision=store().revision if store().exists else None, human=runtime.human)
    except (ValueError, json.JSONDecodeError) as exc: fail(command, argv(command), LangleyError("VALIDATION_ERROR", str(exc)), root=store().root, revision=store().revision if store().exists else None, human=runtime.human)


def read_input(path: Path) -> Any: return json.loads(path.read_text(encoding="utf-8"))
def mutate(kind: str, payload: dict, command: str): return store().append(kind, payload, actor=runtime.actor.model_dump(), argv=argv(command), if_revision=runtime.if_revision)
def analytical_hash(state: dict, ignore_job_id: str | None = None) -> str:
    context={k:v for k,v in state.items() if k not in {"revision","jobs","proposals"}}
    if ignore_job_id:
        proposal_ids={p["id"] for p in state["proposals"].values() if p["job_id"]==ignore_job_id}
        for bucket in ("hypotheses","evidence","matrix","conclusions","sensitivities","indicators"):
            context[bucket]={key:value for key,value in context[bucket].items() if value.get("proposal_id") not in proposal_ids}
    return digest(context)


def proposal_payloads(job: dict, answers: dict) -> list[tuple[str, dict, dict]]:
    kind = job["job_type"]
    if kind == "matrix-row":
        return [("matrix_assessment", {"evidence_id": job["target"]["id"], "hypothesis_id": key.removeprefix("assess_")}, value) for key, value in answers.items() if key.startswith("assess_") and isinstance(value, dict)]
    key = {"hypotheses":"hypotheses","evidence":"evidence","red-team":"challenges","indicators":"indicators"}[kind]
    values = answers.get(key, [])
    if not isinstance(values, list): values = [values]
    output=[]
    for value in values:
        if isinstance(value, dict): output.append((kind.rstrip("s"),{},value)); continue
        parts=[x.strip() for x in str(value).split("|")]
        if kind=="hypotheses" and len(parts)>=2: output.append(("hypothesis",{}, {"name":parts[0],"description":parts[1],"provenance":parts[2] if len(parts)>2 else "EDSL proposal"}))
        elif kind=="evidence" and len(parts)>=2: output.append(("evidence",{}, {"kind":parts[0].lower() if parts[0].lower() in {"observation","argument","assumption","absence","context"} else "argument","label":parts[1],"details":parts[3] if len(parts)>3 else ""}))
        elif kind=="indicators" and len(parts)>=2: output.append(("indicator",{}, {"description":parts[0],"observable_in":parts[1],"supports":parts[2].split(",") if len(parts)>2 else [],"weakens":parts[3].split(",") if len(parts)>3 else [],"threshold":parts[4] if len(parts)>4 else ""}))
        else: output.append(("red_team",{}, {"text":str(value)}))
    return output


@app.command("init")
def init(title: str = typer.Option(...), question: str = typer.Option(...), scope: str = typer.Option("")):
    command = "langley init"
    def run():
        s = store(); project = {"schema_version": 1, "id": uuid.uuid4().hex, "title": title, "question": question, "scope": scope, "created_at": now(), "created_by": runtime.actor.model_dump()}; s.init(project)
        finish(command, {"project": project}, next_steps=[step("Add competing hypotheses", ["langley", "hypothesis", "add"], "At least two alternatives are required.")])
    guard(command, run)


def step(label: str, args: list[str], reason: str, mutates=True, approval=False) -> dict:
    project_root = store().root.resolve()
    portable_args = list(args)
    if portable_args and portable_args[0] == "langley" and "--project-dir" not in portable_args:
        portable_args = ["langley", "--project-dir", str(project_root), *portable_args[1:]]
    return {
        "id": label.lower().replace(" ", "_"), "label": label,
        "argv": portable_args, "cwd": str(project_root),
        "mutates_state": mutates, "requires_user_approval": approval,
        "reason": reason,
    }


def next_action(s: Store) -> tuple[str, list[dict]]:
    if not s.exists: return "setup", [step("Initialize analysis", ["langley", "init", "--title", "<title>", "--question", "<question>"], "No project exists.")]
    state, p = s.state(), phase(s.state())
    if p == "hypotheses": return p, [step("Add a hypothesis", ["langley", "hypothesis", "add"], "At least two active hypotheses are required."), step("Generate hypothesis proposals", ["langley", "job", "generate", "hypotheses"], "EDSL can elicit diverse alternatives.")]
    if p == "evidence": return p, [step("Add evidence", ["langley", "evidence", "add"], "The matrix needs evidence rows."), step("Generate evidence proposals", ["langley", "job", "generate", "evidence"], "EDSL can suggest expected observations.")]
    if p == "matrix":
        gap = gaps(state)[0]; return p, [step("Assess the next evidence row", ["langley", "matrix", "next"], f'{gap["evidence_id"]} has unassessed cells.',False), step("Generate matrix-row proposals", ["langley", "job", "generate", "matrix-row", "--evidence", gap["evidence_id"]], "EDSL can provide independent judgments.")]
    if p == "conclusion": return p, [step("Draft a conclusion", ["langley", "conclusion", "draft", "--input", "conclusion.json"], "All active hypotheses must be compared.")]
    if p == "sensitivity": return p, [step("Run sensitivity test", ["langley", "sensitivity", "run", "--name", "<name>", "--input", "test.json"], "Critical evidence must be challenged."), step("Generate red-team proposals", ["langley", "job", "generate", "red-team"], "EDSL can challenge linchpins.")]
    if p == "indicators": return p, [step("Add an indicator", ["langley", "indicator", "add", "--input", "indicator.json"], "Specify what could change the assessment."), step("Generate indicator proposals", ["langley", "job", "generate", "indicators"], "EDSL can suggest observable milestones.")]
    return p, [step("Generate report", ["langley", "report", "generate"], "The analysis is report-ready.")]


@app.command("guide")
def guide():
    s=store(); p, actions=next_action(s); finish("langley guide", {"authority": "Run `langley next` before each action.", "rules": ["JSON is the default output.", "Scores are heuristics, not probabilities.", "EDSL answers are proposals until reviewed.", "Only `ep run` makes model calls and requires approval."], "phase": p}, next_steps=actions)


@app.command("next")
def next_command():
    s=store(); p, actions=next_action(s); finish("langley next", {"phase": p, "action": actions[0], "alternatives": actions[1:]}, next_steps=actions)


@app.command("status")
def status():
    def run():
        s=store(); s.require(); state=s.state(); p, actions=next_action(s); finish("langley status", {"phase": p, "counts": {k: len(state[k]) for k in ("hypotheses","evidence","matrix","conclusions","sensitivities","indicators","jobs","proposals")}, "validation_issues": validate(s)}, next_steps=actions)
    guard("langley status", run)


@hypothesis_app.command("add")
def hypothesis_add(name: str = typer.Option(...), description: str = typer.Option(...), provenance: str = typer.Option(""), prior_view: str | None = typer.Option(None)):
    command="langley hypothesis add"
    def run():
        s=store(); item=HypothesisInput(name=name,description=description,provenance=provenance,prior_view=prior_view).model_dump(); item.update({"id":s.next_id("hypotheses","h"),"status":"active","created_at":now(),"created_by":runtime.actor.model_dump(),"archived_at":None,"archive_reason":None,"superseded_by":[]}); mutate("hypothesis.created",item,command); finish(command,item)
    guard(command,run)


@hypothesis_app.command("list")
def hypothesis_list(include_archived: bool = typer.Option(False)):
    command="langley hypothesis list"
    def run():
        values=list(store().state()["hypotheses"].values()); finish(command,{"hypotheses":[x for x in values if include_archived or x["status"]=="active"]})
    guard(command,run)


@hypothesis_app.command("show")
def hypothesis_show(identifier: str):
    command="langley hypothesis show"
    def run():
        item=store().state()["hypotheses"].get(identifier)
        if not item: raise LangleyError("NOT_FOUND",f"Unknown hypothesis {identifier}.")
        finish(command,item)
    guard(command,run)


@hypothesis_app.command("import")
def hypothesis_import(input_path: Path=typer.Option(...,"--input")):
    command="langley hypothesis import"
    def run():
        s=store(); raw=read_input(input_path); values=raw if isinstance(raw,list) else raw.get("hypotheses",[]); ids=[]
        for value in values:
            model=HypothesisInput.model_validate(value); item={"id":s.next_id("hypotheses","h"),**model.model_dump(),"status":"active","created_at":now(),"created_by":runtime.actor.model_dump(),"archived_at":None,"archive_reason":None,"superseded_by":[],"import_hash":digest(raw)}; mutate("hypothesis.created",item,command); ids.append(item["id"])
        finish(command,{"imported":ids})
    guard(command,run)


@hypothesis_app.command("archive")
def hypothesis_archive(identifier: str, reason: str = typer.Option(...), citing: str = typer.Option("")):
    command="langley hypothesis archive"
    def run():
        s=store(); state=s.state();
        if identifier not in state["hypotheses"]: raise LangleyError("NOT_FOUND",f"Unknown hypothesis {identifier}.")
        changes={"status":"archived","archived_at":now(),"archive_reason":reason,"archive_citations":[x for x in citing.split(",") if x]}; mutate("hypothesis.updated",{"id":identifier,"changes":changes},command); finish(command,{"id":identifier,**changes},warnings=[] if changes["archive_citations"] else [{"code":"UNPROVEN_ARCHIVE","message":"No inconsistent evidence was cited."}])
    guard(command,run)


@evidence_app.command("add")
def evidence_add(label: str = typer.Option(...), kind: str = typer.Option(...), details: str = typer.Option(""), credibility: str = typer.Option("unknown"), importance: str = typer.Option("unknown"), source: str = typer.Option(""), expected_if: str = typer.Option(""), observability: str = typer.Option("unknown"), observability_rationale: str = typer.Option(""), search_performed: str = typer.Option("")):
    command="langley evidence add"
    def run():
        s=store(); item=EvidenceInput(label=label,kind=kind,details=details,credibility=credibility,importance=importance,source={"citation":source},expected_if=[x for x in expected_if.split(",") if x],observability=observability,observability_rationale=observability_rationale,search_performed=search_performed).model_dump(); item.update({"id":s.next_id("evidence","e"),"status":"active","created_at":now(),"created_by":runtime.actor.model_dump()}); mutate("evidence.created",item,command); finish(command,item)
    guard(command,run)


@evidence_app.command("list")
def evidence_list():
    command="langley evidence list"; guard(command,lambda:finish(command,{"evidence":list(store().state()["evidence"].values())}))


@evidence_app.command("show")
def evidence_show(identifier: str):
    command="langley evidence show"
    def run():
        item=store().state()["evidence"].get(identifier)
        if not item: raise LangleyError("NOT_FOUND",f"Unknown evidence {identifier}.")
        finish(command,item)
    guard(command,run)


@evidence_app.command("import")
def evidence_import(input_path: Path=typer.Option(...,"--input")):
    command="langley evidence import"
    def run():
        s=store(); raw=read_input(input_path); values=raw if isinstance(raw,list) else raw.get("evidence",[]); ids=[]
        for value in values:
            model=EvidenceInput.model_validate(value); item={"id":s.next_id("evidence","e"),**model.model_dump(),"status":"active","created_at":now(),"created_by":runtime.actor.model_dump(),"import_hash":digest(raw)}; mutate("evidence.created",item,command); ids.append(item["id"])
        finish(command,{"imported":ids})
    guard(command,run)


@evidence_app.command("archive")
def evidence_archive(identifier: str,reason: str=typer.Option(...)):
    command="langley evidence archive"
    def run():
        if identifier not in store().state()["evidence"]: raise LangleyError("NOT_FOUND",f"Unknown evidence {identifier}.")
        changes={"status":"archived","archived_at":now(),"archive_reason":reason}; mutate("evidence.updated",{"id":identifier,"changes":changes},command); finish(command,{"id":identifier,**changes})
    guard(command,run)


@matrix_app.command("next")
def matrix_next():
    command="langley matrix next"
    def run():
        state=store().state(); missing=gaps(state)
        if not missing: finish(command,{"complete":True}); return
        eid=missing[0]["evidence_id"]; hs=[h for h in state["hypotheses"].values() if h["status"]=="active"]
        finish(command,{"evidence":state["evidence"][eid],"hypotheses":hs,"expected_input":{"assessments":[{"hypothesis_id":h["id"],"rating":"not_assessed","strength":None,"rationale":"<required>"} for h in hs]}})
    guard(command,run)


@matrix_app.command("set")
def matrix_set(evidence: str = typer.Option(...), input_path: Path = typer.Option(...,"--input")):
    command="langley matrix set"
    def run():
        s=store(); state=s.state(); row=MatrixRowInput.model_validate(read_input(input_path)); active={h["id"] for h in state["hypotheses"].values() if h["status"]=="active"}
        if evidence not in state["evidence"]: raise LangleyError("NOT_FOUND",f"Unknown evidence {evidence}.")
        supplied={x.hypothesis_id for x in row.assessments}
        if supplied != active: raise LangleyError("MATRIX_ROW_INCOMPLETE","Row must assess every active hypothesis.",context={"missing":sorted(active-supplied),"unexpected":sorted(supplied-active)})
        for cell in row.assessments:
            payload={"evidence_id":evidence,**cell.model_dump(),"assessed_at":now(),"assessed_by":runtime.actor.model_dump()}; mutate("matrix.assessed",payload,command)
        finish(command,{"evidence_id":evidence,"assessed":len(row.assessments)})
    guard(command,run)


@matrix_app.command("set-cell")
def matrix_set_cell(evidence: str=typer.Option(...),hypothesis: str=typer.Option(...),rating: str=typer.Option(...),rationale: str=typer.Option(...),strength: int|None=typer.Option(None)):
    command="langley matrix set-cell"
    def run():
        state=store().state()
        if evidence not in state["evidence"] or hypothesis not in state["hypotheses"]: raise LangleyError("NOT_FOUND","Unknown evidence or hypothesis.")
        cell=CellInput(hypothesis_id=hypothesis,rating=rating,strength=strength,rationale=rationale); payload={"evidence_id":evidence,**cell.model_dump(),"assessed_at":now(),"assessed_by":runtime.actor.model_dump()}; mutate("matrix.assessed",payload,command); finish(command,payload)
    guard(command,run)


@matrix_app.command("gaps")
def matrix_gaps():
    command="langley matrix gaps"; guard(command,lambda:finish(command,{"gaps":gaps(store().state())}))


@matrix_app.command("analyze")
def matrix_analyze():
    command="langley matrix analyze"; guard(command,lambda:finish(command,analyze(store().state())))


@matrix_app.command("show")
def matrix_show(format: str=typer.Option("json")):
    command="langley matrix show"
    def run():
        state=store().state(); hs=[h for h in state["hypotheses"].values() if h["status"]=="active"]; rows=[]
        for e in state["evidence"].values(): rows.append({"evidence_id":e["id"],"label":e["label"],"assessments":{h["id"]:state["matrix"].get(f'{e["id"]}:{h["id"]}',{"rating":"not_assessed"}) for h in hs}})
        finish(command,{"format":format,"hypotheses":hs,"rows":rows})
    guard(command,run)


@conclusion_app.command("draft")
def conclusion_draft(input_path: Path=typer.Option(...,"--input")):
    command="langley conclusion draft"
    def run():
        s=store(); state=s.state(); model=ConclusionInput.model_validate(read_input(input_path)); active={h["id"] for h in state["hypotheses"].values() if h["status"]=="active"}; covered={x.get("hypothesis_id") for x in model.hypotheses}
        if active != covered: raise LangleyError("CONCLUSION_INCOMPLETE","Conclusion must discuss every active hypothesis.",context={"missing":sorted(active-covered),"unexpected":sorted(covered-active)})
        for old in state["conclusions"].values():
            if old["status"]=="current": mutate("conclusion.updated",{"id":old["id"],"changes":{"status":"superseded"}},command)
        item=model.model_dump(); item.update({"id":s.next_id("conclusions","c"),"status":"current","created_at":now(),"source_revision":s.revision}); mutate("conclusion.created",item,command); finish(command,item)
    guard(command,run)


@conclusion_app.command("show")
def conclusion_show(identifier: str|None=None):
    command="langley conclusion show"
    def run():
        values=store().state()["conclusions"]
        if identifier: item=values.get(identifier)
        else: item=next((x for x in reversed(list(values.values())) if x["status"]=="current"),None)
        if not item: raise LangleyError("NOT_FOUND","No matching conclusion.")
        finish(command,item)
    guard(command,run)


@sensitivity_app.command("suggest")
def sensitivity_suggest():
    command="langley sensitivity suggest"
    def run():
        state=store().state(); a=analyze(state); diagnostic={x["evidence_id"]:x["diagnosticity"] for x in a["evidence"]}; candidates=[{"evidence_id":e["id"],"diagnosticity":diagnostic.get(e["id"]),"credibility":e["credibility"],"importance":e["importance"],"deception_risk":e["deception_risk"]} for e in state["evidence"].values() if diagnostic.get(e["id"]) in {"high","medium"} or e["importance"]=="high" or e["deception_risk"]=="high"]; finish(command,{"candidates":candidates})
    guard(command,run)


@sensitivity_app.command("run")
def sensitivity_run(name: str=typer.Option(...),input_path: Path=typer.Option(...,"--input")):
    command="langley sensitivity run"
    def run():
        s=store(); model=SensitivityInput.model_validate(read_input(input_path)); item={"id":s.next_id("sensitivities","s"),"name":name,**model.model_dump(),"created_at":now(),"source_revision":s.revision}; mutate("sensitivity.created",item,command); finish(command,item)
    guard(command,run)


@sensitivity_app.command("list")
def sensitivity_list():
    command="langley sensitivity list"; guard(command,lambda:finish(command,{"sensitivities":list(store().state()["sensitivities"].values())}))


@sensitivity_app.command("show")
def sensitivity_show(identifier: str):
    command="langley sensitivity show"
    def run():
        item=store().state()["sensitivities"].get(identifier)
        if not item: raise LangleyError("NOT_FOUND",f"Unknown sensitivity test {identifier}.")
        finish(command,item)
    guard(command,run)


@indicator_app.command("add")
def indicator_add(input_path: Path=typer.Option(...,"--input")):
    command="langley indicator add"
    def run():
        s=store(); model=IndicatorInput.model_validate(read_input(input_path)); item={"id":s.next_id("indicators","i"),**model.model_dump(),"status":"watching","created_at":now()}; mutate("indicator.created",item,command); finish(command,item)
    guard(command,run)


@indicator_app.command("list")
def indicator_list():
    command="langley indicator list"; guard(command,lambda:finish(command,{"indicators":list(store().state()["indicators"].values())}))


@indicator_app.command("observe")
def indicator_observe(identifier: str, details: str=typer.Option(...), source: str=typer.Option("")):
    command="langley indicator observe"
    def run():
        if identifier not in store().state()["indicators"]: raise LangleyError("NOT_FOUND",f"Unknown indicator {identifier}.")
        changes={"status":"observed","observed_at":now(),"observation_details":details,"observation_source":source}; mutate("indicator.updated",{"id":identifier,"changes":changes},command); finish(command,{"id":identifier,**changes})
    guard(command,run)


@app.command("history")
def history(entity: str|None=typer.Option(None),since_revision: int=typer.Option(0)):
    command="langley history"
    def run():
        events=[e for e in store().events() if e["revision"]>since_revision and (not entity or entity in json.dumps(e["payload"]))]; finish(command,{"events":events})
    guard(command,run)


@report_app.command("generate")
def report_generate(name: str=typer.Option("latest"),draft: bool=typer.Option(False)):
    command="langley report generate"
    def run():
        s=store(); state=s.state(); issues=validate(s); errors=[x for x in issues if x.get("severity")=="error"]
        if errors and not draft: raise LangleyError("NOT_REPORT_READY","Analysis has blocking validation issues.",context={"issues":errors},hint="Run `langley validate`, or use `--draft` for an incomplete report.")
        directory=s.dir/"reports"/name
        if directory.exists(): raise LangleyError("ALREADY_EXISTS",f"Report {name} already exists.")
        directory.mkdir(parents=True); a=analyze(state); project=s.project(); current=next((x for x in reversed(list(state["conclusions"].values())) if x["status"]=="current"),None)
        lines=[f'# {project["title"]}',"",f'**Question:** {project["question"]}',"",f'**Revision:** {s.revision}',""]
        if draft: lines += ["> **DRAFT:** This report has unresolved validation issues.",""]
        if current: lines += ["## Assessment","",current["summary"],"",f'Confidence: {current["confidence"]}',"",f'Residual uncertainty: {current["residual_uncertainty"]}',""]
        lines += ["## Hypotheses",""]+[f'- **{h["id"]} — {h["name"]}:** {h["description"]}' for h in state["hypotheses"].values() if h["status"]=="active"]
        lines += ["","## Inconsistency summary",""]+[f'- **{row["hypothesis_id"]}:** raw {row["raw_inconsistency"]}; adjusted {row["adjusted_inconsistency"]}; heuristic rank {row["heuristic_rank"]}' for row in a["hypotheses"]]
        lines += ["","> Scores are heuristic aids, not probabilities or verdicts.","","## Sensitivity tests",""]+[f'- **{x["id"]} — {x["name"]}:** {x["result"].get("summary",x["reason"])}' for x in state["sensitivities"].values()]
        lines += ["","## Indicators",""]+[f'- **{i["id"]}:** {i["description"]}' for i in state["indicators"].values()]
        report="\n".join(lines)+"\n"; (directory/"report.md").write_text(report,encoding="utf-8"); write_json(directory/"analysis.json",{"project":project,"revision":s.revision,"state":state,"analysis":a,"validation_issues":issues})
        with (directory/"matrix.csv").open("w",newline="",encoding="utf-8") as handle:
            writer=csv.writer(handle); hs=[h for h in state["hypotheses"].values() if h["status"]=="active"]; writer.writerow(["evidence_id","evidence",*[h["id"] for h in hs]])
            for e in state["evidence"].values(): writer.writerow([e["id"],e["label"],*[state["matrix"].get(f'{e["id"]}:{h["id"]}',{}).get("rating","not_assessed") for h in hs]])
        files={p.name:digest(p.read_bytes()) for p in directory.iterdir()}; write_json(directory/"manifest.json",{"schema_version":1,"project_id":project["id"],"revision":s.revision,"created_at":now(),"files":files}); finish(command,{"name":name,"paths":{p.name:str(p) for p in directory.iterdir()}})
    guard(command,run)


@report_app.command("list")
def report_list():
    command="langley report list"
    def run():
        s=store(); s.require(); finish(command,{"reports":[p.name for p in sorted((s.dir/"reports").iterdir()) if p.is_dir()]})
    guard(command,run)


@report_app.command("show")
def report_show(name: str="latest"):
    command="langley report show"
    def run():
        path=store().dir/"reports"/name/"report.md"
        if not path.is_file(): raise LangleyError("NOT_FOUND",f"Unknown report {name}.")
        finish(command,{"name":name,"markdown":path.read_text(encoding="utf-8"),"path":str(path)})
    guard(command,run)


@job_generate_app.command("hypotheses")
def job_hypotheses(agents: Path|None=typer.Option(None),iterations: int=typer.Option(1),output: Path|None=typer.Option(None)):
    generate_job("hypotheses",None,agents,iterations,output)

@job_generate_app.command("evidence")
def job_evidence(agents: Path|None=typer.Option(None),iterations: int=typer.Option(1),output: Path|None=typer.Option(None)):
    generate_job("evidence",None,agents,iterations,output)

@job_generate_app.command("matrix-row")
def job_matrix_row(evidence: str=typer.Option(...),agents: Path|None=typer.Option(None),iterations: int=typer.Option(1),output: Path|None=typer.Option(None)):
    generate_job("matrix-row",evidence,agents,iterations,output)

@job_generate_app.command("red-team")
def job_red_team(agents: Path|None=typer.Option(None),iterations: int=typer.Option(1),output: Path|None=typer.Option(None)):
    generate_job("red-team",None,agents,iterations,output)

@job_generate_app.command("indicators")
def job_indicators(agents: Path|None=typer.Option(None),iterations: int=typer.Option(1),output: Path|None=typer.Option(None)):
    generate_job("indicators",None,agents,iterations,output)


def generate_job(kind: str,target: str|None,agents: Path|None,iterations: int,output: Path|None):
    command=f"langley job generate {kind}"
    def run():
        from . import edsl_jobs
        s=store(); state=s.state(); jid=s.next_id("jobs","j"); out=output or s.dir/"jobs"/jid/"jobs.ep"
        out = (s.root / out).resolve() if not out.is_absolute() else out.resolve()
        jobs=edsl_jobs.build(kind,s.project(),state,jid,target=target,agents_path=agents)
        if iterations>1: jobs.run_config.parameters.n=iterations
        edsl_jobs.save(jobs,out); item={"id":jid,"job_type":kind,"project_id":s.project()["id"],"project_revision":state["revision"],"input_hash":analytical_hash(state),"jobs_path":str(out),"jobs_hash":digest(out.read_bytes()),"question_names":list(jobs.survey.question_names),"target":{"id":target} if target else {},"status":"generated","created_at":now()}; mutate("job.created",item,command)
        result=out.with_name("results.ep"); handoff=[step("Inspect EDSL job",["ep","inspect",str(out)],"Inspect prompts and context.",False),step("Estimate EDSL cost",["ep","jobs","cost",str(out)],"Estimate cost before execution.",False),step("Run EDSL job",["ep","run",str(out),"--model","<model-name>","--output",str(result)],"This may incur cost and transmit project data.",False,True),step("Ingest EDSL results",["langley","job","ingest",jid,"--from",str(result)],"Create reviewable proposals.")]; finish(command,item,next_steps=handoff)
    guard(command,run)


@job_app.command("list")
def job_list():
    command="langley job list"; guard(command,lambda:finish(command,{"jobs":list(store().state()["jobs"].values())}))


@job_app.command("show")
def job_show(identifier: str):
    command="langley job show"
    def run():
        item=store().state()["jobs"].get(identifier)
        if not item: raise LangleyError("NOT_FOUND",f"Unknown job {identifier}.")
        finish(command,item)
    guard(command,run)


@job_app.command("ingest")
def job_ingest(identifier: str,from_path: Path=typer.Option(...,"--from")):
    command="langley job ingest"
    def run():
        from . import edsl_jobs
        s=store(); state=s.state(); job=state["jobs"].get(identifier)
        if not job: raise LangleyError("NOT_FOUND",f"Unknown job {identifier}.")
        result_hash=digest(from_path.read_bytes())
        existing=[p for p in state["proposals"].values() if p.get("results_hash")==result_hash]
        if existing: finish(command,{"job_id":identifier,"idempotent":True,"proposal_ids":[p["id"] for p in existing]}); return
        results=edsl_jobs.load_results(from_path); rows=results.select("*").to_dicts(remove_prefix=True); created=[]
        for index,row in enumerate(rows):
            scenario={k.removeprefix("scenario."):v for k,v in row.items() if k.startswith("scenario.")}
            scenario.update({k:row[k] for k in ("langley_project_id","langley_job_id","langley_revision","job_type","target_id") if k in row})
            if scenario.get("langley_project_id") != s.project()["id"] or scenario.get("langley_job_id") != identifier or scenario.get("job_type") != job["job_type"]: raise LangleyError("JOB_CONTEXT_MISMATCH","Results context does not match the job.",context=scenario)
            answers={k.removeprefix("answer."):v for k,v in row.items() if k.startswith("answer.")}
            if not answers: answers={k:v for k,v in row.items() if k in job["question_names"]}
            for proposal_kind,target,payload in proposal_payloads(job,answers):
                pid=s.next_id("proposals","p"); item={"id":pid,"kind":proposal_kind,"job_id":identifier,"result_index":index,"target":target or job["target"],"payload":payload,"model_provenance":{"model":row.get("model.model",row.get("model")),"agent_name":row.get("agent.name",row.get("agent_name")),"iteration":row.get("iteration")},"results_hash":result_hash,"source_revision":job["project_revision"],"status":"pending","created_at":now()}; mutate("proposal.created",item,command); created.append(pid)
        mutate("job.updated",{"id":identifier,"changes":{"status":"ingested","results_path":str(from_path),"results_hash":result_hash}},command); finish(command,{"job_id":identifier,"proposal_ids":created})
    guard(command,run)


@proposal_app.command("list")
def proposal_list(job: str|None=typer.Option(None),status: str|None=typer.Option(None)):
    command="langley proposal list"
    def run():
        values=list(store().state()["proposals"].values()); finish(command,{"proposals":[p for p in values if (not job or p["job_id"]==job) and (not status or p["status"]==status)]})
    guard(command,run)


@proposal_app.command("show")
def proposal_show(identifier: str):
    command="langley proposal show"
    def run():
        item=store().state()["proposals"].get(identifier)
        if not item: raise LangleyError("NOT_FOUND",f"Unknown proposal {identifier}.")
        finish(command,item)
    guard(command,run)


@proposal_app.command("compare")
def proposal_compare(job: str=typer.Option(...)):
    command="langley proposal compare"
    def run():
        values=[p for p in store().state()["proposals"].values() if p["job_id"]==job]; finish(command,{"job_id":job,"count":len(values),"proposals":values})
    guard(command,run)


@proposal_app.command("reject")
def proposal_reject(identifier: str,reason: str=typer.Option(...)):
    review_proposal(identifier,"rejected",reason,False)


@proposal_app.command("accept")
def proposal_accept(identifier: str,reason: str=typer.Option(...),accept_stale: bool=typer.Option(False)):
    review_proposal(identifier,"accepted",reason,accept_stale)


def review_proposal(identifier: str,status: str,reason: str,accept_stale: bool):
    command=f"langley proposal {status.removesuffix('ed')}"
    def run():
        s=store(); item=s.state()["proposals"].get(identifier)
        if not item: raise LangleyError("NOT_FOUND",f"Unknown proposal {identifier}.")
        if item["status"]!="pending": raise LangleyError("INVALID_STATE","Proposal is not pending.")
        if status=="accepted" and analytical_hash(s.state(),item["job_id"]) != s.state()["jobs"][item["job_id"]]["input_hash"] and not accept_stale: raise LangleyError("STALE_PROPOSAL","Analytical state changed after job generation.",hint="Review changes and use --accept-stale with a rationale if appropriate.")
        materialized=None
        if status=="accepted":
            payload=item["payload"]
            if item["kind"]=="hypothesis":
                model=HypothesisInput.model_validate(payload); materialized={"id":s.next_id("hypotheses","h"),**model.model_dump(),"status":"active","created_at":now(),"created_by":runtime.actor.model_dump(),"archived_at":None,"archive_reason":None,"superseded_by":[],"proposal_id":identifier}; mutate("hypothesis.created",materialized,command)
            elif item["kind"]=="evidence":
                model=EvidenceInput.model_validate(payload); materialized={"id":s.next_id("evidence","e"),**model.model_dump(),"status":"active","created_at":now(),"created_by":runtime.actor.model_dump(),"proposal_id":identifier}; mutate("evidence.created",materialized,command)
            elif item["kind"]=="matrix_assessment":
                target=item["target"]; strength=payload.get("strength"); rating=payload.get("rating")
                if rating in {"neutral","not_applicable"}: strength=None
                model=CellInput(hypothesis_id=target["hypothesis_id"],rating=rating,strength=strength,rationale=payload.get("rationale","EDSL proposal accepted"),interpretation="; ".join(payload.get("assumptions",[]))); materialized={"evidence_id":target["evidence_id"],**model.model_dump(),"assessed_at":now(),"assessed_by":runtime.actor.model_dump(),"proposal_id":identifier}; mutate("matrix.assessed",materialized,command)
            elif item["kind"]=="indicator":
                model=IndicatorInput.model_validate(payload); materialized={"id":s.next_id("indicators","i"),**model.model_dump(),"status":"watching","created_at":now(),"proposal_id":identifier}; mutate("indicator.created",materialized,command)
        mutate("proposal.reviewed",{"id":identifier,"status":status,"reason":reason,"reviewed_at":now()},command); finish(command,{"id":identifier,"status":status,"materialized":materialized})
    guard(command,run)


DOCS = {
    "overview": "Langley implements Heuer's eight-step Analysis of Competing Hypotheses method.",
    "workflow": "Run `langley next`, perform its action, and repeat. Compare evidence row-by-row before drawing conclusions.",
    "matrix": "Assess every evidence/hypothesis pair as consistent, inconsistent, neutral, or not applicable. Seek disconfirmation.",
    "scoring": "Raw and adjusted inconsistency scores are transparent heuristics, never probabilities or verdicts.",
    "edsl": "Generate model-free Jobs, inspect and cost them, run with `ep run` after approval, ingest Results, then review proposals.",
    "proposal-review": "EDSL answers remain immutable pending proposals until explicitly accepted or rejected with a rationale.",
    "troubleshooting": "Run `langley status` and `langley validate`; every structured error includes a recovery hint.",
}


@docs_app.command("list")
def docs_list(): finish("langley docs list", {"topics": sorted(DOCS)})


@docs_app.command("show")
def docs_show(topic: str):
    command="langley docs show"
    if topic not in DOCS: fail(command,argv(command),LangleyError("NOT_FOUND",f"Unknown documentation topic {topic}."),root=store().root,human=runtime.human)
    finish(command,{"topic":topic,"markdown":DOCS[topic]})


@docs_app.command("search")
def docs_search(query: str):
    finish("langley docs search", {"query":query,"matches":[{"topic":k,"excerpt":v} for k,v in DOCS.items() if query.lower() in (k+" "+v).lower()]})


@app.command("validate")
def validate_command(strict: bool=typer.Option(False)):
    command="langley validate"
    def run():
        issues=validate(store()); warnings=[x for x in issues if x.get("severity")!="error"]; errors=[x for x in issues if x.get("severity")=="error" or x.get("code")=="EVENT_CHAIN_INVALID"]
        payload=envelope(command,argv(command),data={"valid":not errors,"issues":issues},root=store().root,revision=store().revision,warnings=warnings,errors=errors if strict else []); emit(payload,runtime.human)
        if strict and errors: raise typer.Exit(1)
    guard(command,run)


def main(): app()
