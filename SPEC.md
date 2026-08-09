# langley — Analysis of Competing Hypotheses CLI

**Version:** 0.1  
**Status:** Draft for review  
**Method source:** Richards J. Heuer Jr., *Psychology of Intelligence Analysis*, Chapter 8

## 1. Purpose

`langley` is a Python CLI for conducting and auditing an Analysis of Competing
Hypotheses (ACH). It is designed primarily for use by an AI agent working with a
human analyst, while remaining usable directly by a human.

The tool turns Heuer's eight-step method into a durable, inspectable workflow. It
stores hypotheses, evidence, matrix judgments, tentative conclusions, sensitivity
tests, and future indicators in a local project. It computes transparent summaries
that help an analyst compare hypotheses, but it does not decide what is true.

The name follows the repository's convention of naming structured-analysis tools
after people or places associated with their method and history.

## 2. Goals

- Make simultaneous comparison of competing hypotheses easier than serially
  confirming a favored hypothesis.
- Preserve reasonable but unproven hypotheses until they are explicitly rejected
  with a rationale.
- Force each item of evidence to be assessed against every active hypothesis.
- Surface diagnostic evidence, inconsistent evidence, assumptions, missing
  evidence, source weaknesses, and possible denial or deception.
- Make sensitivity analysis reproducible rather than an informal afterthought.
- Produce conclusions that compare all hypotheses and state what could change the
  assessment.
- Leave a complete audit trail of who or what made each judgment and when.
- Give an agent one safe, machine-readable next action at every workflow state.
- Build portable EDSL Jobs for hypothesis generation, evidence elicitation, matrix
  assessment, red-teaming, and indicators, with explicit proposal review.

## 3. Non-goals

`langley` does not:

- Fetch, search for, extract, or independently verify evidence.
- Ask an LLM to generate hypotheses or make matrix judgments inside ordinary CRUD
  commands; AI assistance uses explicit EDSL Jobs and proposal review.
- Treat consistency as proof, or absence of reporting as evidence of absence.
- Compute Bayesian posteriors from qualitative ACH judgments.
- Select the winning hypothesis automatically.
- Replace source evaluation, domain expertise, peer review, or human judgment.
- Hide uncertainty behind a single composite score.

AI-assisted work is supported through explicit, inspectable EDSL job generation and
result ingestion. Core ACH state management remains deterministic: generated answers
enter the project as proposals and never silently become accepted analytical judgments.

## 4. Method model

The canonical workflow follows Heuer's eight steps:

1. **Generate hypotheses.** Identify all reasonable alternatives before evaluating
   them.
2. **Collect evidence and arguments.** Include facts, assumptions, deductions,
   arguments, and expected-but-absent observations.
3. **Build the matrix.** For each evidence row, assess its relationship to every
   hypothesis and identify diagnostic evidence.
4. **Refine.** Add, split, merge, reword, or archive hypotheses; archive
   non-diagnostic evidence without erasing it.
5. **Assess hypotheses.** Seek disconfirming evidence and record tentative relative
   likelihoods.
6. **Test sensitivity.** Challenge linchpin evidence and assumptions, including
   source problems, alternative interpretations, and denial or deception.
7. **Report conclusions.** Discuss the relative likelihood of every active
   hypothesis and why less likely alternatives were not selected.
8. **Define indicators.** Record observable milestones that would cause the
   assessment to change.

The CLI uses workflow phases rather than hard locks:

```text
hypotheses -> evidence -> matrix -> refinement -> conclusion -> sensitivity
           -> indicators -> report-ready
```

Earlier records may be revised at any time. A revision can move the project back to
an earlier phase and mark downstream conclusions or reports stale.

## 5. Method invariants

The following rules are part of the product, not merely documentation:

1. At least two active hypotheses are required for an ACH matrix.
2. Archived hypotheses and evidence remain in the audit trail.
3. Archiving an unproven hypothesis requires a rationale; `langley` warns when no
   inconsistent evidence is cited.
4. Every active evidence/hypothesis pair must have an explicit matrix assessment
   before the matrix is complete. `not_assessed` is distinct from `not_applicable`.
5. Evidence is evaluated row-by-row across all hypotheses in the agent workflow.
6. Consistent evidence never counts as proof. The primary comparison summary is
   inconsistency-oriented.
