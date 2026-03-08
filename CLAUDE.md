# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Disco-Agent is a general-purpose Discord-to-Claude automation daemon with a plugin system. It receives commands via Discord, queues them in SQLite, and executes them as Claude Agent SDK sessions. Ships with built-in `analyze` (read-only) and `custom` (read-write) workflows. Domain-specific functionality (e.g., Unreal Engine builds) is added through plugins.

## Development Commands

```bash
# Install dependencies
uv sync

# Run the daemon (dev mode, uses local source)
uv run disco-agent start

# Run all tests
uv run pytest -v

# Run a single test file
uv run pytest tests/test_foo.py -v

# Run a single test function
uv run pytest tests/test_queue.py::test_enqueue_and_fetch -v

# Rebuild global install after code changes
uv cache clean disco-agent && uv tool install . --reinstall
```

## Architecture

The system follows a queue-based architecture:

```
Discord bot (on_message) --> SQLite queue --> Daemon poll loop --> Workflow dispatcher
```

**Entry point:** `src/disco_agent/daemon.py:main()` runs the Discord bot and poll loop concurrently via `asyncio.gather`.

**Configuration:** `config.py` loads `config.toml` (TOML) + `.env` (bot token) into `AgentConfig` dataclasses. Resolution order: `--config` flag > `DISCO_AGENT_CONFIG` env > CWD auto-detection.

**Task queue:** `queue.py` uses `aiosqlite` with a single `tasks` table. `fetch_next()` atomically claims the oldest pending task via `UPDATE ... RETURNING *`.

**Workflow registry:** Workflows self-register via `@register("name")` decorator in `workflows/__init__.py`. The daemon imports built-in workflow modules in `daemon.py` to trigger registration. Plugin workflows are registered at startup by the plugin loader.

**BaseWorkflow** (`workflows/base.py`): All workflows inherit from this ABC. `run()` handles thread creation, status posting, and result reporting. Subclasses implement `execute() -> WorkflowResult`.

**AgentSessionWorkflow** (`workflows/session.py`): Base class for workflows that delegate to a Claude Agent SDK session. Handles session creation, streaming output to Discord, history injection, and cost tracking. Both built-in workflows (`analyze`, `custom`) and session plugins extend this.

**Plugin system** (`plugins.py`): At startup, `load_plugins()` iterates over `[[plugins]]` entries from config.toml. Session plugins dynamically create `AgentSessionWorkflow` subclasses. Code plugins import a `workflows.py` module via `importlib`. All plugin commands are registered in `WORKFLOW_REGISTRY` alongside built-ins.

## Built-in Workflows

- `analyze` (`workflows/analyze.py`): Read-only Claude session. Tools: Read, Glob, Grep, Bash.
- `custom` (`workflows/custom.py`): Read/write Claude session. Tools: Read, Glob, Grep, Bash, Edit, Write. Also handles thread replies.

## Plugin System

Two plugin types:

- **Session plugins** (`type = "session"`): Config-only. Each command in the plugin's `commands` list gets a dynamically generated `AgentSessionWorkflow` subclass that runs in the plugin's `path` directory.
- **Code plugins** (`type = "code"`): Python workflows loaded from `<path>/workflows.py`. The module is imported via `importlib.util` and must use `@register()` to add workflows. Optional `set_plugin_config(raw_dict)` receives the `[plugin-config.<name>]` section.

Plugin configs live in `config.toml` under `[[plugins]]` (plugin definition) and `[plugin-config.<name>]` (plugin-specific settings).

## UE Plugin

Lives in `plugins/ue/`. Loaded as a code plugin. Provides:

- `plugins/ue/config.py`: `UEPluginConfig` dataclass, `load_ue_config()` parser
- `plugins/ue/workflows.py`: `CompileWorkflow` (`!build`) and `PackageWorkflow` (`!package`) -- runs RunUAT.bat, on failure spawns Claude session for error analysis/retry

The UE plugin is not loaded unless configured in `config.toml` with a `[[plugins]]` entry of `type = "code"` and `path = "plugins/ue"`.

## Key Conventions

- All async code uses `asyncio` (no threads). Tests use `pytest-asyncio` with `asyncio_mode = "auto"`.
- Config dataclasses use stdlib `dataclasses`, not Pydantic (Pydantic is a dependency for the Agent SDK).
- Discord message content is truncated to 1900 chars via `truncate_for_discord()`.
- The `Notifier` protocol in `base.py` decouples workflows from the Discord client, making testing easier.
- Plugin commands must not conflict with built-in workflow names; the loader raises `ValueError` on collision.
