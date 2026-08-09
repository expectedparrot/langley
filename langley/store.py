from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import LangleyError


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


EMPTY_STATE = {
    "hypotheses": {}, "evidence": {}, "matrix": {}, "conclusions": {},
    "sensitivities": {}, "indicators": {}, "jobs": {}, "proposals": {},
}


class Store:
    def __init__(self, start: Path, explicit: bool = False):
        self.root = start.resolve()
        if not explicit:
            cursor = self.root
            while cursor != cursor.parent and not (cursor / ".langley").is_dir():
                cursor = cursor.parent
            if (cursor / ".langley").is_dir():
                self.root = cursor
        self.dir = self.root / ".langley"

    @property
    def exists(self) -> bool:
        return (self.dir / "project.json").is_file()

    def require(self) -> None:
        if not self.exists:
            raise LangleyError("NO_PROJECT", "No Langley project found.", hint="Run `langley init --title ... --question ...`.")

    def project(self) -> dict:
        self.require()
        return json.loads((self.dir / "project.json").read_text())

    def event_paths(self) -> list[Path]:
        return sorted((self.dir / "events").glob("*.json")) if self.exists else []

    def events(self) -> list[dict]:
        return [json.loads(path.read_text()) for path in self.event_paths()]

    @property
    def revision(self) -> int:
        return len(self.event_paths())

    def init(self, project: dict) -> None:
        if self.exists:
            raise LangleyError("ALREADY_EXISTS", "A Langley project already exists here.", context={"root": str(self.root)})
        for name in ("events", "cache", "snapshots", "jobs", "proposals", "reports"):
            (self.dir / name).mkdir(parents=True, exist_ok=True)
        write_json(self.dir / "project.json", project)
        write_json(self.dir / "cache" / "state.json", {**EMPTY_STATE, "revision": 0})

    def state(self) -> dict:
        self.require()
        state = json.loads(json.dumps(EMPTY_STATE))
        for event in self.events():
            self._apply(state, event)
        state["revision"] = self.revision
        return state

    def append(self, event_type: str, payload: dict, *, actor: dict, argv: list[str], if_revision: int | None = None) -> dict:
        self.require()
        revision = self.revision
        if if_revision is not None and revision != if_revision:
            raise LangleyError("REVISION_CONFLICT", f"Expected revision {if_revision}, found {revision}.", context={"expected": if_revision, "actual": revision})
        previous = self.events()[-1]["event_hash"] if revision else None
        body = {"revision": revision + 1, "type": event_type, "timestamp": now(), "actor": actor, "argv": argv, "previous_hash": previous, "payload": payload}
        body["event_hash"] = digest(body)
        write_json(self.dir / "events" / f"{revision + 1:08d}.json", body)
        state = self.state()
        write_json(self.dir / "cache" / "state.json", state)
        return body

    @staticmethod
    def _apply(state: dict, event: dict) -> None:
        p, kind = event["payload"], event["type"]
        if kind.endswith(".created"):
            bucket = {
                "hypothesis": "hypotheses", "evidence": "evidence",
                "conclusion": "conclusions", "sensitivity": "sensitivities",
                "indicator": "indicators", "job": "jobs", "proposal": "proposals",
            }[kind.split(".")[0]]
            state[bucket][p["id"]] = p
        elif kind.endswith(".updated"):
            bucket = {
                "hypothesis": "hypotheses", "evidence": "evidence",
                "conclusion": "conclusions", "sensitivity": "sensitivities",
                "indicator": "indicators", "job": "jobs", "proposal": "proposals",
            }[kind.split(".")[0]]
            state[bucket][p["id"]].update(p["changes"])
        elif kind == "matrix.assessed":
            state["matrix"][f'{p["evidence_id"]}:{p["hypothesis_id"]}'] = p
        elif kind == "proposal.reviewed":
            state["proposals"][p["id"]].update({"status": p["status"], "review_reason": p["reason"], "reviewed_at": p["reviewed_at"]})

    def next_id(self, bucket: str, prefix: str) -> str:
        values = self.state()[bucket]
        highest = max((int(key[len(prefix):]) for key in values if key.startswith(prefix)), default=0)
        return f"{prefix}{highest + 1:03d}"

    def verify(self) -> list[dict]:
        issues, previous = [], None
        for index, event in enumerate(self.events(), 1):
            saved = event.pop("event_hash", None)
            expected = digest(event)
            event["event_hash"] = saved
            if event.get("revision") != index or event.get("previous_hash") != previous or saved != expected:
                issues.append({"code": "EVENT_CHAIN_INVALID", "revision": index})
            previous = saved
        return issues