7. A missing observation must record why it should have been observable if the
   hypothesis were true.
8. A conclusion must discuss every active hypothesis.
9. A report cannot be complete until critical evidence has been sensitivity-tested
   or the analyst records why no evidence is critical.
10. Computed scores are labeled heuristics and are always accompanied by their
    contributing cells.

## 6. Project and storage model

One directory is one analysis. Commands search upward from the current directory
for `.langley/`, unless `--project-dir` is supplied.

```text
<project>/
  .langley/
    project.json
    events/
      00000001.json
      00000002.json
      ...
    cache/
      state.json
    snapshots/
      <label>/
        manifest.json
        state.json
    jobs/
      <job-id>/
        jobs.ep
        manifest.json
        results.ep                   # present after result registration
    proposals/
      <proposal-id>.json
    reports/
      <report-id>/
        report.md
        matrix.csv
        analysis.json
        manifest.json
    docs/
      overrides/
  README.md                         # optional project summary
```

The append-only event log is the source of truth. `state.json` is a disposable
materialized cache. Each mutation appends one event with the command, timestamp,
actor metadata, prior event hash, payload, and resulting artifact hashes. This makes
revisions and agent actions auditable without requiring Git.

### `project.json`

```json
{
  "schema_version": 1,
  "id": "01J...",
  "title": "Cause of the service outage",
  "question": "Which explanation best accounts for the outage?",
  "scope": "Production systems, 2026-08-01 through 2026-08-03",
  "created_at": "2026-08-09T15:00:00Z",
  "created_by": {"type": "agent", "name": "codex"}
}
```

Entity IDs are stable, short, sequential identifiers: hypotheses `h001`, evidence
`e001`, conclusions `c001`, sensitivity tests `s001`, and indicators `i001`.
Display order is stored separately and may change without changing IDs.

## 7. Data schemas

All persisted records are validated with Pydantic on write and when rebuilding
state. Timestamps use UTC ISO 8601. Free-text fields support UTF-8 Markdown.

### 7.1 Hypothesis

```json
{
  "id": "h001",
  "name": "Database saturation",
  "description": "Connection exhaustion caused requests to queue and fail.",
  "status": "active",
  "provenance": "Proposed during initial brainstorming",
  "prior_view": "plausible",
  "created_at": "2026-08-09T15:05:00Z",
  "created_by": {"type": "agent", "name": "codex"},
  "archived_at": null,
  "archive_reason": null,
  "superseded_by": []
}
```

`status` is `active | archived | merged | split`. `prior_view` is optional,
qualitative, and preserved so the audit can reveal changes in belief. It is never
used in the inconsistency score.

### 7.2 Evidence

“Evidence” is intentionally broad, matching Heuer's use of the term.

```json
{
  "id": "e001",
  "label": "Connection count reached configured maximum",
  "details": "Metric was at 100% from 14:02 to 14:19 UTC.",
  "kind": "observation",
  "status": "active",
  "source": {
    "citation": "metrics://prod/db/connections?at=2026-08-01T14:02Z",
    "publisher": "production telemetry",
    "observed_at": "2026-08-01T14:02:00Z",
    "accessed_at": "2026-08-09T15:10:00Z"
  },
  "credibility": "high",
  "credibility_rationale": "Direct system metric with complete coverage.",
  "importance": "high",
  "deception_risk": "low",
  "tags": ["database", "telemetry"],
  "created_at": "2026-08-09T15:10:00Z",
  "created_by": {"type": "agent", "name": "codex"}
}
```

`kind` is one of:

- `observation`: a reported or directly observed fact;
- `argument`: a logical argument or deduction;
- `assumption`: a premise influencing the assessment;
- `absence`: an expected observation that is missing;
- `context`: background information included for completeness.

For `absence`, these additional fields are required:

```json
{
  "expected_if": ["h002"],
  "observability": "high",
  "observability_rationale": "The action always emits an audited deployment event.",
  "search_performed": "Queried deployment audit log for the full interval."
}
```

`credibility`, `importance`, `deception_risk`, and `observability` use
`low | medium | high | unknown`. Their rationales are required when the value is
not `unknown`.

### 7.3 Matrix assessment

Each active evidence/hypothesis pair has one current assessment:

