# Disco-Agent

A daemon that automates workflows via Discord commands using the Claude Agent SDK. Ships with built-in research and freeform coding commands, and supports plugins for domain-specific workflows (e.g., Unreal Engine builds).

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** package manager
- **Claude Code CLI** logged in (Max plan or API key)
- **Discord bot token** ([create one here](https://discord.com/developers/applications))

## Setup

### 1. Install dependencies

```bash
cd Disco-Agent
uv sync
```

### 2. Create the Discord bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application**, give it a name, then go to **Bot** in the left sidebar
3. Enable **Message Content Intent** under Privileged Gateway Intents
4. Click **Reset Token** (or **Copy** if first time) -- save this token, it's only shown once

### 3. Invite the bot to your server

1. In the Developer Portal, go to **OAuth2** > **URL Generator**
2. Under **Scopes**, check `bot`
3. Under **Bot Permissions**, check: Send Messages, Create Public Threads, Send Messages in Threads, Read Message History, View Channels
4. Copy the generated URL, paste it in your browser, select your server, and authorize

> **Updating an existing bot?** If you previously invited the bot without thread permissions, regenerate the OAuth2 URL with the full permission set above and re-authorize. This updates permissions in place -- it won't duplicate the bot.

### 4. Configure secrets

```bash
cp .env.example .env
```

Edit `.env` and paste your bot token:

```env
DISCORD_BOT_TOKEN=MTIzNDU2Nzg5MDEyMzQ1Njc4OQ.Abc123.xyz...
```

### 5. Configure the agent

```bash
cp config.toml.example config.toml
```

Edit `config.toml` to set your Discord channel, role restrictions, and any plugins. See `config.toml.example` for all available options.

### 6. Start the daemon

```bash
uv run disco-agent start
```

## Discord Commands

| Command | What it does |
|---------|-------------|
| `!analyze "question"` | Read-only research session |
| `!run "prompt"` | Freeform Claude session (read/write) |
| `!history [search]` | Show recent sessions |
| `!status` | Show task queue |
| `!cancel` | Cancel all active tasks |
| `!help` | Show command reference |

Plugins can register additional commands (e.g., the UE plugin adds `!build` and `!package`).

## Threads & Live Output

Every command creates a **Discord thread** on the original message. Claude's output streams into the thread in real-time via edit-in-place messages, keeping the main channel clean.

**Thread replies:** Reply in any task thread (no `!` prefix needed) to continue the conversation. Thread replies spawn a new Claude session with the full thread history as context and read/write access.

To disable threads for specific workflows, add them to `config.toml`:

```toml
[discord]
non_threaded_workflows = ["compile"]  # these fall back to channel messages
```

## How It Works

```
Discord --> Bot --> SQLite Queue <-- Daemon (polls every 10s)
                                        |
                                  Workflow Dispatcher
                                  /       |       \
                            analyze    custom    [plugins]
```

- **Analyze**: Read-only Claude Agent SDK session (tools: Read, Glob, Grep, Bash).
- **Custom**: Read/write Claude Agent SDK session (adds Edit, Write). Also handles thread replies.
- **Plugins**: Session or code plugins that register additional workflows at startup.

## Plugin System

Disco-Agent supports two types of plugins: **session plugins** and **code plugins**.

### Session plugins

Session plugins are config-only. They point a Claude Agent SDK session at an external directory (e.g., a repo with its own `.claude/commands/`). No Python code required -- just add a `[[plugins]]` block to `config.toml`:

```toml
[[plugins]]
name = "conductor"
type = "session"
path = "C:/Source/conductor-agent"
commands = ["submit"]
budget_warning_usd = 2.0
allowed_tools = ["Read", "Glob", "Grep", "Bash", "Write"]
```

Each entry in `commands` becomes a Discord `!command`. The session runs with its working directory set to `path`.

### Code plugins

Code plugins are Python modules loaded from a directory. They can define custom workflow classes with full control over execution logic. The plugin directory must contain a `workflows.py` file that uses the `@register` decorator to add workflows:

```toml
[[plugins]]
name = "ue"
type = "code"
path = "plugins/ue"

[plugin-config.ue]
engine_path = "C:/Program Files/Epic Games/UE_5.7/Engine"
project_path = "Proj/MyProject/MyProject.uproject"
```

The `[plugin-config.<name>]` section is passed to the plugin's `set_plugin_config()` function at load time.

### Adding a new plugin

1. **Session plugin**: Add a `[[plugins]]` entry with `type = "session"` to `config.toml`. Done.
2. **Code plugin**: Create a directory with a `workflows.py` that imports `@register` from `disco_agent.workflows` and registers workflow classes. Add a `[[plugins]]` entry with `type = "code"`. Optionally export a `set_plugin_config(raw_dict)` function to receive config.

## UE Plugin

The UE (Unreal Engine) plugin adds build automation commands with AI-powered error analysis and retry.

**Commands provided:**

| Command | What it does |
|---------|-------------|
| `!build ProjectName` | Compile the project via RunUAT. On failure, Claude analyzes the error and retries up to N times. |
| `!package ProjectName Win64` | Package the project (compile + cook + stage + pak). Platform defaults to Win64. |

### Quick setup

Run the `/setup-ue` slash command in Claude Code from the Disco-Agent repo root. It will interactively configure the UE plugin in your `config.toml`.

### Manual setup

Add to `config.toml`:

```toml
[[plugins]]
name = "ue"
type = "code"
path = "plugins/ue"

[plugin-config.ue]
engine_path = "C:/Program Files/Epic Games/UE_5.7/Engine"
project_path = "Proj/MyProject/MyProject.uproject"
platform = "Win64"
max_retries = 3
```

### UE source for /ue-research

To use the `/ue-research` command for API validation, clone the UE source:

```
git clone https://github.com/EpicGames/UnrealEngine.git C:/Source/UnrealEngine
```

Then set `ue_source_path` in your config:

```toml
[plugin-config.ue]
ue_source_path = "C:/Source/UnrealEngine"
```

## Budget Warnings

The agent tracks token cost per session. When a configurable threshold is exceeded, it posts a warning to Discord. It does **not** hard-stop -- you can `!cancel` manually.

Budgets are per-workflow. Built-in thresholds are set in `config.toml` under `[budgets]`:

```toml
[budgets]
analyze_warning_usd = 3.0
custom_warning_usd = 5.0
```

Plugins define their own thresholds. For example, the UE plugin uses `compile_warning_usd` and `package_warning_usd` in `[plugin-config.ue]`. Session plugins accept `budget_warning_usd` in their `[[plugins]]` block.

## Authentication

Uses your existing Claude Code CLI login (Max plan). No `ANTHROPIC_API_KEY` needed unless you prefer API-based auth.

## CLI

```bash
disco-agent start    # Run the daemon
disco-agent queue    # Show current task queue

# Explicit config path
disco-agent start --config /path/to/config.toml

# Or via environment variable
DISCO_AGENT_CONFIG=/path/to/config.toml disco-agent start
```

Resolution order: `--config` flag > `DISCO_AGENT_CONFIG` env var > CWD auto-detection.

## Running Tests

```bash
uv run pytest -v
```

## Adding New Plugins

See the [Plugin System](#plugin-system) section above. For session plugins, just add config. For code plugins, create a directory with a `workflows.py` and register your workflows with `@register("command_name")`.
