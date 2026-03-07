from __future__ import annotations

from typing import Any

from disco_agent.config import BudgetConfig, CompileConfig, UEConfig
from disco_agent.queue import TaskQueue
from disco_agent.workflows import register
from disco_agent.workflows.base import Notifier
from disco_agent.workflows.compile import CompileWorkflow


@register("package")
class PackageWorkflow(CompileWorkflow):
    """Package workflow — same as compile but uses package budget threshold."""

    def __init__(
        self,
        task: dict[str, Any],
        queue: TaskQueue,
        notifier: Notifier,
        ue_config: UEConfig,
        compile_config: CompileConfig,
        budget_config: BudgetConfig,
        repo_root: str,
    ):
        budget_config_copy = BudgetConfig(
            compile_warning_usd=budget_config.package_warning_usd,
            package_warning_usd=budget_config.package_warning_usd,
            submit_warning_usd=budget_config.submit_warning_usd,
            analyze_warning_usd=budget_config.analyze_warning_usd,
            custom_warning_usd=budget_config.custom_warning_usd,
        )
        super().__init__(
            task=task,
            queue=queue,
            notifier=notifier,
            ue_config=ue_config,
            compile_config=compile_config,
            budget_config=budget_config_copy,
            repo_root=repo_root,
        )
