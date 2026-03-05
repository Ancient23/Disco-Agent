from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

from ue_agent.queue import TaskQueue

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    success: bool
    output: str = ""
    error: str = ""
    cost_usd: float = 0.0
    extra: dict = field(default_factory=dict)


class Notifier(Protocol):
    async def send_status(self, channel_id: str, message: str) -> None: ...
    async def send_result(
        self, channel_id: str, message_id: str, result: WorkflowResult
    ) -> None: ...


class BaseWorkflow(ABC):
    def __init__(
        self,
        task: dict[str, Any],
        queue: TaskQueue,
        notifier: Notifier,
    ):
        self.task = task
        self.queue = queue
        self.notifier = notifier
        self.task_id: int = task["id"]
        self.channel_id: str = task["discord_channel_id"]
        self.message_id: str = task["discord_message_id"]

    async def is_cancelled(self) -> bool:
        return await self.queue.is_cancelled(self.task_id)

    async def run(self) -> WorkflowResult:
        await self.notifier.send_status(
            self.channel_id,
            f"Started **{self.task['workflow']}** for `{self.task['project']}`",
        )
        try:
            result = await self.execute()
        except Exception as e:
            logger.exception("Workflow failed with exception")
            result = WorkflowResult(success=False, error=str(e))

        await self.notifier.send_result(self.channel_id, self.message_id, result)

        if result.success:
            await self.queue.complete(
                self.task_id,
                {"output": result.output, "cost_usd": result.cost_usd, **result.extra},
            )
        else:
            await self.queue.fail(
                self.task_id,
                {"error": result.error, "cost_usd": result.cost_usd, **result.extra},
            )

        return result

    @abstractmethod
    async def execute(self) -> WorkflowResult:
        ...