```json
{
  "evidence_id": "e001",
  "hypothesis_id": "h001",
  "rating": "inconsistent",
  "strength": 2,
  "rationale": "Saturation should raise, not reduce, active connections.",
  "interpretation": "Assumes the metric is not delayed.",
  "assessed_at": "2026-08-09T15:20:00Z",
  "assessed_by": {"type": "agent", "name": "codex"}
}
```

`rating` is:

- `consistent`: expected or readily explained if the hypothesis is true;
- `inconsistent`: surprising or difficult to explain if the hypothesis is true;
- `neutral`: applicable but does not distinguish this hypothesis;
- `not_applicable`: no meaningful relationship;
- `not_assessed`: explicit placeholder only, never matrix-complete.

`strength` is `1 | 2 | 3` and is required for `consistent` and `inconsistent`.
It captures the strength of the relationship, not confidence that the evidence is
true. Every non-placeholder cell requires a rationale.

### 7.4 Derived diagnosticity

Diagnosticity is computed per evidence row from variation among its active matrix
assessments. An item assessed identically for every hypothesis has no diagnostic
value. The CLI reports:

- the distribution of ratings across hypotheses;
- `diagnosticity: none | low | medium | high`;
- which hypothesis pairs the evidence distinguishes;
- whether the result depends on a single assessment.

The exact deterministic rubric is versioned in `analysis.json` and documented by
`langley docs show scoring`. Users may override the derived label with an explicit
label and rationale, but both derived and analyst labels remain visible.

### 7.5 Tentative conclusion

```json
{
  "id": "c001",
  "status": "current",
  "summary": "Database saturation is currently the least inconsistent explanation.",
  "confidence": "moderate",
  "hypotheses": [
    {
      "hypothesis_id": "h001",
      "rank": 1,
      "likelihood": "likely",
      "rationale": "Fewest material inconsistencies; depends on e004.",
      "rejection_basis": null
    },
    {
      "hypothesis_id": "h002",
      "rank": 2,
      "likelihood": "unlikely",
      "rationale": "Conflicts with e003 and e006.",
      "rejection_basis": ["e003", "e006"]
    }
  ],
  "critical_evidence_ids": ["e004", "e006"],
  "critical_assumptions": ["Telemetry timestamps are correctly synchronized."],
  "residual_uncertainty": "A shared upstream failure could mimic both patterns.",
  "created_at": "2026-08-09T16:00:00Z"
}
```

`likelihood` uses `very_likely | likely | roughly_even | unlikely | very_unlikely |
insufficient_evidence`. These are analyst judgments, not score mappings. Numerical
probabilities are optional and must be explicitly supplied by the analyst; the tool
never derives them from matrix scores.

### 7.6 Sensitivity test

```json
{
  "id": "s001",
  "name": "Telemetry metric is misleading",
  "reason": "e004 is a linchpin and may lag during failover.",
  "changes": [
    {"operation": "exclude_evidence", "evidence_id": "e004"},
    {
      "operation": "replace_cell",
      "evidence_id": "e004",
      "hypothesis_id": "h002",
      "rating": "neutral",
      "strength": null
    }
  ],
  "result": {
    "ranking_changed": true,
    "previous_leader": "h001",
    "new_leader": null,
    "summary": "Without e004 the two leading hypotheses are not distinguishable."
  },
  "created_at": "2026-08-09T16:15:00Z"
}
```

Supported operations are `exclude_evidence`, `change_credibility`, `replace_cell`,
and `activate_hypothesis`. A test is a non-mutating scenario over a recorded state
revision. Its narrative result is supplied by the analyst; Langley also includes a
deterministic before/after score comparison.

### 7.7 Indicator

```json
{
  "id": "i001",
  "description": "Connection utilization remains below 60% while failures recur.",
  "observable_in": "Production database telemetry",
  "supports": ["h002"],
  "weakens": ["h001"],
  "threshold": "Observed during any recurrence lasting at least five minutes",
  "collection_owner": "site reliability team",
  "review_by": "2026-09-01",
  "status": "watching"
}
```

Indicator status is `watching | observed | expired | retired`. Observing an
indicator appends an event and marks the current conclusion stale; it does not
silently alter the matrix.

### 7.8 EDSL job and proposal

Every generated EDSL job has a Langley manifest alongside its portable package:

