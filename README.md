# adw-agent

A daemon that automates Unreal Engine compile, package, and Conductor submission workflows, triggered by Discord commands. Uses the Claude Agent SDK for intelligent build error analysis and automated fixes.

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** package manager
- **Claude Code CLI** logged in (Max plan or API key)
- **Discord bot token** ([create one here](https://discord.com/developers/applications))
- **UE 5.x engine** installed locally (for compile/package workflows)

## Setup

### 1. Install dependencies

```bash
cd adw-agent
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

> **Updating an existing bot?** If you previously invited the bot without thread permissions, regenerate the OAuth2 URL with the full permission set above and re-authorize. This updates permissions in place — it won't duplicate the bot.

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

Edit `config.toml`:

```toml
[ue]
engine_path = "C:/Program Files/Epic Games/UE_5.3/Engine"  # your engine path
project_path = "Proj/CitySample/CitySample.uproject"

[discord]
command_channel_id = "1234567890"  # your channel ID (leave empty for any channel)
required_role = "BuildOps"         # Discord role required to use commands (leave empty to allow all)
```

### 6. Start the daemon

For development (always uses local source):

```bash
uv run ue-agent start
```

Or install globally:

```bash
uv tool install .
ue-agent start
```

**Important:** The daemon finds its config by looking for `adw-agent/` relative to your current working directory. Always run `ue-agent` from the repo root or the `adw-agent/` directory.

After code changes, the global install must be rebuilt:

```bash
cd adw-agent
uv cache clean ue-agent && uv tool install . --reinstall
```

During development, prefer `uv run ue-agent start` which always uses the local source.

## Discord Commands

| Command | What it does |
|---------|-------------|
| `!build CitySample` | Compile the project via RunUAT. On failure, Claude analyzes the error and retries up to N times. |
| `!package CitySample Win64` | Package the project (compile + cook + stage + pak). Platform defaults to Win64. |
| `!submit CitySample --dry-run` | Submit a Conductor render job using the `.claude/commands/` in conductor-agent. |
| `!analyze "why does X crash"` | Read-only research session -- Claude explores the codebase to answer your question. |
| `!run "refactor s3_upload.py"` | Freeform prompt -- Claude can read and write files in the repo. |
| `!history [search]` | Show recent sessions, or search past sessions by keyword. |
| `!status` | Show the current task queue. |
| `!cancel` | Cancel all active/pending tasks. |
| `!help` | Show command reference in Discord. |

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
                                  /   |   |   |   \
                            compile package submit analyze custom
```

- **Compile/Package**: Runs `RunUAT.bat BuildCookRun` via subprocess. If the build fails, the Claude Agent SDK analyzes the error log and attempts an automated fix, then retries (up to `max_retries`).
- **Submit**: Spins up a Claude Agent SDK session pointed at `conductor-agent/` with access to the `.claude/commands/` slash commands.
- **Analyze**: Read-only Agent SDK session against the repo (tools: Read, Glob, Grep, Bash).
- **Custom**: Read/write Agent SDK session -- essentially Discord as a Claude Code interface.

## Budget Warnings

The agent tracks token cost per session. When a configurable threshold is exceeded, it posts a warning to Discord. It does **not** hard-stop -- you can `!cancel` manually.

Thresholds are set in `config.toml` under `[budgets]`:

```toml
[budgets]
compile_warning_usd = 5.0
submit_warning_usd = 2.0
analyze_warning_usd = 3.0
custom_warning_usd = 5.0
```

## Authentication

Uses your existing Claude Code CLI login (Max plan). No `ANTHROPIC_API_KEY` needed unless you prefer API-based auth.

## CLI

```bash
ue-agent start    # Run the daemon (default)
ue-agent queue    # Show current task queue in terminal
```

## Running Tests

```bash
cd adw-agent
uv run pytest -v
```

## Adding New Workflows

1. Create `src/ue_agent/workflows/my_workflow.py`
2. Subclass `BaseWorkflow`, implement `execute()`, decorate with `@register("my_workflow")`
3. Add the Discord command in `discord_bot.py`

No changes needed to the daemon, queue, or base infrastructure.

## Project Structure

```
adw-agent/
├── pyproject.toml
├── config.toml.example
├── .env.example
├── src/ue_agent/
│   ├── daemon.py           # Entry point: poll loop + Discord bot
│   ├── discord_bot.py      # Command parsing, role auth, status posting
│   ├── queue.py            # SQLite task queue
│   ├── config.py           # TOML + .env config loading
│   ├── cost_tracker.py     # Soft budget warning tracker
│   ├── session_history.py  # Persist/query chat session history
│   ├── streaming.py        # Edit-in-place Discord message streaming
│   ├── utils.py            # Log parsing, message truncation
│   └── workflows/
│       ├── __init__.py     # Registry + @register decorator
│       ├── base.py         # BaseWorkflow ABC
│       ├── compile.py      # UE compile + AI error analysis/retry
│       ├── package.py      # UE packaging (extends compile)
│       ├── submit.py       # Conductor submission via Agent SDK
│       ├── analyze.py      # Read-only codebase research
│       └── custom.py       # Freeform prompt with write access
└── tests/
```
