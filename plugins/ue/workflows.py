from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from disco_agent.cost_tracker import CostTracker
from disco_agent.queue import TaskQueue
from disco_agent.utils import tail_lines
from disco_agent.workflows import register
from disco_agent.workflows.base import BaseWorkflow, Notifier, WorkflowResult

logger = logging.getLogger(__name__)

# --- Plugin config (set by disco_agent.plugins loader) ---

_plugin_config = None


def set_plugin_config(raw):
    """Called by the plugin loader with the [plugin-config.ue] dict, or a UEPluginConfig directly."""
    global _plugin_config
    from plugins.ue.config import UEPluginConfig, load_ue_config
    if isinstance(raw, UEPluginConfig):
        _plugin_config = raw
    else:
        _plugin_config = load_ue_config(raw)


def _get_config():
    if _plugin_config is None:
        from plugins.ue.config import UEPluginConfig
        return UEPluginConfig()
    return _plugin_config


# --- UE build helpers ---

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


async def sdk_analyze_and_fix(error_log: str, repo_root: str, allowed_tools: list[str]):
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


# --- Workflows ---

@register("compile")
class CompileWorkflow(BaseWorkflow):
    def __init__(
        self,
        task: dict[str, Any],
        queue: TaskQueue,
        notifier: Notifier,
        repo_root: str,
        **kwargs,
    ):
        super().__init__(task=task, queue=queue, notifier=notifier)
        config = _get_config()
        self.ue_config = config
        self.cost_tracker = CostTracker(config.compile_warning_usd)
        self.repo_root = repo_root

    async def execute(self) -> WorkflowResult:
        config = self.ue_config
        max_retries = config.max_retries
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

            task_platform = self.task.get("platform") or config.platform
            task_project_path = self.task.get("project_path") or config.project_path

            exit_code, stdout, stderr = await run_uat(
                engine_path=config.engine_path,
                project_path=task_project_path,
                platform=task_platform,
                flags=config.build_flags,
                cwd=self.repo_root,
            )

            if exit_code == 0:
                return WorkflowResult(
                    success=True,
                    output=f"Build succeeded on attempt {attempt}",
                    cost_usd=self.cost_tracker.total_cost_usd,
                )

            last_error = stderr or stdout
            error_tail = tail_lines(last_error, config.error_tail_lines)

            if attempt >= max_retries:
                break

            await self._send_update(
                f"Build failed (attempt {attempt}). Analyzing error with Claude...",
            )

            stream = self._create_stream()

            async for message in sdk_analyze_and_fix(
                error_log=error_tail,
                repo_root=self.repo_root,
                allowed_tools=["Read", "Edit", "Glob", "Grep", "Bash"],
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

            if stream:
                await stream.finalize()

            await self._send_update("Fix attempted. Recompiling...")

        return WorkflowResult(
            success=False,
            error=f"Build failed after {max_retries} retries exhausted. Last error:\n{tail_lines(last_error, 50)}",
            cost_usd=self.cost_tracker.total_cost_usd,
        )


@register("package")
class PackageWorkflow(CompileWorkflow):
    """Package workflow -- same as compile but uses package budget threshold."""

    def __init__(self, task, queue, notifier, repo_root, **kwargs):
        super().__init__(task=task, queue=queue, notifier=notifier, repo_root=repo_root, **kwargs)
        config = _get_config()
        self.cost_tracker = CostTracker(config.package_warning_usd)