```json
{
  "schema_version": 1,
  "id": "j001",
  "job_type": "matrix-row",
  "project_id": "01J...",
  "project_revision": 17,
  "input_hash": "sha256:...",
  "jobs_path": ".langley/jobs/j001/jobs.ep",
  "jobs_hash": "sha256:...",
  "question_names": ["assess_h001", "assess_h002", "assess_h003"],
  "target": {"evidence_id": "e001"},
  "created_at": "2026-08-09T15:30:00Z",
  "created_by": {"type": "agent", "name": "codex"},
  "status": "generated"
}
```

Imported EDSL answers become proposals:

```json
{
  "id": "p001",
  "kind": "matrix_assessment",
  "job_id": "j001",
  "result_index": 0,
  "target": {"evidence_id": "e001", "hypothesis_id": "h002"},
  "payload": {
    "rating": "inconsistent",
    "strength": 2,
    "rationale": "The observation would be unusual if h002 were true.",
    "assumptions": ["Telemetry timestamps are reliable."]
  },
  "model_provenance": {
    "model": "provider/model-name",
    "agent_name": "langley_matrix_critic",
    "iteration": 0
  },
  "status": "pending",
  "reviewed_at": null,
  "review_reason": null
}
```

Proposal status is `pending | accepted | rejected | superseded`. Accepting a proposal
creates the corresponding normal entity or matrix event and records the proposal ID.
The original model answer remains immutable. A proposal created from an older project
revision is `stale`; it may be reviewed but cannot be accepted without an explicit
`--accept-stale` acknowledgement and rationale.

## 8. Built-in EDSL integration

### 8.1 Execution boundary

Langley builds portable, model-free EDSL `Jobs` packages. EDSL's `ep` CLI owns model
selection, cost estimation, authentication, and execution:

```bash
langley job generate hypotheses --output .langley/jobs/j001/jobs.ep
ep inspect .langley/jobs/j001/jobs.ep
ep jobs cost .langley/jobs/j001/jobs.ep
ep run .langley/jobs/j001/jobs.ep --model <model-name> \
  --output .langley/jobs/j001/results.ep
langley job ingest j001 --from .langley/jobs/j001/results.ep
langley proposal review --job j001
```

`job generate` and `job ingest` are local operations and make no model calls.
Langley's returned handoff marks `ep run` as `requires_user_approval: true` because it
may incur cost and transmit project content. Langley never selects a default model or
runs `ep` as a subprocess.

Both Jobs and Results are retained and hashed. The Jobs package records the exact
survey, analyst personas, scenarios, and project context. The Results package records
answers and EDSL model provenance.

### 8.2 Supported v0.1 job types

#### `hypotheses`

Generate diverse, mutually distinguishable candidate explanations or outcomes. The
job includes the focal question, scope, existing hypotheses, and instructions to keep
unproven-but-plausible alternatives alive. Multiple analyst personas may be supplied
with `--agents agents.ep`; otherwise Langley creates a small built-in `AgentList` with
different analytic perspectives. Answers use `QuestionList` or `QuestionDict` and
become hypothesis proposals.

#### `evidence`

For each selected hypothesis, ask what should and should not be observable if it were
true, while distinguishing observations, arguments, assumptions, and absences. Model
claims are candidate collection requirements, not verified facts. Imported items are
marked `proposed` and require source/credibility completion before acceptance as
observations.

#### `matrix-row`

Assess one evidence item across every active hypothesis. The job contains the exact
row context and one structured question per hypothesis, but the prompt explicitly asks
the agent to compare across the full set. Answers must provide rating, optional
strength, rationale, assumptions, and confidence. They become matrix proposals.

#### `red-team`

Challenge a current conclusion, especially critical evidence and assumptions. The job
asks for alternate interpretations, source weaknesses, missing hypotheses, denial or
deception possibilities, and concrete sensitivity tests. Results never alter the
conclusion directly.

#### `indicators`

Suggest observable milestones that support or weaken specific hypotheses, including
thresholds and likely observation channels. Results become indicator proposals.

### 8.3 Portable EDSL construction

The adapter uses public EDSL objects:

- `Jobs`, `Survey`, `AgentList`, and `ScenarioList` for the portable run design;
- `QuestionDict` and `QuestionList` for schema-constrained answers;
- `jobs.git.save(path)` for `.jobs.ep` packages;
- `Results.git.load(path)` for `.ep` result ingestion;
- `Results.select(...).to_dicts(remove_prefix=True)` for normalized extraction.

