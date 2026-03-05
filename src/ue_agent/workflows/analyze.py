from __future__ import annotations

import json
import logging
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query

from ue_agent.config import BudgetConfig
from ue_agent.cost_tracker import CostTracker
from ue_agent.queue import TaskQueue
from ue_agent.workflows import register
from ue_agent.workflows.base import BaseWorkflow, Notifier, WorkflowResult

logger = logging.getLogger(__name__)


@register("analyze")
class AnalyzeWorkflow(BaseWorkflow):
    def __init__(
        self,
        task: dict[str, Any],
        queue: TaskQueue,
        notifier: Notifier,
        budget_config: BudgetConfig,
        repo_root: str,
    ):
        super().__init__(task=task, queue=queue, notifier=notifier)
        self.cost_tracker = CostTracker(budget_config.analyze_warning_usd)
        self.repo_root = repo_root

    async def execute(self) -> WorkflowResult:
        params = json.loads(self.task["params"]) if isinstance(self.task["params"], str) else self.task["params"]
        question = params.get("prompt", "")

        if not question:
            return WorkflowResult(success=False, error="No question provided")

        sdk_output = ""
        async for message in query(
            prompt=question,
            options=ClaudeAgentOptions(
                allowed_tools=["Read", "Glob", "Grep", "Bash"],
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

        return WorkflowResult(
            success=True,
            output=sdk_output,
            cost_usd=self.cost_tracker.total_cost_usd,
        )
