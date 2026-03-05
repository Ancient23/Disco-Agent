from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from ue_agent.config import AgentConfig, load_config
from ue_agent.discord_bot import DiscordNotifier, create_bot
from ue_agent.queue import TaskQueue
from ue_agent.workflows import WORKFLOW_REGISTRY

# Import workflows to trigger @register decorators
import ue_agent.workflows.compile  # noqa: F401
import ue_agent.workflows.package  # noqa: F401
import ue_agent.workflows.submit  # noqa: F401
import ue_agent.workflows.analyze  # noqa: F401
import ue_agent.workflows.custom  # noqa: F401

logger = logging.getLogger("ue_agent")


def _build_workflow(
    workflow_name: str,
    task: dict[str, Any],
    queue: TaskQueue,
    notifier: DiscordNotifier,
    config: AgentConfig,
    repo_root: str,
):
    cls = WORKFLOW_REGISTRY[workflow_name]

    if workflow_name in ("compile", "package"):
        return cls(
            task=task,
            queue=queue,
            notifier=notifier,
            ue_config=config.ue,
            compile_config=config.compile,
            budget_config=config.budgets,
            repo_root=repo_root,
        )
    elif workflow_name == "submit":
        return cls(
            task=task,
            queue=queue,
            notifier=notifier,
            conductor_config=config.conductor,
            budget_config=config.budgets,
            repo_root=repo_root,
        )
    elif workflow_name in ("analyze", "custom"):
        return cls(
            task=task,
            queue=queue,
            notifier=notifier,
            budget_config=config.budgets,
            repo_root=repo_root,
        )
    else:
        raise ValueError(f"Unknown workflow: {workflow_name}")


async def poll_loop(
    queue: TaskQueue,
    notifier: DiscordNotifier,
    config: AgentConfig,
    repo_root: str,
    shutdown_event: asyncio.Event,
):
    interval = config.general.poll_interval_seconds
    logger.info(f"Daemon poll loop started (interval={interval}s)")

    while not shutdown_event.is_set():
        task = await queue.fetch_next()
        if task is not None:
            workflow_name = task["workflow"]
            if workflow_name not in WORKFLOW_REGISTRY:
                logger.error(f"Unknown workflow '{workflow_name}' for task #{task['id']}")
                await queue.fail(task["id"], {"error": f"Unknown workflow: {workflow_name}"})
            else:
                logger.info(f"Running {workflow_name} task #{task['id']}")
                try:
                    wf = _build_workflow(workflow_name, task, queue, notifier, config, repo_root)
                    await wf.run()
                except Exception:
                    logger.exception(f"Unhandled error in workflow {workflow_name}")
                    await queue.fail(task["id"], {"error": "Unhandled daemon error"})

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def show_queue(config: AgentConfig):
    queue = TaskQueue(config.general.db_path)
    await queue.initialize()
    tasks = await queue.list_active()
    await queue.close()

    if not tasks:
        print("No active tasks.")
        return

    for t in tasks:
        print(f"#{t['id']}  {t['status']:<10}  {t['workflow']:<10}  {t['project']}")


async def run_daemon(config: AgentConfig, repo_root: str):
    queue = TaskQueue(config.general.db_path)
    await queue.initialize()

    bot = create_bot(config, queue)
    notifier = DiscordNotifier(bot)
    shutdown_event = asyncio.Event()

    async def start_bot():
        await bot.start(config.discord.bot_token)

    async def start_poll():
        await asyncio.sleep(2)
        await poll_loop(queue, notifier, config, repo_root, shutdown_event)

    try:
        await asyncio.gather(start_bot(), start_poll())
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down...")
        shutdown_event.set()
        await bot.close()
        await queue.close()


def _find_repo_root() -> Path:
    """Find the repo root by looking for adw-agent/ with config files.

    Search order:
    1. Current working directory IS adw-agent/ (cwd has config.toml or pyproject.toml)
    2. Current working directory contains adw-agent/
    3. Walk up from cwd looking for adw-agent/
    """
    cwd = Path.cwd()

    # cwd is the adw-agent directory itself
    if (cwd / "pyproject.toml").exists() and (cwd / "src" / "ue_agent").exists():
        return cwd.parent

    # cwd contains adw-agent/
    if (cwd / "adw-agent" / "pyproject.toml").exists():
        return cwd

    # Walk up from cwd
    for parent in cwd.parents:
        if (parent / "adw-agent" / "pyproject.toml").exists():
            return parent

    # Fallback: assume cwd is repo root
    return cwd


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    repo_root = _find_repo_root()
    agent_dir = repo_root / "adw-agent"

    subcommand = sys.argv[1] if len(sys.argv) > 1 else "start"

    config = load_config(
        config_path=agent_dir / "config.toml",
        env_path=agent_dir / ".env",
    )

    logger.info(f"Repo root: {repo_root}")
    logger.info(f"Config: {agent_dir / 'config.toml'}")

    if subcommand == "queue":
        asyncio.run(show_queue(config))
    elif subcommand == "start":
        asyncio.run(run_daemon(config, str(repo_root)))
    else:
        print(f"Unknown subcommand: {subcommand}")
        print("Usage: ue-agent [start|queue]")
        sys.exit(1)


if __name__ == "__main__":
    main()
