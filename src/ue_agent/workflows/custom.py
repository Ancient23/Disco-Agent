from __future__ import annotations

import json
import logging
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from ue_agent.config import BudgetConfig
from ue_agent.cost_tracker import CostTracker
from ue_agent.queue import TaskQueue
from ue_agent.session_history import get_history_dir, inject_history_context, save_session
from ue_agent.workflows import register
from ue_agent.workflows.base import BaseWorkflow, Notifier, WorkflowResult

logger = logging.getLogger(__name__)


@register("custom")
class CustomWorkflow(BaseWorkflow):
    def __init__(
        self,
        task: dict[str, Any],
        queue: TaskQueue,
        notifier: Notifier,
        budget_config: BudgetConfig,
        repo_root: str,
    ):
        super().__init__(task=task, queue=queue, notifier=notifier)
        self.cost_tracker = CostTracker(budget_config.custom_warning_usd)
        self.repo_root = repo_root
        self.history_dir = get_history_dir(repo_root)

    async def execute(self) -> WorkflowResult:
        params = json.loads(self.task["params"]) if isinstance(self.task["params"], str) else self.task["params"]
        prompt = params.get("prompt", "")

        if not prompt:
            return WorkflowResult(success=False, error="No prompt provided")

        thread_context = params.get("thread_context", "")
        thread_id_override = params.get("thread_id", "")

        if thread_context:
            full_prompt = (
                "=== Previous conversation in this thread ===\n"
                f"{thread_context}\n"
                "=== End of thread history ===\n\n"
                "The user may reference the conversation above. "
                f"Execute the following request:\n\n{prompt}"
            )
        else:
            full_prompt = inject_history_context(
                prompt,
                instruction="Execute the following request:",
                history_dir=self.history_dir,
            )

        # If this is a thread reply, use the existing thread instead of creating a new one
        if thread_id_override:
            self.thread_id = thread_id_override
            self.use_threads = False  # Don't create a new thread in run()

        stream = self._create_stream()
        sdk_output = ""
        async for message in query(
            prompt=full_prompt,
            options=ClaudeAgentOptions(
                allowed_tools=["Read", "Edit", "Write", "Glob", "Grep", "Bash"],
                cwd=self.repo_root,
                permission_mode="bypassPermissions",
            ),
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock) and stream:
                        await stream.append(block.text)
                        logger.info("Claude: %s", block.text[:200])
                    elif isinstance(block, ToolUseBlock) and stream:
                        await stream.append_tool_use(block.name, block.input)
                        logger.info("Tool: %s", block.name)
            elif isinstance(message, ResultMessage):
                if message.total_cost_usd is not None:
                    for w in self.cost_tracker.add_cost(message.total_cost_usd):
                        await self._send_update(w)
                if message.result:
                    sdk_output = message.result

        if stream:
            await stream.finalize()

        # Persist this session for future reference
        save_session(
            task_id=self.task_id,
            workflow="custom",
            prompt=prompt,
            output=sdk_output,
            cost_usd=self.cost_tracker.total_cost_usd,
            requested_by=self.task.get("requested_by", ""),
            discord_channel_id=self.channel_id,
            history_dir=self.history_dir,
        )

        return WorkflowResult(
            success=True,
            output=sdk_output,
            cost_usd=self.cost_tracker.total_cost_usd,
        )
