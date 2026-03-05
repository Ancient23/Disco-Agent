from __future__ import annotations

import json
import logging
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query

from ue_agent.config import BudgetConfig, ConductorConfig
from ue_agent.cost_tracker import CostTracker
from ue_agent.queue import TaskQueue
from ue_agent.workflows import register
from ue_agent.workflows.base import BaseWorkflow, Notifier, WorkflowResult

logger = logging.getLogger(__name__)


@register("submit")
class SubmitWorkflow(BaseWorkflow):
    def __init__(
        self,
        task: dict[str, Any],
        queue: TaskQueue,
        notifier: Notifier,
        conductor_config: ConductorConfig,
        budget_config: BudgetConfig,
        repo_root: str,
    ):
        super().__init__(task=task, queue=queue, notifier=notifier)
        self.conductor_config = conductor_config
        self.cost_tracker = CostTracker(budget_config.submit_warning_usd)
        self.repo_root = repo_root

    async def execute(self) -> WorkflowResult:
        params = json.loads(self.task["params"]) if isinstance(self.task["params"], str) else self.task["params"]
        project = self.task["project"]
        options_str = params.get("options", "")

        prompt = (
            f"Submit a Conductor render job for project '{project}'.\n"
            f"Use the /submit-job command with these options: {options_str}\n"
            f"If no specific options, use defaults from the app config.\n"
            f"Report the submission result."
        )

        conductor_cwd = f"{self.repo_root}/{self.conductor_config.conductor_agent_path}"

        sdk_output = ""
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                allowed_tools=["Read", "Glob", "Grep", "Bash", "Write"],
                cwd=conductor_cwd,
                setting_sources=["project"],
                permission_mode="bypassPermissions",
            ),
        ):
            if hasattr(message, "cost_usd"):
                warnings = self.cost_tracker.add_cost(message.cost_usd)
                for w in warnings:
                    await self.notifier.send_status(self.channel_id, w)
            if hasattr(message, "result"):
                sdk_output = message.result

        success = "error" not in sdk_output.lower() if sdk_output else False
        return WorkflowResult(
            success=success,
            output=sdk_output,
            error="" if success else sdk_output,
            cost_usd=self.cost_tracker.total_cost_usd,
        )
