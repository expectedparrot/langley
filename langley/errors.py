from __future__ import annotations


class LangleyError(Exception):
    def __init__(self, code: str, message: str, *, context=None, hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or {}
        self.hint = hint

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "context": self.context, "hint": self.hint}
