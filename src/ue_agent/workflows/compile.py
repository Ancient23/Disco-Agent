from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from ue_agent.config import BudgetConfig, CompileConfig, UEConfig
from ue_agent.cost_tracker import CostTracker
from ue_agent.queue import TaskQueue
from ue_agent.streaming import StreamingDiscordMessage
from ue_agent.utils import tail_lines
from ue_agent.workflows import register
from ue_agent.workflows.base import BaseWorkflow, Notifier, WorkflowResult

logger = logging.getLogger(__name__)


async def run_uat(
    engine_path: str | Path,
    project_path: str,
    platform: str,
    flags: list[str],
    cwd: str,
) -> tuple[int, str, str]:
    bat = Path(engine_path) / "Build" / "BatchFiles" / "RunUAT.bat"
    cmd = [
        str(bat),
        "BuildCookRun",
        f"-project={project_path}",
        f"-platform={platform}",
        *flags,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    returncode = proc.returncode if proc.returncode is not None else 1
    return (
        returncode,
        stdout_bytes.decode("utf-8", errors="replace"),
        stderr_bytes.decode("utf-8", errors="replace"),
    )


async def sdk_analyze_and_fix(
    error_log: str,
    repo_root: str,
    allowed_tools: list[str],
):
    prompt = (
        "A UE BuildCookRun compile has failed. Analyze the error below and attempt to fix it.\n"
        "Focus on the actual compilation error, not warnings.\n\n"
        f"Build error log (last lines):\n```\n{error_log}\n```"
    )
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=allowed_tools,
            cwd=repo_root,
            permission_mode="bypassPermissions",
        ),
    ):
        yield message


@register("compile")
class CompileWorkflow(BaseWorkflow):
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
        super().__init__(task=task, queue=queue, notifier=notifier)
        self.ue_config = ue_config
        self.compile_config = compile_config
        self.cost_tracker = CostTracker(budget_config.compile_warning_usd)
        self.repo_root = repo_root

    async def _send_update(self, text: str) -> None:
        """Send a status update to thread or channel."""
        if self.thread_id:
            await self.notifier.send_to_thread(self.thread_id, text)
        else:
            await self.notifier.send_status(self.channel_id, text)

    async def execute(self) -> WorkflowResult:
        max_retries = self.compile_config.max_retries
        last_error = ""

        for attempt in range(1, max_retries + 1):
            if await self.is_cancelled():
                return WorkflowResult(
                    success=False,
                    error="Cancelled by user",
                    cost_usd=self.cost_tracker.total_cost_usd,
                )

            await self._send_update(
                f"Compile attempt {attempt}/{max_retries} for `{self.task['project']}`",
            )

            task_platform = self.task.get("platform") or self.ue_config.platform
            task_project_path = self.task.get("project_path") or self.ue_config.project_path

            exit_code, stdout, stderr = await run_uat(
                engine_path=self.ue_config.engine_path,
                project_path=task_project_path,
                platform=task_platform,
                flags=self.ue_config.build_flags,
                cwd=self.repo_root,
            )

            if exit_code == 0:
                return WorkflowResult(
                    success=True,
                    output=f"Build succeeded on attempt {attempt}",
                    cost_usd=self.cost_tracker.total_cost_usd,
                )

            last_error = stderr or stdout
            error_tail = tail_lines(last_error, self.compile_config.error_tail_lines)

            if attempt >= max_retries:
                break

            await self._send_update(
                f"Build failed (attempt {attempt}). Analyzing error with Claude...",
            )

            sdk_output = ""
            stream = None
            if self.thread_id:
                thread = self.notifier.get_thread(self.thread_id)
                if thread:
                    stream = StreamingDiscordMessage(thread)

            async for message in sdk_analyze_and_fix(
                error_log=error_tail,
                repo_root=self.repo_root,
                allowed_tools=["Read", "Edit", "Glob", "Grep", "Bash"],
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
                        warnings = self.cost_tracker.add_cost(message.total_cost_usd)
                        for w in warnings:
                            await self._send_update(w)
                    if message.result:
                        sdk_output = message.result

            if stream:
                await stream.finalize()

            await self._send_update(
                f"Fix attempted. Recompiling...",
            )

        return WorkflowResult(
            success=False,
            error=f"Build failed after {max_retries} retries exhausted. Last error:\n{tail_lines(last_error, 50)}",
            cost_usd=self.cost_tracker.total_cost_usd,
        )
