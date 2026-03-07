# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Disco-Agent (package name: `ue-agent`) is a Python daemon that automates Unreal Engine compile, package, and Conductor submission workflows via Discord commands. It uses the Claude Agent SDK for intelligent build error analysis and automated fixes.

## Development Commands

```bash
# Install dependencies
uv sync

# Run the daemon (dev mode, uses local source)
uv run ue-agent start

# Run all tests
uv run pytest -v

# Run a single test file
uv run pytest tests/test_queue.py -v

# Run a single test function
uv run pytest tests/test_queue.py::test_enqueue_and_fetch -v

# Rebuild global install after code changes
uv cache clean ue-agent && uv tool install . --reinstall
```

## Architecture

The system follows a queue-based architecture:

```
Discord bot (on_message) --> SQLite queue --> Daemon poll loop --> Workflow dispatcher
```

**Entry point:** `src/ue_agent/daemon.py:main()` runs the Discord bot and poll loop concurrently via `asyncio.gather`.

**Configuration:** `config.py` loads `config.toml` (TOML) + `.env` (bot token) into `AgentConfig` dataclasses. Resolution order: `--config` flag > `UE_AGENT_CONFIG` env > CWD auto-detection.

**Task queue:** `queue.py` uses `aiosqlite` with a single `tasks` table. `fetch_next()` atomically claims the oldest pending task via `UPDATE ... RETURNING *`.

**Workflow registry:** Workflows self-register via `@register("name")` decorator in `workflows/__init__.py`. The daemon imports all workflow modules in `daemon.py` to trigger registration. New workflows only need a file in `workflows/`, a `@register` decorator, and a command parser entry in `discord_bot.py`.

**BaseWorkflow** (`workflows/base.py`): All workflows inherit from this ABC. `run()` handles thread creation, status posting, and result reporting. Subclasses implement `execute() -> WorkflowResult`.

**Workflow types and their Claude Agent SDK access:**
- `compile` / `package`: Runs `RunUAT.bat BuildCookRun` subprocess. On failure, spawns a Claude session with read/write tools to analyze and fix errors. Retries up to `max_retries`.
- `analyze`: Read-only Claude session (tools: Read, Glob, Grep, Bash).
- `custom`: Read/write Claude session (adds Edit, Write). Also handles thread replies.
- `submit`: Claude session pointed at the `conductor-agent/` directory.

**Discord threading:** Every command creates a Discord thread for output. `StreamingDiscordMessage` (`streaming.py`) implements edit-in-place message streaming with rollover when messages exceed Discord's character limit. Thread replies (non-`!` messages in active threads) are routed to `custom` workflow with full thread history as context.

**Session history:** `session_history.py` persists completed sessions as JSON files in `chat_history/`. Injected into new Claude prompts so sessions have memory of previous interactions.

**Cost tracking:** `CostTracker` emits a one-time warning to Discord when a session exceeds its per-workflow budget threshold (soft limit, no hard stop).

## Key Conventions

- All async code uses `asyncio` (no threads). Tests use `pytest-asyncio` with `asyncio_mode = "auto"`.
- Config dataclasses use stdlib `dataclasses`, not Pydantic (despite Pydantic being a dependency -- it's for future use or the Agent SDK).
- Discord message content is truncated to 1900 chars via `truncate_for_discord()`.
- The `Notifier` protocol in `base.py` decouples workflows from the Discord client, making testing easier.
