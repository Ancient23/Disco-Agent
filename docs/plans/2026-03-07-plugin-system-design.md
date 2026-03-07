# Disco-Agent: Plugin System & Rename Design

**Date:** 2026-03-07
**Status:** Approved

## Summary

Transform the repo from a UE-specific build agent into a general-purpose Discord-to-Claude automation daemon. Rename the package from `ue-agent` to `disco-agent`, extract all domain-specific workflows into a plugin system, and keep only generic workflows (analyze, custom) in core.

## Architecture

### Core daemon (always available)

- `analyze` — read-only Claude session against the repo
- `custom` / `run` — read-write Claude session against the repo
- `status`, `cancel`, `history`, `help` — queue management

### Plugin system

Two plugin types, both configured in `config.toml`:

**Session plugins** — config-only, no Python. Spawn a Claude session in an external repo that has its own `.claude/commands/`.

```toml
[[plugins]]
name = "conductor"
type = "session"
path = "C:/Source/conductor-agent"
commands = ["submit"]
budget_warning_usd = 2.0
allowed_tools = ["Read", "Glob", "Grep", "Bash", "Write"]
```

**Code plugins** — Python files with `@register` workflows loaded from a local directory.

```toml
[[plugins]]
name = "ue"
type = "code"
path = "plugins/ue"

[plugins.ue]
engine_path = "C:/Program Files/Epic Games/UE_5.7/Engine"
project_path = "Proj/MyProject/MyProject.uproject"
platform = "Win64"
build_flags = ["-cook", "-stage", "-pak", "-unattended", "-nullrhi"]
max_retries = 3
error_tail_lines = 200
ue_source_path = ""
```

### Plugin loading (at startup)

`plugins.py`:
1. Read `[[plugins]]` array from config
2. For `type = "session"`: dynamically create a workflow class (subclass of `AgentSessionWorkflow`) and register it for each command name
3. For `type = "code"`: `importlib.import_module` on `workflows.py` at the given path, triggering `@register` decorators
4. Plugin-specific config sections (`[plugins.ue]`) passed to code plugins as a dict

Conflict detection: if two plugins register the same command name, fail at startup with a clear error.

### AgentSessionWorkflow

New base class in `workflows/session.py` that handles the "spawn Claude in a directory" pattern. Extracts common logic from the current submit/analyze/custom workflows:

```python
class AgentSessionWorkflow(BaseWorkflow):
    """Workflow that delegates to a Claude Agent SDK session."""

    def __init__(self, *, cwd, allowed_tools, budget_warning_usd, **kwargs):
        ...

    async def execute(self) -> WorkflowResult:
        # prompt construction, SDK streaming, cost tracking, session history
        ...
```

Session plugins use this automatically. Code plugins can subclass it or use `BaseWorkflow` directly.

### Discord command routing

- Built-in commands (`!analyze`, `!run`, `!status`, `!cancel`, `!history`, `!help`) hardcoded
- Plugin commands registered dynamically from `[[plugins]]` config
- `!command` matching checks plugin registry after built-ins

## Package rename

- `src/ue_agent/` -> `src/disco_agent/`
- Package name: `disco-agent`
- CLI: `disco-agent start`, `disco-agent queue`
- Entry point: `disco-agent = "disco_agent.daemon:main"`
- All internal imports: `from ue_agent.` -> `from disco_agent.`

## File changes

### Removed from core

- `workflows/compile.py` -> `plugins/ue/workflows.py`
- `workflows/package.py` -> `plugins/ue/workflows.py`
- `workflows/submit.py` -> deleted (replaced by session plugin config)
- `UEConfig`, `CompileConfig`, `ConductorConfig` removed from `config.py`
- `[ue]`, `[conductor]`, `[compile]` sections removed from core config
- `compile_warning_usd`, `package_warning_usd`, `submit_warning_usd` removed from core budgets

### New files

- `src/disco_agent/plugins.py` — plugin loader
- `src/disco_agent/workflows/session.py` — `AgentSessionWorkflow` base class
- `plugins/ue/workflows.py` — UE compile/package workflows
- `plugins/ue/config.py` — UE plugin config dataclass
- `plugins/ue/commands/ue-research.md` — updated slash command (configurable UE source path, auto-discovered repo source locations)
- `.claude/commands/setup-ue.md` — interactive setup: detects engine path, sets ue_source_path, finds .uproject, writes plugin config

### Final directory structure

```
Disco-Agent/
├── src/disco_agent/
│   ├── daemon.py
│   ├── discord_bot.py
│   ├── plugins.py
│   ├── queue.py
│   ├── config.py
│   ├── cost_tracker.py
│   ├── session_history.py
│   ├── streaming.py
│   ├── utils.py
│   └── workflows/
│       ├── __init__.py
│       ├── base.py
│       ├── session.py
│       ├── analyze.py
│       └── custom.py
├── plugins/
│   └── ue/
│       ├── workflows.py
│       ├── config.py
│       └── commands/
│           └── ue-research.md
├── .claude/commands/
│   └── setup-ue.md
├── tests/
├── docs/plans/
├── pyproject.toml
├── config.toml.example
├── .env.example
└── README.md
```

## Config changes

`config.toml.example`:

```toml
[general]
poll_interval_seconds = 10
db_path = "tasks.db"
# repo_root = "C:/Source/my-project"

[discord]
command_channel_id = ""
required_role = "BuildOps"
non_threaded_workflows = []

[budgets]
analyze_warning_usd = 3.0
custom_warning_usd = 5.0

# --- Plugins ---

# Session plugin (external repo with slash commands):
# [[plugins]]
# name = "conductor"
# type = "session"
# path = "C:/Source/conductor-agent"
# commands = ["submit"]
# budget_warning_usd = 2.0
# allowed_tools = ["Read", "Glob", "Grep", "Bash", "Write"]

# Code plugin (UE build automation):
# [[plugins]]
# name = "ue"
# type = "code"
# path = "plugins/ue"
#
# [plugins.ue]
# engine_path = "C:/Program Files/Epic Games/UE_5.7/Engine"
# project_path = "Proj/MyProject/MyProject.uproject"
# platform = "Win64"
# build_flags = ["-cook", "-stage", "-pak", "-unattended", "-nullrhi"]
# max_retries = 3
# error_tail_lines = 200
# ue_source_path = ""
```

## UE plugin: ue-research command

- UE source path read from `ue_source_path` in `[plugins.ue]` config, substituted into the command template as `$UE_SOURCE_PATH`
- Repo source locations auto-discovered: scans for `*.Build.cs`, `Source/` directories, `.uproject` files
- All UE version references default to 5.7

## UE plugin: setup-ue slash command

`.claude/commands/setup-ue.md` interactively walks the user through:
1. Detecting UE engine install path
2. Setting `ue_source_path` (optional, for ue-research)
3. Finding `.uproject` file
4. Writing the `[[plugins]]` and `[plugins.ue]` entries into `config.toml`

## Tests

- All imports updated for `disco_agent`
- `test_config.py` updated to remove UE/conductor config tests from core
- New tests for plugin loading (session and code types, conflict detection)
- Existing compile/package tests adapt for plugin context
