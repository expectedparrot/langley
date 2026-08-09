from __future__ import annotations

import json
from typing import Any

import typer

from .errors import LangleyError


def envelope(command: str, argv: list[str], *, data=None, root=None, revision=None, warnings=None, errors=None, next_steps=None) -> dict:
    errors = errors or []
    return {
        "schema_version": "1.0", "command": command, "argv": argv,
        "status": "error" if errors else ("warning" if warnings else "ok"),
        "project_root": str(root) if root else None, "revision": revision,
        "data": data or {}, "artifacts": {}, "warnings": warnings or [],
        "errors": errors, "next_steps": next_steps or [],
    }


def emit(payload: dict, human: bool = False) -> None:
    if human:
        typer.echo(f'{payload["command"]}: {payload["status"]}')
        typer.echo(json.dumps(payload["data"], indent=2, ensure_ascii=False))
    else:
        typer.echo(json.dumps(payload, ensure_ascii=False))


def fail(command: str, argv: list[str], error: LangleyError, *, root=None, revision=None, human=False) -> None:
    emit(envelope(command, argv, root=root, revision=revision, errors=[error.as_dict()]), human)
    raise typer.Exit(code=4 if error.code == "REVISION_CONFLICT" else 1)