Generated Jobs contain no models (`len(jobs.models) == 0`). A caller supplies a model
to `ep run`, or replaces the model component using normal EDSL CLI options.

Every execution scenario includes `langley_project_id`, `langley_revision`,
`langley_job_id`, `job_type`, and target entity IDs. Ingestion checks these values
instead of trusting filenames.

### 8.4 Result ingestion

`langley job ingest`:

1. Loads the package with `Results.git.load` (or `Results.from_dict` for documented
   JSON input).
2. Verifies project ID, job ID, job type, target IDs, question names, and source job
   hash.
3. Preserves the Results package and SHA-256 hash.
4. Validates every structured answer against the proposal schema.
5. Creates one immutable proposal per answer, including model, agent, iteration, and
   result index.
6. Reports malformed or missing answers without accepting partial analytical state.

By default, valid answers are ingested even when individual agents disagree. The
comparison command groups proposals by target and exposes rating counts, rationales,
and dissent. Agreement is a property of the elicited judgments, not evidence that a
hypothesis is true.

Re-ingesting the same Results hash is idempotent. A different Results package for the
same job is allowed as another run and receives a distinct run ID.

### 8.5 Proposal review

Proposal review is always separate from ingestion:

```bash
langley proposal list --job j001 --status pending
langley proposal compare --job j001
langley proposal show p001
langley proposal accept p001 --reason "Rationale is sound and source was checked."
langley proposal reject p002 --reason "Duplicates h003."
langley proposal accept --job j001 --input decisions.json
```

Batch acceptance requires an explicit decision for every proposal ID; there is no
`accept-all` command. Conflicting matrix proposals cannot both be accepted for the
same cell. The reviewer must choose one or enter a new assessment with a rationale.

### 8.6 Custom agents and iterations

`--agents PATH` accepts an EDSL `AgentList` `.ep` or JSON package. Langley records its
hash but does not modify it. `--iterations N` requests repeated independent judgments
through the generated Jobs design; default is one. Built-in personas and prompt
templates are versioned package data and their versions appear in the manifest.

No aggregation rule converts repeated answers into an accepted judgment. The compare
view may show counts and agreement rates when there are at least two responses.

## 9. Computed analysis

Langley computes transparent aids, never a verdict.

### Inconsistency summary

For each hypothesis, report:

- count and IDs of inconsistent cells by strength;
- a raw inconsistency total (`strength` summed);
- a credibility/importance-adjusted total using a documented ordinal rubric;
- the diagnostic evidence contributing to either total;
- unresolved and not-assessed cells.

The default display ranks by adjusted inconsistency ascending, but calls the first
item **least inconsistent**, never “true,” “proven,” or automatically “most likely.”
Ties are preserved.

### Score safeguards

- No normalization into probabilities.
- No hidden weights.
- Both raw and adjusted results are returned.
- Each score expands to the exact evidence and cell contributions.
- A conclusion may disagree with the score if the analyst records why.
- Changes to the scoring rubric require a schema/rubric version bump.

## 10. Agent interface

### 10.1 JSON envelope

JSON is the default for every command. Exactly one JSON object is written to stdout:

```json
{
  "schema_version": "1.0",
  "command": "langley matrix next",
  "argv": ["langley", "matrix", "next"],
  "status": "ok",
  "project_root": "/work/outage-analysis",
  "revision": 17,
  "data": {},
  "artifacts": {},
  "warnings": [],
  "errors": [],
  "next_steps": [
    {
      "id": "assess_e001",
      "label": "Assess e001 across all active hypotheses",
      "argv": ["langley", "matrix", "set", "--evidence", "e001", "--input", "e001.json"],
      "mutates_state": true,
      "requires_user_approval": false,
      "reason": "e001 is the next incomplete evidence row."
    }
  ]
}
```

Errors use the same envelope and a nonzero exit code. Each error contains `code`,
`message`, `context`, and `hint`. No logs or progress are written to stdout.
`--human` provides Rich-rendered output. `--jsonl-progress` writes structured
progress to stderr for long operations.

### 10.2 Canonical control loop

An agent begins or resumes with:

```bash
langley guide
langley next
```

