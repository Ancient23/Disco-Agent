from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseWorkflow

WORKFLOW_REGISTRY: dict[str, type[BaseWorkflow]] = {}


def register(name: str):
    def decorator(cls: type[BaseWorkflow]) -> type[BaseWorkflow]:
        WORKFLOW_REGISTRY[name] = cls
        return cls

    return decorator
