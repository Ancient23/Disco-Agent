from __future__ import annotations

import logging
from typing import Any

import discord

from disco_agent.config import AgentConfig
from disco_agent.queue import TaskQueue
from disco_agent.session_history import format_session_for_prompt, get_history_dir, load_recent_sessions, search_sessions
from disco_agent.utils import truncate_for_discord
from disco_agent.workflows import WORKFLOW_REGISTRY
from disco_agent.workflows.base import WorkflowResult

logger = logging.getLogger(__name__)


def parse_command(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text.startswith("!"):
        return None

    parts = text.split(None, 1)
    cmd = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

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

    # Dynamic plugin commands
    cmd_name = cmd[1:]  # strip the !
    if cmd_name in WORKFLOW_REGISTRY:
        return {
            "workflow": cmd_name,
            "project": rest.split()[0] if rest else "",
            "platform": "",
            "params": {"prompt": rest, "raw_args": rest},
        }

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

    async def create_thread(self, channel_id: str, message_id: str, name: str) -> str:
        """Create a thread on a message. Returns thread ID as string."""
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return ""
        message = await channel.fetch_message(int(message_id))
        thread = await message.create_thread(name=name)
        thread_id = str(thread.id)
        # Register for reply tracking
        self.bot.active_threads[thread.id] = {"name": name}
        return thread_id

    async def send_to_thread(self, thread_id: str, message: str) -> str:
        """Send a message to a thread. Returns message ID as string."""
        thread = self.bot.get_channel(int(thread_id))
        if not thread:
            logger.warning("send_to_thread: thread %s not in cache, cannot send", thread_id)
            return ""
        content = truncate_for_discord(message)
        if not content or not content.strip():
            return ""
        msg = await thread.send(content)
        return str(msg.id)

    async def edit_message(self, thread_id: str, message_id: str, new_content: str) -> None:
        """Edit an existing message in a thread."""
        thread = self.bot.get_channel(int(thread_id))
        if not thread:
            return
        msg = await thread.fetch_message(int(message_id))
        await msg.edit(content=truncate_for_discord(new_content))

    def get_thread(self, thread_id: str):
        """Get a thread channel object for StreamingDiscordMessage."""
        thread = self.bot.get_channel(int(thread_id))
        if not thread:
            logger.warning("get_thread: thread %s not in channel cache", thread_id)
        return thread


def create_bot(config: AgentConfig, queue: TaskQueue, repo_root: str = "") -> discord.Client:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = discord.Client(intents=intents)
    bot.active_threads = {}  # type: ignore[attr-defined]

    required_role = config.discord.required_role
    command_channel_id = config.discord.command_channel_id
    history_dir = get_history_dir(repo_root) if repo_root else "chat_history"

    @bot.event
    async def on_ready():
        logger.info(f"Discord bot connected as {bot.user}")
        # Re-populate active_threads from guilds so replies work after restart
        for guild in bot.guilds:
            for thread in guild.threads:
                if thread.me is not None:
                    bot.active_threads[thread.id] = {"name": thread.name}
        logger.info("Restored %d active thread(s) for reply tracking", len(bot.active_threads))

    @bot.event
    async def on_message(message: discord.Message):
        if message.author == bot.user:
            return

        # Allow messages from the command channel or from threads parented to it
        if command_channel_id:
            channel_id = str(message.channel.id)
            parent_id = str(getattr(message.channel, "parent_id", "")) if isinstance(message.channel, discord.Thread) else ""
            if channel_id != command_channel_id and parent_id != command_channel_id:
                return

        if required_role:
            if not isinstance(message.author, discord.Member):
                return
            role_names = [r.name for r in message.author.roles]
            if required_role not in role_names:
                return

        parsed = parse_command(message.content)

        # Thread reply: if in an active thread and no command parsed
        if parsed is None:
            if isinstance(message.channel, discord.Thread) and message.channel.id in bot.active_threads:
                history_messages = []
                async for msg in message.channel.history(limit=50, oldest_first=True):
                    if msg.id == message.id:
                        continue
                    role = "assistant" if msg.author == bot.user else "user"
                    history_messages.append(f"[{role}] {msg.content}")

                thread_context = "\n".join(history_messages)

                task_id = await queue.enqueue(
                    workflow="custom",
                    project="",
                    platform="",
                    params={
                        "prompt": message.content,
                        "thread_context": thread_context,
                        "thread_id": str(message.channel.id),
                    },
                    discord_channel_id=str(message.channel.id),
                    discord_message_id=str(message.id),
                    requested_by=str(message.author),
                )
                await message.channel.send(f"↩️ Queued follow-up (task #{task_id})")
                logger.info("Thread reply → queued custom task #%d", task_id)
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
            # Built-in commands
            help_lines = [
                "**Disco-Agent Commands**",
                "```",
                '!analyze "<question>"            Research the codebase (read-only)',
                '!run "<prompt>"                  Freeform Claude session (read/write)',
                "!history [search]               Show past sessions (optional keyword search)",
                "!status                         Show task queue",
                "!cancel                         Cancel all active tasks",
                "!help                           Show this message",
            ]
            # Plugin commands
            plugin_cmds = sorted(
                name for name in WORKFLOW_REGISTRY
                if name not in ("analyze", "custom")
            )
            if plugin_cmds:
                help_lines.append("")
                help_lines.append("--- Plugins ---")
                for cmd in plugin_cmds:
                    help_lines.append(f"!{cmd}")
            help_lines.append("```")
            help_lines.append("")
            help_lines.append("**Thread Replies**")
            help_lines.append("Reply in a task thread to continue the conversation — no `!` command needed.")
            await message.channel.send("\n".join(help_lines))
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
