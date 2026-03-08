from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from disco_agent.config import AgentConfig, load_config
from disco_agent.discord_bot import DiscordNotifier, create_bot
from disco_agent.queue import TaskQueue
from disco_agent.workflows import WORKFLOW_REGISTRY

# Import workflows to trigger @register decorators
import disco_agent.workflows.analyze  # noqa: F401
import disco_agent.workflows.custom  # noqa: F401

from disco_agent.plugins import load_plugins

logger = logging.getLogger("disco_agent")


def _build_workflow(
    workflow_name: str,
    task: dict[str, Any],
    queue: TaskQueue,
    notifier: DiscordNotifier,
    config: AgentConfig,
    repo_root: str,
):
    cls = WORKFLOW_REGISTRY[workflow_name]

    if workflow_name in ("analyze", "custom"):
        return cls(
            task=task,
            queue=queue,
            notifier=notifier,
            budget_config=config.budgets,
            repo_root=repo_root,
        )
    else:
        # Plugin workflow — session plugins take (task, queue, notifier, repo_root)
        return cls(
            task=task,
            queue=queue,
            notifier=notifier,
            repo_root=repo_root,
        )


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
                    wf.use_threads = workflow_name not in config.discord.non_threaded_workflows
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

    bot = create_bot(config, queue, repo_root=repo_root)
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
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").exists() and (cwd / "src" / "disco_agent").exists():
        return cwd
    return cwd


def _parse_args() -> tuple[str, Path | None]:
    """Parse CLI arguments. Returns (subcommand, config_path_or_None)."""
    import os

    subcommand = "start"
    config_path: Path | None = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--config" and i + 1 < len(args):
            config_path = Path(args[i + 1])
            i += 2
        elif args[i] in ("start", "queue"):
            subcommand = args[i]
            i += 1
        else:
            print(f"Unknown argument: {args[i]}")
            print("Usage: disco-agent [start|queue] [--config PATH]")
            sys.exit(1)

    # Fallback: DISCO_AGENT_CONFIG env var
    if config_path is None:
        env_config = os.environ.get("DISCO_AGENT_CONFIG", "")
        if env_config:
            config_path = Path(env_config)

    return subcommand, config_path


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    subcommand, explicit_config = _parse_args()

    if explicit_config:
        # Explicit config: derive .env from same directory
        config_path = explicit_config.resolve()
        config_dir = config_path.parent
        env_path = config_dir / ".env"
        config = load_config(config_path=config_path, env_path=env_path)
        # repo_root: from config, or parent of config dir
        if config.general.repo_root:
            repo_root = Path(config.general.repo_root)
        else:
            repo_root = config_dir.parent
    else:
        # Auto-detect from CWD (original behavior)
        repo_root = _find_repo_root()
        config_dir = repo_root
        config = load_config(
            config_path=config_dir / "config.toml",
            env_path=config_dir / ".env",
        )
        # Config repo_root overrides auto-detection
        if config.general.repo_root:
            repo_root = Path(config.general.repo_root)

    # Resolve relative db_path against the config directory
    if not Path(config.general.db_path).is_absolute():
        config.general.db_path = str(config_dir / config.general.db_path)

    load_plugins(config.plugins_raw, config.plugin_configs, str(config_dir))

    logger.info(f"Repo root: {repo_root}")
    logger.info(f"Config: {explicit_config or (repo_root / 'config.toml')}")

    if subcommand == "queue":
        asyncio.run(show_queue(config))
    elif subcommand == "start":
        asyncio.run(run_daemon(config, str(repo_root)))


if __name__ == "__main__":
    main()
