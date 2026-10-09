"""Custom exceptions for Kindle QuickSend."""

from typing import Optional


class KqsError(Exception):
    """Base exception for user-facing Kindle QuickSend errors with an optional hint."""

    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        if self.hint:
            return f"{self.message}\nHint: {self.hint}"
        return self.message
