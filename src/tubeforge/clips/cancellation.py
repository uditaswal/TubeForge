"""Cancellation signal shared by the clip pipeline."""

from __future__ import annotations


class TaskCancelled(Exception):
    def __init__(self, message: str = "Task cancelled") -> None:
        super().__init__(message)
