from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import discord

from ue_agent.config import AgentConfig
from ue_agent.queue import TaskQueue
from ue_agent.session_history import format_session_for_prompt, load_recent_sessions, search_sessions
from ue_agent.utils import truncate_for_discord
from ue_agent.workflows.base import WorkflowResult

logger = logging.getLogger(__name__)


def parse_command(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text.startswith("!"):
        return None

    parts = text.split(None, 1)
    cmd = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if cmd == "!build":
        if not rest:
            return None
        tokens = rest.split()
        return {
            "workflow": "compile",
            "project": tokens[0],
            "platform": tokens[1] if len(tokens) > 1 else "Win64",
            "params": {},
        }

    if cmd == "!package":
        if not rest:
            return None
        tokens = rest.split()
        return {
            "workflow": "package",
            "project": tokens[0],
            "platform": tokens[1] if len(tokens) > 1 else "Win64",
            "params": {},
        }

    if cmd == "!submit":
        if not rest:
            return None
        tokens = rest.split(None, 1)
        project = tokens[0]
        options = tokens[1] if len(tokens) > 1 else ""
        return {
            "workflow": "submit",
            "project": project,
            "platform": "Win64",
            "params": {"options": options},
        }

    if cmd == "!analyze":
        if not rest:
            return None
        prompt = rest.strip('"').strip("'")
        return {
            "workflow": "analyze",
            "project": "",
            "platform": "",
            "params": {"prompt": prompt},
        }

    if cmd == "!run":
        if not rest:
            return None
        prompt = rest.strip('"').strip("'")
        return {
            "workflow": "custom",
            "project": "",
            "platform": "",
            "params": {"prompt": prompt},
        }

    if cmd == "!status":
        return {"workflow": "__status", "project": "", "platform": "", "params": {}}

    if cmd == "!cancel":
        return {"workflow": "__cancel", "project": "", "platform": "", "params": {}}

    if cmd == "!history":
        search_term = rest.strip('"').strip("'").strip() if rest else ""
        return {
            "workflow": "__history",
            "project": "",
            "platform": "",
            "params": {"search": search_term},
        }

    if cmd == "!help":
        return {"workflow": "__help", "project": "", "platform": "", "params": {}}

    return None


class DiscordNotifier:
    def __init__(self, bot: discord.Client):
        self.bot = bot

    async def send_status(self, channel_id: str, message: str) -> None:
        channel = self.bot.get_channel(int(channel_id))
        if channel:
            await channel.send(truncate_for_discord(message))

    async def send_result(
        self, channel_id: str, message_id: str, result: WorkflowResult
    ) -> None:
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return

        if result.success:
            text = f"**Completed** (${result.cost_usd:.2f})\n{result.output}"
        else:
            text = f"**Failed** (${result.cost_usd:.2f})\n{result.error}"

        await channel.send(truncate_for_discord(text))


def create_bot(config: AgentConfig, queue: TaskQueue, repo_root: str = "") -> discord.Client:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = discord.Client(intents=intents)

    required_role = config.discord.required_role
    command_channel_id = config.discord.command_channel_id
    history_dir = str(Path(repo_root) / "adw-agent" / "chat_history") if repo_root else "chat_history"

    @bot.event
    async def on_ready():
        logger.info(f"Discord bot connected as {bot.user}")

    @bot.event
    async def on_message(message: discord.Message):
        if message.author == bot.user:
            return

        if command_channel_id and str(message.channel.id) != command_channel_id:
            return

        if required_role and isinstance(message.author, discord.Member):
            role_names = [r.name for r in message.author.roles]
            if required_role not in role_names:
                return

        parsed = parse_command(message.content)
        if parsed is None:
            return

        if parsed["workflow"] == "__history":
            search_term = parsed["params"].get("search", "")
            if search_term:
                sessions = search_sessions(
                    search_term, history_dir=history_dir, max_results=5,
                )
                header = f"**Session history matching** `{search_term}`"
            else:
                sessions = load_recent_sessions(n=5, history_dir=history_dir)
                header = "**Recent session history**"

            if not sessions:
                await message.channel.send(f"{header}\nNo sessions found.")
                return

            lines = [header]
            for s in sessions:
                lines.append(format_session_for_prompt(s, max_output_len=200))
            await message.channel.send(
                truncate_for_discord("\n".join(lines))
            )
            return

        if parsed["workflow"] == "__help":
            help_text = (
                "**UE Build Agent Commands**\n"
                "```\n"
                "!build <project> [platform]     Compile via RunUAT (auto-fix on failure)\n"
                "!package <project> [platform]   Package (compile + cook + stage + pak)\n"
                "!submit <project> [options]     Submit Conductor render job\n"
                '!analyze "<question>"            Research the codebase (read-only)\n'
                '!run "<prompt>"                  Freeform Claude session (read/write)\n'
                '!history [search]               Show past sessions (optional keyword search)\n'
                "!status                         Show task queue\n"
                "!cancel                         Cancel all active tasks\n"
                "!help                           Show this message\n"
                "```\n"
                "**Examples**\n"
                "```\n"
                "!build CitySample\n"
                "!package CitySample Win64\n"
                "!submit CitySample --dry-run\n"
                '!analyze "why does the 4D capture crash on frame 200"\n'
                '!run "add error handling to s3_upload.py"\n'
                "!history crash\n"
                "```"
            )
            await message.channel.send(help_text)
            return

        if parsed["workflow"] == "__status":
            tasks = await queue.list_active()
            if not tasks:
                await message.channel.send("No active tasks.")
            else:
                lines = []
                for t in tasks:
                    lines.append(
                        f"#{t['id']} **{t['workflow']}** `{t['project']}` — {t['status']}"
                    )
                await message.channel.send("\n".join(lines))
            return

        if parsed["workflow"] == "__cancel":
            tasks = await queue.list_active()
            if not tasks:
                await message.channel.send("No active tasks to cancel.")
                return
            for t in tasks:
                await queue.cancel(t["id"])
            await message.channel.send(
                f"Cancelled {len(tasks)} task(s)."
            )
            return

        task_id = await queue.enqueue(
            workflow=parsed["workflow"],
            project=parsed["project"],
            platform=parsed["platform"],
            params=parsed["params"],
            discord_channel_id=str(message.channel.id),
            discord_message_id=str(message.id),
            requested_by=str(message.author),
        )
        await message.channel.send(
            f"Queued **{parsed['workflow']}** for `{parsed['project']}` (task #{task_id})"
        )

    return bot
