from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query

from ue_agent.config import BudgetConfig
from ue_agent.cost_tracker import CostTracker
from ue_agent.queue import TaskQueue
from ue_agent.session_history import build_history_context, save_session
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
        self.history_dir = str(Path(repo_root) / "adw-agent" / "chat_history")

    async def execute(self) -> WorkflowResult:
        params = json.loads(self.task["params"]) if isinstance(self.task["params"], str) else self.task["params"]
        prompt = params.get("prompt", "")

        if not prompt:
            return WorkflowResult(success=False, error="No prompt provided")

        # Inject prior session history so Claude can reference earlier conversations
        history_context = build_history_context(history_dir=self.history_dir)
        if history_context:
            full_prompt = (
                f"{history_context}\n"
                "The user may reference previous sessions above. "
                "Execute the following request:\n\n"
                f"{prompt}"
            )
        else:
            full_prompt = prompt

        sdk_output = ""
        async for message in query(
            prompt=full_prompt,
            options=ClaudeAgentOptions(
                allowed_tools=["Read", "Edit", "Write", "Glob", "Grep", "Bash"],
                cwd=self.repo_root,
                permission_mode="bypassPermissions",
            ),
        ):
            if hasattr(message, "cost_usd"):
                warnings = self.cost_tracker.add_cost(message.cost_usd)
                for w in warnings:
                    await self.notifier.send_status(self.channel_id, w)
            if hasattr(message, "result"):
                sdk_output = message.result

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
