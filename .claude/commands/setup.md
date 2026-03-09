---
description: Set up or extend the global ~/.disco-agent config for multi-instance deployment
---

# Setup Global Disco-Agent

Set up the `~/.disco-agent/` directory for running `disco-agent start-all`, or add a new repository plugin to an existing setup.

## Step 1: Check Existing Setup

Check whether `~/.disco-agent/` already exists and what's configured:

```bash
ls ~/.disco-agent/instances.toml 2>/dev/null
ls ~/.disco-agent/.env 2>/dev/null
ls ~/.disco-agent/instances/ 2>/dev/null
```

Read `~/.disco-agent/instances.toml` and `~/.disco-agent/.env` if they exist to understand current state.

**If nothing exists**, proceed to Step 2 (fresh setup). **If already set up**, skip to Step 3 (add repo).

## Step 2: Fresh Setup

### 2a. Create directory structure

```bash
mkdir -p ~/.disco-agent/instances
```

### 2b. Discord Bot Token

Ask the user for their Discord bot token. Create `~/.disco-agent/.env`:

```
DISCORD_BOT_TOKEN=<token from user>
```

If the user doesn't have a token yet, explain:
1. Go to https://discord.com/developers/applications
2. Create a New Application
3. Go to Bot → Reset Token → copy it
4. Under Privileged Gateway Intents, enable **Message Content Intent**
5. Go to OAuth2 → URL Generator, select `bot` scope with `Send Messages`, `Read Message History`, `Create Public Threads`, `Send Messages in Threads` permissions
6. Use the generated URL to invite the bot to their server

### 2c. Disco-Agent Root

Ask the user where the Disco-Agent repo is cloned (e.g., `C:/Github/Disco-Agent`). Verify the path contains `src/disco_agent/daemon.py`.

### 2d. Create instances.toml

Write `~/.disco-agent/instances.toml`:

```toml
disco_agent_root = "<disco-agent repo path>"
```

No `[[instances]]` entries yet — those get added in Step 3.

### 2e. Global Install

Rebuild the global install from the Disco-Agent repo:

```bash
cd <disco-agent repo path>
uv cache clean disco-agent && uv tool install . --reinstall
```

Now proceed to Step 3 to add the first repo.

## Step 3: Add a Repository

Ask the user:

1. **Repo path**: Absolute path to the repository (e.g., `C:/Github/conductor-agent`). Verify it exists.
2. **Instance name**: Short identifier for this instance (e.g., `conductor`). Must be unique across existing instances. Default: derive from the repo directory name.
3. **Discord channel ID**: The channel where this instance listens for commands. Explain how to get it: *Right-click the channel in Discord → Copy Channel ID* (requires Developer Mode enabled in Discord settings: User Settings → Advanced → Developer Mode).
4. **Plugin commands**: Check if the repo has `.claude/commands/` with markdown files. If so, list them and ask which ones to expose as Discord commands (e.g., `batch-submit`, `submit-job`). These become `!batch-submit`, `!submit-job`, etc. in Discord.
5. **Allowed tools**: Default is `["Read", "Glob", "Grep", "Bash", "Write", "Edit"]` for read/write. Ask if they want read-only (drop `Write` and `Edit`).

### 3a. Create instance config directory

```bash
mkdir -p ~/.disco-agent/instances/<name>
```

### 3b. Write instance config.toml

Write `~/.disco-agent/instances/<name>/config.toml`:

```toml
[general]
poll_interval_seconds = 10
db_path = "tasks.db"
repo_root = "<repo path>"

[discord]
command_channel_id = "<channel id from user>"
required_role = "BuildOps"
non_threaded_workflows = []

[budgets]
analyze_warning_usd = 3.0
custom_warning_usd = 5.0
```

If plugin commands were found in Step 3.4, also append a session plugin block:

```toml
[[plugins]]
name = "<instance name>"
type = "session"
path = "<repo path>"
commands = [<list of command names>]
budget_warning_usd = 5.0
allowed_tools = [<chosen tools>]
```

### 3c. Add instance to instances.toml

Append to `~/.disco-agent/instances.toml`:

```toml
[[instances]]
name = "<name>"
config = "instances/<name>/config.toml"
```

## Step 4: Verify & Report

1. Read back `~/.disco-agent/instances.toml` to confirm all instances are listed.
2. For each instance, read its `config.toml` and verify the channel ID is set.
3. Check that `~/.disco-agent/.env` has a `DISCORD_BOT_TOKEN` value (not empty/placeholder).

Report the final setup to the user with:
- Number of instances configured
- For each: name, repo path, channel ID, available commands (`!analyze`, `!run`, plus any plugin commands)
- How to start: `disco-agent start-all`
- How to check status: `disco-agent status`
- How to stop: `disco-agent stop-all`
- How to install as a service: `disco-agent install-service`
