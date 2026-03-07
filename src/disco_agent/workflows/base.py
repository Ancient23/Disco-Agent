from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

from disco_agent.queue import TaskQueue
from disco_agent.streaming import StreamingDiscordMessage

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
    async def create_thread(self, channel_id: str, message_id: str, name: str) -> str: ...
    async def send_to_thread(self, thread_id: str, message: str) -> str: ...
    async def edit_message(self, thread_id: str, message_id: str, new_content: str) -> None: ...
    def get_thread(self, thread_id: str): ...


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
        self.thread_id: str = ""
        self.use_threads: bool = True

    async def is_cancelled(self) -> bool:
        return await self.queue.is_cancelled(self.task_id)

    async def _send_update(self, text: str) -> None:
        """Send a status update to thread (if active) or channel."""
        if self.thread_id:
            await self.notifier.send_to_thread(self.thread_id, text)
        else:
            await self.notifier.send_status(self.channel_id, text)

    def _create_stream(self) -> StreamingDiscordMessage | None:
        """Create a streaming message for the thread, or None if no thread."""
        if not self.thread_id:
            return None
        thread = self.notifier.get_thread(self.thread_id)
        return StreamingDiscordMessage(thread) if thread else None

    async def run(self) -> WorkflowResult:
        # Thread reply: reuse existing thread instead of creating a new one
        params = self.task.get("params", {})
        if isinstance(params, str):
            import json
            params = json.loads(params)
        if params.get("thread_id"):
            self.thread_id = params["thread_id"]
            self.use_threads = False

        if self.use_threads:
            try:
                thread_name = f"Task #{self.task_id} — {self.task['workflow']}"
                self.thread_id = await self.notifier.create_thread(
                    self.channel_id, self.message_id, thread_name,
                )
                await self.notifier.send_to_thread(
                    self.thread_id,
                    f"Starting **{self.task['workflow']}** for `{self.task.get('project', '')}`...",
                )
            except Exception:
                logger.warning("Failed to create thread, falling back to channel", exc_info=True)
                self.thread_id = ""

        if not self.thread_id:
            await self.notifier.send_status(
                self.channel_id,
                f"Started **{self.task['workflow']}** for `{self.task['project']}`",
            )

        try:
            result = await self.execute()
        except Exception as e:
            logger.exception("Workflow failed with exception")
            result = WorkflowResult(success=False, error=str(e))

        if self.thread_id:
            if result.success:
                text = f"**Completed** (${result.cost_usd:.2f})\n{result.output}"
            else:
                text = f"**Failed** (${result.cost_usd:.2f})\n{result.error}"
            await self.notifier.send_to_thread(self.thread_id, text)
        else:
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