`langley guide` returns stable operating rules, method boundaries, schema summaries,
and relevant embedded documentation. `langley next` is read-only and returns one
canonical action plus safe alternatives. `langley status` returns fuller project
state, completeness counts, stale artifacts, validation issues, and recommended
next steps.

The canonical action always permits a model-free manual workflow. When EDSL assistance
is useful, `next` may also return `langley job generate ...` as an alternative; it
never makes external execution the only way forward. After generation, `next` walks
the agent through inspect, cost, approval-gated execution, ingestion, and proposal
review. It does not claim that an `ep run` occurred merely because a Jobs file exists.

`next_steps[].argv` is always an argument array so an agent need not invoke a shell.
Every Langley argv includes the canonical absolute `--project-dir` selector and every
action includes an absolute `cwd`. Cross-tool actions such as `ep inspect`, cost, and
run also carry `cwd` and use absolute artifact paths. Callers execute argv directly
with the supplied cwd; they must not reconstruct commands or infer project context.
For convenience, human output may also show a shell-escaped command string derived
from argv.

### 10.3 Actor and provenance

Mutating commands accept:

```text
--actor-type human|agent|import
--actor-name <name>
--reason <text>
```

Defaults may come from `LANGLEY_ACTOR_TYPE` and `LANGLEY_ACTOR_NAME`. The event stores
both raw argv and normalized inputs. Imports store the source path and SHA-256 hash.

### 10.4 Concurrency

Every mutation accepts `--if-revision <n>`. A mismatch returns
`REVISION_CONFLICT` without writing. This prevents parallel agents from silently
overwriting one another. Project writes use a lock and atomic rename.

## 11. CLI reference

Global options:

```text
--project-dir PATH
--human
--jsonl-progress
--actor-type TYPE
--actor-name NAME
--if-revision N
--version
```

### Bootstrap and recovery

```text
langley init --title TEXT --question TEXT [--scope TEXT]
langley guide [--no-doc]
langley status
langley next
langley validate [--strict]
langley history [--entity ID] [--since-revision N]
langley snapshot save LABEL
langley snapshot list
langley snapshot restore LABEL --confirm LABEL
```

`init`, `guide`, `status`, `next`, and `validate` are the minimum complete
agent-facing surface. Outside a project, `next` recommends `init` rather than
failing.

### Hypotheses

```text
langley hypothesis add --name TEXT --description TEXT [--prior-view TEXT]
langley hypothesis import --input hypotheses.json
langley hypothesis list [--include-archived]
langley hypothesis show ID
langley hypothesis update ID [fields...]
langley hypothesis archive ID --reason TEXT [--citing e001,e002]
langley hypothesis merge ID ID --name TEXT --description TEXT --reason TEXT
langley hypothesis split ID --input replacements.json --reason TEXT
```

### Evidence

```text
langley evidence add --label TEXT --kind KIND [options...]
langley evidence import --input evidence.json
langley evidence list [--kind KIND] [--status STATUS]
langley evidence show ID
langley evidence update ID [fields...]
langley evidence archive ID --reason TEXT
```

Single-record commands accept flags for simple use. `--input` commands accept a
documented JSON object or array and are the preferred agent interface for batches
and rich text.

### Matrix and refinement

```text
langley matrix next [--limit N]
langley matrix set --evidence ID --input row.json
langley matrix set-cell --evidence ID --hypothesis ID --rating RATING \
  [--strength 1|2|3] --rationale TEXT
langley matrix import --input matrix.json [--replace]
langley matrix show [--format json|csv|markdown]
langley matrix analyze
langley matrix gaps
langley refine status
langley refine complete --reason TEXT
```

`matrix next` returns one entire evidence row with every active hypothesis, relevant
evidence metadata, prior assessments, and the exact JSON schema expected by
`matrix set`. This encourages the required row-wise comparison.

`matrix import --replace` and all restore operations require an explicit confirmation
flag in addition to user authorization because they can supersede current state.

### Conclusions and sensitivity

```text
langley conclusion draft --input conclusion.json
langley conclusion show [ID]
langley conclusion list
langley conclusion supersede ID --input conclusion.json --reason TEXT
langley sensitivity suggest
langley sensitivity run --name TEXT --input test.json
langley sensitivity list
langley sensitivity show ID
langley sensitivity compare ID [ID...]
```

