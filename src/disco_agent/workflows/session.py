from __future__ import annotations

import json
import logging
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from disco_agent.cost_tracker import CostTracker
from disco_agent.queue import TaskQueue
from disco_agent.session_history import get_history_dir, inject_history_context, save_session
from disco_agent.workflows.base import BaseWorkflow, Notifier, WorkflowResult

logger = logging.getLogger(__name__)


class AgentSessionWorkflow(BaseWorkflow):
    """Workflow that delegates to a Claude Agent SDK session in a given directory."""

    def __init__(
        self,
        task: dict[str, Any],
        queue: TaskQueue,
        notifier: Notifier,
        session_cwd: str,
        allowed_tools: list[str],
        budget_warning_usd: float,
        repo_root: str,
    ):
        super().__init__(task=task, queue=queue, notifier=notifier)
        self.session_cwd = session_cwd
        self.allowed_tools = allowed_tools
        self.cost_tracker = CostTracker(budget_warning_usd)
        self.repo_root = repo_root
        self.history_dir = get_history_dir(repo_root)

    async def execute(self) -> WorkflowResult:
        params = json.loads(self.task["params"]) if isinstance(self.task["params"], str) else self.task["params"]
        prompt = params.get("prompt", "")

        if not prompt:
            return WorkflowResult(success=False, error="No prompt provided")

        full_prompt = inject_history_context(
            prompt,
            instruction="Execute the following request:",
            history_dir=self.history_dir,
        )

        stream = self._create_stream()
        sdk_output = ""
        async for message in query(
            prompt=full_prompt,
            options=ClaudeAgentOptions(
                allowed_tools=self.allowed_tools,
                cwd=self.session_cwd,
                permission_mode="bypassPermissions",
            ),
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock) and stream:
                        await stream.append(block.text)
                    elif isinstance(block, ToolUseBlock) and stream:
                        await stream.append_tool_use(block.name, block.input)
            elif isinstance(message, ResultMessage):
                if message.total_cost_usd is not None:
                    for w in self.cost_tracker.add_cost(message.total_cost_usd):
                        await self._send_update(w)
                if message.result:
                    sdk_output = message.result

        if stream:
            await stream.finalize()

        save_session(
            task_id=self.task_id,
            workflow=self.task["workflow"],
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