`sensitivity suggest` is deterministic. It returns high-diagnosticity evidence,
high-importance assumptions, low-credibility linchpins, high-deception-risk items,
and cells whose reversal changes the heuristic ranking.

### EDSL jobs and proposals

```text
langley job generate hypotheses [--agents PATH] [--iterations N] [--output PATH]
langley job generate evidence [--hypothesis ID...] [--agents PATH] [--output PATH]
langley job generate matrix-row --evidence ID [--agents PATH] [--iterations N] [--output PATH]
langley job generate red-team [--conclusion ID] [--agents PATH] [--output PATH]
langley job generate indicators [--conclusion ID] [--agents PATH] [--output PATH]
langley job list [--status STATUS]
langley job show ID
langley job ingest ID --from results.ep
langley proposal list [--job ID] [--kind KIND] [--status STATUS]
langley proposal show ID
langley proposal compare [--job ID] [--target ID]
langley proposal accept ID --reason TEXT [--accept-stale]
langley proposal reject ID --reason TEXT
langley proposal accept --job ID --input decisions.json
```

Generation returns an execution handoff containing argument arrays for `ep inspect`,
`ep jobs cost`, `ep run`, and `langley job ingest`. Only `ep run` has
`requires_user_approval: true`.

### Indicators and report

```text
langley indicator add --input indicator.json
langley indicator list [--status STATUS]
langley indicator observe ID --details TEXT [--source TEXT]
langley indicator retire ID --reason TEXT
langley report generate [--name NAME]
langley report show [NAME]
langley report list
```

### Embedded docs

```text
langley docs list
langley docs show TOPIC
langley docs search QUERY
```

Required topics are `overview`, `workflow`, `hypotheses`, `evidence`, `matrix`,
`scoring`, `sensitivity`, `edsl`, `proposal-review`, `reporting`, `agent-interface`,
and `troubleshooting`.

## 12. Validation and workflow readiness

`langley validate` always checks structural validity, referential integrity, event
hashes, cache consistency, and report manifests. Method validation also emits coded
issues, including:

| Code | Severity | Condition |
|---|---|---|
| `TOO_FEW_HYPOTHESES` | error | Fewer than two active hypotheses |
| `MATRIX_GAP` | error | Active pair is not assessed |
| `MISSING_CELL_RATIONALE` | error | Assessment lacks required reasoning |
| `ABSENCE_NOT_OBSERVABLE` | error | Absence evidence lacks observability analysis |
| `UNPROVEN_ARCHIVE` | warning | Hypothesis archived without cited inconsistency |
| `NON_DIAGNOSTIC_ACTIVE` | warning | Evidence has no diagnostic value after refinement |
| `CONCLUSION_INCOMPLETE` | error | Active hypothesis omitted from conclusion |
| `SCORE_DISAGREEMENT_UNEXPLAINED` | warning | Conclusion differs from heuristic ordering without rationale |
| `LINCHPIN_UNTESTED` | error | Critical evidence has no sensitivity test |
| `NO_INDICATORS` | error | No future indicator exists |
| `STALE_CONCLUSION` | error | Upstream state changed after conclusion |
| `STALE_REPORT` | warning | Report predates current state |
| `JOB_CONTEXT_MISMATCH` | error | EDSL Results do not match the recorded job/project context |
| `STALE_PROPOSAL` | warning | Proposal was generated from an older project revision |
| `MALFORMED_EDSL_ANSWER` | error | A Results answer does not match its job-type schema |
| `PROPOSAL_CONFLICT` | error | Acceptance would create conflicting current judgments |

Normal commands may proceed with warnings. `report generate` refuses structural and
method errors but supports `--draft` to generate a visibly incomplete working report.
There is no generic `--force` bypass for invalid state.

## 13. Report contract

Each generated report contains:

1. Question, scope, state revision, and generation metadata.
2. Executive assessment and confidence.
3. All active hypotheses with relative likelihood, rationale, and ranking/ties.
4. ACH matrix with cell rationales available in the JSON companion.
5. Inconsistency and diagnosticity summaries with rubric version.
6. Critical evidence, assumptions, source concerns, and deception considerations.
7. Sensitivity tests and whether conclusions changed.
8. Residual uncertainty and information gaps.
9. Future indicators and collection owners.
10. Archived hypotheses/evidence and why they were removed.
11. Audit metadata and artifact hashes.

`analysis.json` is the canonical machine-readable report. `report.md` is a rendered
view, and `matrix.csv` supports inspection in a spreadsheet. `manifest.json` hashes
all files and records the source project revision.

## 14. Package structure

The initial package should resemble its peers:

```text
langley/
  __init__.py
  __main__.py
  cli.py
  schemas.py
  store.py
  events.py
  workflow.py
  analysis.py
  edsl_jobs.py
  ingest.py
  proposals.py
  validation.py
  renderer.py
  docs.py
  docs_content/
    *.md
tests/
  test_agent_interface.py
  test_cli.py
  test_store.py
  test_analysis.py
  test_edsl_jobs.py
  test_ingest.py
  test_proposals.py
  test_validation.py
pyproject.toml
README.md
LICENSE
SPEC.md
```

Target runtime is Python 3.11+. Initial dependencies are:

- `typer` for the command tree;
- `pydantic` for schemas and validation;
- `rich` for opt-in human output;
- `edsl` for portable Jobs construction and Results ingestion.

The default build backend is setuptools, matching `green` and `kahn`. The console
entry point is:

```toml
[project.scripts]
langley = "langley.cli:main"
```

Langley itself requires no network access and generated Jobs contain no model. Only
the separately approved `ep run` handoff may use a network model. The EDSL dependency
is declared consistently with peer packages during development:

```toml
dependencies = [
  "edsl @ git+https://github.com/expectedparrot/edsl.git@main",
  "pydantic>=2.7",
  "rich>=13.7",
  "typer>=0.12"
]
```

## 15. Exit codes

| Code | Meaning |
|---:|---|
| 0 | Success, including success with warnings |
| 1 | User/input/workflow error represented in the JSON envelope |
| 2 | CLI syntax error |
| 3 | Project corruption or schema incompatibility |
| 4 | Revision conflict or lock contention |

## 16. Security and privacy

- Project data stays local unless the calling agent explicitly moves it.
- Source fields store citations and hashes, not credentials.
- Error output must not echo environment variables or secret values.
- Markdown report rendering escapes raw HTML by default.
- Paths in imported documents are resolved relative to the project and normalized;
  report generation never reads arbitrary paths embedded in evidence text.

## 17. Acceptance criteria for v0.1

The first implementation is complete when:

1. A clean Python 3.11 environment can install the package and run `langley --help`.
2. An agent can initialize and complete a small ACH analysis using only JSON output
   and successive `langley next` calls.
3. Every command emits the stable envelope, with structured recovery hints on error.
4. State survives process restarts and rebuilds exactly from the event log.
5. Revision guards prevent a stale writer from mutating state.
6. Matrix completeness distinguishes unassessed from neutral/not-applicable cells.
7. Diagnosticity and inconsistency summaries are deterministic, expandable, and
   covered by unit tests.
8. Hypothesis/evidence revisions make downstream conclusions and reports stale.
9. Sensitivity tests do not mutate the base matrix.
10. Validation prevents a final report that omits a hypothesis, lacks linchpin
    testing, or lacks indicators.
11. Generated JSON, Markdown, and CSV reports agree and have verified hashes.
12. Tests include the complete eight-step happy path plus malformed imports,
    partial matrices, archived entities, score ties, stale state, event tampering,
    and concurrent revision conflicts.
13. Every EDSL job type round-trips through `Jobs.git.save/load`, contains no model,
    and embeds the project ID, revision, job ID, and target IDs.
14. EDSL Results ingestion validates context and structured answers, preserves model
    provenance, and is idempotent for the same Results hash.
15. Imported model answers remain pending proposals until separately accepted or
    rejected; accepting them creates ordinary audited Langley events.
16. Conflicting, malformed, or stale proposals cannot silently mutate the analysis.

## 18. Deferred decisions and future work

The following are deliberately outside v0.1 and should be decided only after the
core workflow is tested with agents:

- Collaborative multi-user merges beyond optimistic revision checks.
- Cryptographic signatures for sources or analyst approvals.
- Configurable scoring rubrics.
- Bayesian or probabilistic extensions with defensible likelihood inputs.
- Import/export compatibility with other ACH tools.
- A browser matrix editor or hosted project store.

Any probabilistic extension must remain distinct from qualitative ACH scoring and
must never infer likelihoods merely from counts of consistent evidence.
