# Plugin System & Rename Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform ue-agent into disco-agent: a general-purpose Discord-to-Claude daemon with a plugin system for domain-specific workflows.

**Architecture:** Core daemon provides analyze/custom workflows and queue management. Plugins (configured in `config.toml`) add domain-specific Discord commands — either as "session" plugins (config-only, spawn Claude in an external repo) or "code" plugins (Python workflow classes loaded from a local directory). The UE compile/package workflows move out of core into a bundled UE plugin.

**Tech Stack:** Python 3.11+, asyncio, discord.py, aiosqlite, claude-agent-sdk, tomllib, pytest + pytest-asyncio

---

### Task 1: Rename package — `ue_agent` to `disco_agent`

This is a mechanical rename. Do it first so all subsequent work is on the new names.

**Files:**
- Rename: `src/ue_agent/` -> `src/disco_agent/`
- Modify: `pyproject.toml`
- Modify: all `tests/*.py` files (import paths)
- Modify: `src/disco_agent/*.py` (internal imports)
- Modify: `src/disco_agent/workflows/*.py` (internal imports)

**Step 1: Rename the source directory**

```bash
cd C:/Source/Disco-Agent && mv src/ue_agent src/disco_agent
```

**Step 2: Update pyproject.toml**

Change:
```toml
[project]
name = "disco-agent"
description = "Discord-to-Claude automation daemon with plugin system"

[project.scripts]
disco-agent = "disco_agent.daemon:main"

[tool.hatch.build.targets.wheel]
packages = ["src/disco_agent"]
```

**Step 3: Find-and-replace imports in all source files**

In every `.py` file under `src/disco_agent/` and `tests/`:
- Replace `from ue_agent.` with `from disco_agent.`
- Replace `import ue_agent.` with `import disco_agent.`
- Replace `ue_agent` logger names with `disco_agent` (e.g., `logging.getLogger("ue_agent")` -> `logging.getLogger("disco_agent")`)

Files to update (source — all internal imports):
- `src/disco_agent/daemon.py` — lines 9-19 imports, line 21 logger, lines 147/151/156 `ue_agent` dir references, line 181 usage string, line 184-188 env var name `UE_AGENT_CONFIG` -> `DISCO_AGENT_CONFIG`
- `src/disco_agent/discord_bot.py` — lines 8-12 imports
- `src/disco_agent/workflows/base.py` — lines 8-9 imports
- `src/disco_agent/workflows/analyze.py` — lines 10-15 imports
- `src/disco_agent/workflows/custom.py` — lines 10-15 imports
- `src/disco_agent/workflows/compile.py` — lines 11-16 imports
- `src/disco_agent/workflows/package.py` — lines 5-9 imports
- `src/disco_agent/workflows/submit.py` — lines 10-14 imports
- `src/disco_agent/session_history.py` — no imports to change, but the `adw-agent` reference in `get_history_dir` (line 26) should change to just `chat_history` (history dir relative to repo root, not nested in a subdir)

Files to update (tests — all imports):
- `tests/test_config.py` — lines 41, 69, 78, 98, 112: `ue_agent.config` -> `disco_agent.config`
- `tests/test_discord_bot.py` — lines 3, 83: `ue_agent.discord_bot` -> `disco_agent.discord_bot`
- `tests/test_workflows.py` — lines 3-4, 52, 103, 117-121: `ue_agent.workflows` -> `disco_agent.workflows`, `ue_agent.config` -> `disco_agent.config`
- `tests/test_compile.py` — lines 6, 46-47, 69-70, 107-108, 135: `ue_agent.` -> `disco_agent.`
- `tests/test_queue.py` — line 8: `ue_agent.queue` -> `disco_agent.queue`
- `tests/test_streaming.py` — line 4: `ue_agent.streaming` -> `disco_agent.streaming`
- `tests/test_session_history.py` — lines 5-13, 144, 150, 158: `ue_agent.` -> `disco_agent.`
- `tests/test_cost_tracker.py` — line 3: `ue_agent.cost_tracker` -> `disco_agent.cost_tracker`
- `tests/test_thread_replies.py` — line 5: `ue_agent.discord_bot` -> `disco_agent.discord_bot`
- `tests/conftest.py` — line 7: `ue_agent.queue` -> `disco_agent.queue`

**Step 4: Update daemon.py auto-detect references**

In `daemon.py`, the `_find_repo_root()` function references `adw-agent/` and `ue_agent` directory names. Simplify to look for `src/disco_agent` and the `Disco-Agent` directory name:

```python
def _find_repo_root() -> Path:
    cwd = Path.cwd()
    # cwd is the Disco-Agent directory itself
    if (cwd / "pyproject.toml").exists() and (cwd / "src" / "disco_agent").exists():
        return cwd
    # Fallback: assume cwd is repo root
    return cwd
```

Also update the usage string:
```python
print("Usage: disco-agent [start|queue] [--config PATH]")
```

And the env var fallback:
```python
env_config = os.environ.get("DISCO_AGENT_CONFIG", "")
```

And in `main()`, the auto-detect path for config:
```python
# Auto-detect: look for config.toml in CWD
repo_root = _find_repo_root()
config_dir = repo_root
config = load_config(
    config_path=config_dir / "config.toml",
    env_path=config_dir / ".env",
)
```

**Step 5: Update session_history.py**

Change `get_history_dir` to not reference `adw-agent`:
```python
def get_history_dir(repo_root: str) -> str:
    return str(Path(repo_root) / "chat_history")
```

**Step 6: Run tests to verify rename is clean**

```bash
cd C:/Source/Disco-Agent && uv run pytest -v
```

Expected: All existing tests pass with new import paths.

**Step 7: Commit**

```bash
git add -A && git commit -m "refactor: rename package from ue-agent to disco-agent"
```

---

### Task 2: Slim down core config — remove UE/Conductor/Compile sections

**Files:**
- Modify: `src/disco_agent/config.py`
- Modify: `tests/test_config.py`
- Modify: `config.toml.example`
- Modify: `.env.example`

**Step 1: Write failing test — config loads without UE/conductor/compile sections**

Add to `tests/test_config.py`:

```python
def test_load_config_minimal(tmp_path):
    """Core config should work with only general/discord/budgets sections."""
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("""
[general]
poll_interval_seconds = 10

[discord]
command_channel_id = "123"

[budgets]
analyze_warning_usd = 3.0
custom_warning_usd = 5.0
""")
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_BOT_TOKEN=tok\n")

    from disco_agent.config import load_config
    config = load_config(config_path=config_toml, env_path=env_file)
    assert config.general.poll_interval_seconds == 10
    assert config.discord.command_channel_id == "123"
    assert config.budgets.analyze_warning_usd == 3.0
    assert not hasattr(config, 'ue')
    assert not hasattr(config, 'conductor')
    assert not hasattr(config, 'compile')


def test_config_has_plugins_raw(tmp_path):
    """Config should expose raw TOML data for plugins."""
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("""
[general]
[discord]
[budgets]

[[plugins]]
name = "test-plugin"
type = "session"
path = "/tmp/test"
commands = ["test"]
budget_warning_usd = 1.0
allowed_tools = ["Read"]
""")
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_BOT_TOKEN=tok\n")

    from disco_agent.config import load_config
    config = load_config(config_path=config_toml, env_path=env_file)
    assert len(config.plugins_raw) == 1
    assert config.plugins_raw[0]["name"] == "test-plugin"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_config.py::test_load_config_minimal -v
```

Expected: FAIL (config still has `ue`, `conductor`, `compile` attrs)

**Step 3: Update config.py — remove UE/Conductor/Compile, add plugins_raw**

Rewrite `config.py`:

```python
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GeneralConfig:
    poll_interval_seconds: int = 10
    db_path: str = "tasks.db"
    repo_root: str = ""


@dataclass
class DiscordConfig:
    bot_token: str = ""
    command_channel_id: str = ""
    required_role: str = "BuildOps"
    non_threaded_workflows: list[str] = field(default_factory=list)


@dataclass
class BudgetConfig:
    analyze_warning_usd: float = 3.0
    custom_warning_usd: float = 5.0


@dataclass
class AgentConfig:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    budgets: BudgetConfig = field(default_factory=BudgetConfig)
    plugins_raw: list[dict[str, Any]] = field(default_factory=list)
    plugin_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    _raw: dict[str, Any] = field(default_factory=dict)


def _apply_section(target, data: dict) -> None:
    for key, value in data.items():
        if hasattr(target, key):
            current = getattr(target, key)
            if isinstance(current, Path):
                setattr(target, key, Path(value))
            else:
                setattr(target, key, value)


def load_config(
    config_path: str | Path = "config.toml",
    env_path: str | Path = ".env",
) -> AgentConfig:
    config = AgentConfig()

    config_path = Path(config_path)
    if config_path.exists():
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
        config._raw = raw
        if "general" in raw:
            _apply_section(config.general, raw["general"])
        if "discord" in raw:
            _apply_section(config.discord, raw["discord"])
        if "budgets" in raw:
            _apply_section(config.budgets, raw["budgets"])
        config.plugins_raw = raw.get("plugins", [])
        # Collect [plugins.<name>] sections
        if "plugins" in raw and isinstance(raw.get("plugins"), dict):
            # TOML: [[plugins]] is a list, [plugins.x] is a dict — tomllib merges
            pass
        for key, val in raw.items():
            if key.startswith("plugins.") or (key == "plugins" and isinstance(val, dict)):
                pass
        # Plugin-specific config: [plugins.<name>] sections
        config.plugin_configs = {
            k.split(".", 1)[1]: v
            for k, v in raw.items()
            if k.startswith("plugins.") and isinstance(v, dict)
        }

    env_path = Path(env_path)
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        raise ValueError("DISCORD_BOT_TOKEN must be set in .env or environment")
    config.discord.bot_token = token

    return config
```

Note: TOML `[[plugins]]` produces a list at `raw["plugins"]`. Separate `[plugins.ue]` sections produce `raw["plugins"]["ue"]` as a nested dict. However, tomllib merges `[[plugins]]` (array) and `[plugins.ue]` (table) — this is actually a TOML conflict. We need a different key for plugin-specific config.

**TOML disambiguation:** Use `[plugin-config.ue]` instead of `[plugins.ue]` to avoid TOML key conflict:

```toml
[[plugins]]
name = "ue"
type = "code"
path = "plugins/ue"

[plugin-config.ue]
engine_path = "C:/Program Files/Epic Games/UE_5.7/Engine"
```

Update `config.py` to read `plugin_configs` from `raw.get("plugin-config", {})`:

```python
config.plugin_configs = raw.get("plugin-config", {})
```

**Step 4: Update existing config tests**

Remove UE/conductor/compile references from `test_load_config_from_toml` and `test_load_config_defaults`. The test for `non_threaded_workflows` stays. Update `test_load_config_missing_token_raises` to use minimal TOML.

```python
def test_load_config_from_toml(tmp_path):
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("""
[general]
poll_interval_seconds = 15
db_path = "my_tasks.db"

[discord]
command_channel_id = "123456"
required_role = "Builders"

[budgets]
analyze_warning_usd = 10.0
custom_warning_usd = 5.0
""")
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_BOT_TOKEN=test-token-123\n")

    from disco_agent.config import load_config
    config = load_config(config_path=config_toml, env_path=env_file)
    assert config.general.poll_interval_seconds == 15
    assert config.general.db_path == "my_tasks.db"
    assert config.discord.command_channel_id == "123456"
    assert config.discord.required_role == "Builders"
    assert config.discord.bot_token == "test-token-123"
    assert config.budgets.analyze_warning_usd == 10.0


def test_load_config_defaults(tmp_path):
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("[general]\n[discord]\n[budgets]\n")
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_BOT_TOKEN=tok\n")

    from disco_agent.config import load_config
    config = load_config(config_path=config_toml, env_path=env_file)
    assert config.general.poll_interval_seconds == 10
    assert config.budgets.analyze_warning_usd == 3.0


def test_load_config_missing_token_raises(tmp_path):
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("[general]\n[discord]\n[budgets]\n")
    env_file = tmp_path / ".env"
    env_file.write_text("")

    os.environ.pop("DISCORD_BOT_TOKEN", None)

    from disco_agent.config import load_config
    with pytest.raises(ValueError, match="DISCORD_BOT_TOKEN"):
        load_config(config_path=config_toml, env_path=env_file)
```

**Step 5: Update config.toml.example**

```toml
[general]
poll_interval_seconds = 10
db_path = "tasks.db"
# Optional: explicit repo root for Claude sessions (auto-detected from CWD if omitted)
# repo_root = "C:/Source/my-project"

[discord]
command_channel_id = ""
required_role = "BuildOps"
# Workflows that reply directly in the channel instead of creating a thread
non_threaded_workflows = []

[budgets]
analyze_warning_usd = 3.0
custom_warning_usd = 5.0

# --- Plugins ---
# See README.md for full plugin documentation.

# Session plugin example (external repo with its own .claude/commands/):
# [[plugins]]
# name = "conductor"
# type = "session"
# path = "C:/Source/conductor-agent"
# commands = ["submit"]
# budget_warning_usd = 2.0
# allowed_tools = ["Read", "Glob", "Grep", "Bash", "Write"]

# Code plugin example (UE build automation):
# [[plugins]]
# name = "ue"
# type = "code"
# path = "plugins/ue"
#
# [plugin-config.ue]
# engine_path = "C:/Program Files/Epic Games/UE_5.7/Engine"
# project_path = "Proj/MyProject/MyProject.uproject"
# platform = "Win64"
# build_flags = ["-cook", "-stage", "-pak", "-unattended", "-nullrhi"]
# max_retries = 3
# error_tail_lines = 200
# ue_source_path = ""
```

**Step 6: Update .env.example**

Remove conductor S3 references:
```
DISCORD_BOT_TOKEN=your-discord-bot-token-here
```

**Step 7: Run tests**

```bash
uv run pytest tests/test_config.py -v
```

Expected: All pass.

**Step 8: Commit**

```bash
git add -A && git commit -m "refactor: slim core config, remove UE/conductor/compile sections"
```

---

### Task 3: Create AgentSessionWorkflow base class

**Files:**
- Create: `src/disco_agent/workflows/session.py`
- Create: `tests/test_session_workflow.py`

**Step 1: Write failing test**

Create `tests/test_session_workflow.py`:

```python
from unittest.mock import AsyncMock, patch
import pytest

from disco_agent.workflows.session import AgentSessionWorkflow


@pytest.fixture
def task():
    return {
        "id": 1,
        "workflow": "test-session",
        "project": "TestProj",
        "platform": "",
        "params": '{"prompt": "do something"}',
        "status": "running",
        "discord_channel_id": "chan1",
        "discord_message_id": "msg1",
        "requested_by": "user1",
    }


async def test_session_workflow_runs_sdk_query(task):
    from claude_agent_sdk.types import ResultMessage

    mock_result = ResultMessage(
        type="result",
        subtype="",
        result="session output",
        session_id="s1",
        total_cost_usd=0.25,
    )

    async def fake_query(prompt, options):
        yield mock_result

    queue = AsyncMock()
    notifier = AsyncMock()

    wf = AgentSessionWorkflow(
        task=task,
        queue=queue,
        notifier=notifier,
        session_cwd="/tmp/test-repo",
        allowed_tools=["Read", "Glob"],
        budget_warning_usd=5.0,
        repo_root="/tmp",
    )

    with patch("disco_agent.workflows.session.query", side_effect=fake_query):
        result = await wf.execute()

    assert result.success is True
    assert result.output == "session output"
    assert result.cost_usd == 0.25


async def test_session_workflow_uses_configured_tools(task):
    """Verify allowed_tools are passed to the SDK."""
    captured_options = {}

    async def capture_query(prompt, options):
        captured_options["allowed_tools"] = options.allowed_tools
        # yield nothing — empty session
        return
        yield  # make it a generator

    queue = AsyncMock()
    notifier = AsyncMock()

    wf = AgentSessionWorkflow(
        task=task,
        queue=queue,
        notifier=notifier,
        session_cwd="/tmp/repo",
        allowed_tools=["Read", "Bash"],
        budget_warning_usd=5.0,
        repo_root="/tmp",
    )

    with patch("disco_agent.workflows.session.query", side_effect=capture_query):
        await wf.execute()

    assert captured_options["allowed_tools"] == ["Read", "Bash"]
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_session_workflow.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'disco_agent.workflows.session'`

**Step 3: Implement AgentSessionWorkflow**

Create `src/disco_agent/workflows/session.py`:

```python
from __future__ import annotations

import json
import logging
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from disco_agent.cost_tracker import CostTracker
from disco_agent.queue import TaskQueue
from disco_agent.session_history import get_history_dir, inject_history_context, save_session
from disco_agent.workflows.base import BaseWorkflow, Notifier, WorkflowResult

logger = logging.getLogger(__name__)


class AgentSessionWorkflow(BaseWorkflow):
    """Workflow that delegates to a Claude Agent SDK session in a given directory."""

    def __init__(
        self,
        task: dict[str, Any],
        queue: TaskQueue,
        notifier: Notifier,
        session_cwd: str,
        allowed_tools: list[str],
        budget_warning_usd: float,
        repo_root: str,
    ):
        super().__init__(task=task, queue=queue, notifier=notifier)
        self.session_cwd = session_cwd
        self.allowed_tools = allowed_tools
        self.cost_tracker = CostTracker(budget_warning_usd)
        self.repo_root = repo_root
        self.history_dir = get_history_dir(repo_root)

    async def execute(self) -> WorkflowResult:
        params = json.loads(self.task["params"]) if isinstance(self.task["params"], str) else self.task["params"]
        prompt = params.get("prompt", "")

        if not prompt:
            return WorkflowResult(success=False, error="No prompt provided")

        full_prompt = inject_history_context(
            prompt,
            instruction="Execute the following request:",
            history_dir=self.history_dir,
        )

        stream = self._create_stream()
        sdk_output = ""
        async for message in query(
            prompt=full_prompt,
            options=ClaudeAgentOptions(
                allowed_tools=self.allowed_tools,
                cwd=self.session_cwd,
                permission_mode="bypassPermissions",
            ),
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock) and stream:
                        await stream.append(block.text)
                    elif isinstance(block, ToolUseBlock) and stream:
                        await stream.append_tool_use(block.name, block.input)
            elif isinstance(message, ResultMessage):
                if message.total_cost_usd is not None:
                    for w in self.cost_tracker.add_cost(message.total_cost_usd):
                        await self._send_update(w)
                if message.result:
                    sdk_output = message.result

        if stream:
            await stream.finalize()

        save_session(
            task_id=self.task_id,
            workflow=self.task["workflow"],
            prompt=prompt,
            output=sdk_output,
            cost_usd=self.cost_tracker.total_cost_usd,
            requested_by=self.task.get("requested_by", ""),
            discord_channel_id=self.channel_id,
            history_dir=self.history_dir,
        )

        return WorkflowResult(
            success=True,
            output=sdk_output,
            cost_usd=self.cost_tracker.total_cost_usd,
        )
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_session_workflow.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: add AgentSessionWorkflow base class for session-based plugins"
```

---

### Task 4: Create plugin loader

**Files:**
- Create: `src/disco_agent/plugins.py`
- Create: `tests/test_plugins.py`

**Step 1: Write failing tests**

Create `tests/test_plugins.py`:

```python
import pytest
from unittest.mock import AsyncMock

from disco_agent.plugins import load_plugins
from disco_agent.workflows import WORKFLOW_REGISTRY


@pytest.fixture(autouse=True)
def clean_registry():
    """Remove any test-registered workflows after each test."""
    before = set(WORKFLOW_REGISTRY.keys())
    yield
    for key in set(WORKFLOW_REGISTRY.keys()) - before:
        del WORKFLOW_REGISTRY[key]


def test_load_session_plugin_registers_commands():
    plugins_raw = [
        {
            "name": "test-session",
            "type": "session",
            "path": "/tmp/fake-repo",
            "commands": ["deploy", "rollback"],
            "budget_warning_usd": 2.0,
            "allowed_tools": ["Read", "Bash"],
        }
    ]

    load_plugins(plugins_raw, plugin_configs={}, config_dir=".")

    assert "deploy" in WORKFLOW_REGISTRY
    assert "rollback" in WORKFLOW_REGISTRY


def test_load_code_plugin(tmp_path):
    plugin_dir = tmp_path / "my_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "workflows.py").write_text("""
from disco_agent.workflows import register
from disco_agent.workflows.base import BaseWorkflow, WorkflowResult

@register("my_cmd")
class MyWorkflow(BaseWorkflow):
    async def execute(self):
        return WorkflowResult(success=True, output="ok")
""")

    plugins_raw = [
        {
            "name": "my-plugin",
            "type": "code",
            "path": str(plugin_dir),
        }
    ]

    load_plugins(plugins_raw, plugin_configs={}, config_dir=".")

    assert "my_cmd" in WORKFLOW_REGISTRY


def test_duplicate_command_raises():
    plugins_raw = [
        {
            "name": "plugin-a",
            "type": "session",
            "path": "/tmp/a",
            "commands": ["deploy"],
            "budget_warning_usd": 1.0,
            "allowed_tools": ["Read"],
        },
        {
            "name": "plugin-b",
            "type": "session",
            "path": "/tmp/b",
            "commands": ["deploy"],
            "budget_warning_usd": 1.0,
            "allowed_tools": ["Read"],
        },
    ]

    with pytest.raises(ValueError, match="deploy.*already registered"):
        load_plugins(plugins_raw, plugin_configs={}, config_dir=".")


def test_session_plugin_workflow_has_correct_cwd():
    plugins_raw = [
        {
            "name": "test",
            "type": "session",
            "path": "/tmp/my-repo",
            "commands": ["mycmd"],
            "budget_warning_usd": 3.0,
            "allowed_tools": ["Read", "Glob"],
        }
    ]

    load_plugins(plugins_raw, plugin_configs={}, config_dir=".")

    # Instantiate the dynamically created workflow class
    cls = WORKFLOW_REGISTRY["mycmd"]
    task = {
        "id": 1, "workflow": "mycmd", "project": "", "platform": "",
        "params": '{"prompt": "test"}', "status": "running",
        "discord_channel_id": "c", "discord_message_id": "m",
        "requested_by": "u",
    }
    wf = cls(task=task, queue=AsyncMock(), notifier=AsyncMock(), repo_root="/tmp")
    assert wf.session_cwd == "/tmp/my-repo"
    assert wf.allowed_tools == ["Read", "Glob"]


def test_no_plugins_is_fine():
    load_plugins([], plugin_configs={}, config_dir=".")
    # no error


def test_plugin_config_passed_to_code_plugin(tmp_path):
    """Code plugins receive their config section."""
    plugin_dir = tmp_path / "cfg_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "workflows.py").write_text("""
from disco_agent.workflows import register
from disco_agent.workflows.base import BaseWorkflow, WorkflowResult

@register("cfg_cmd")
class CfgWorkflow(BaseWorkflow):
    async def execute(self):
        return WorkflowResult(success=True)
""")

    plugins_raw = [{"name": "cfg", "type": "code", "path": str(plugin_dir)}]
    plugin_configs = {"cfg": {"some_key": "some_value"}}

    result = load_plugins(plugins_raw, plugin_configs=plugin_configs, config_dir=".")
    assert result["cfg"]["some_key"] == "some_value"
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_plugins.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'disco_agent.plugins'`

**Step 3: Implement plugins.py**

Create `src/disco_agent/plugins.py`:

```python
from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from disco_agent.workflows import WORKFLOW_REGISTRY
from disco_agent.workflows.session import AgentSessionWorkflow

logger = logging.getLogger(__name__)


def _make_session_workflow_class(
    command_name: str,
    session_cwd: str,
    allowed_tools: list[str],
    budget_warning_usd: float,
) -> type:
    """Dynamically create a workflow class for a session plugin command."""

    class _SessionPluginWorkflow(AgentSessionWorkflow):
        def __init__(self, task, queue, notifier, repo_root, **kwargs):
            super().__init__(
                task=task,
                queue=queue,
                notifier=notifier,
                session_cwd=session_cwd,
                allowed_tools=allowed_tools,
                budget_warning_usd=budget_warning_usd,
                repo_root=repo_root,
            )

    _SessionPluginWorkflow.__name__ = f"SessionPlugin_{command_name}"
    _SessionPluginWorkflow.__qualname__ = f"SessionPlugin_{command_name}"
    return _SessionPluginWorkflow


def _load_session_plugin(plugin: dict[str, Any]) -> list[str]:
    """Register session plugin commands. Returns list of registered command names."""
    commands = plugin.get("commands", [])
    path = plugin["path"]
    allowed_tools = plugin.get("allowed_tools", ["Read", "Glob", "Grep", "Bash"])
    budget = plugin.get("budget_warning_usd", 5.0)

    registered = []
    for cmd in commands:
        if cmd in WORKFLOW_REGISTRY:
            raise ValueError(
                f"Command '{cmd}' already registered — "
                f"plugin '{plugin['name']}' conflicts with an existing workflow"
            )
        cls = _make_session_workflow_class(cmd, path, allowed_tools, budget)
        WORKFLOW_REGISTRY[cmd] = cls
        registered.append(cmd)
        logger.info("Registered session plugin command: !%s -> %s", cmd, path)

    return registered


def _load_code_plugin(plugin: dict[str, Any], config_dir: str) -> None:
    """Load a code plugin by importing its workflows.py module."""
    plugin_path = Path(plugin["path"])
    if not plugin_path.is_absolute():
        plugin_path = Path(config_dir) / plugin_path

    workflows_file = plugin_path / "workflows.py"
    if not workflows_file.exists():
        raise FileNotFoundError(
            f"Code plugin '{plugin['name']}': {workflows_file} not found"
        )

    module_name = f"disco_agent_plugin_{plugin['name'].replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, str(workflows_file))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    logger.info("Loaded code plugin '%s' from %s", plugin["name"], workflows_file)


def load_plugins(
    plugins_raw: list[dict[str, Any]],
    plugin_configs: dict[str, dict[str, Any]],
    config_dir: str,
) -> dict[str, dict[str, Any]]:
    """Load all plugins from config. Returns plugin_configs for downstream use."""
    for plugin in plugins_raw:
        ptype = plugin.get("type", "session")
        name = plugin.get("name", "unnamed")

        if ptype == "session":
            _load_session_plugin(plugin)
        elif ptype == "code":
            _load_code_plugin(plugin, config_dir)
        else:
            logger.warning("Unknown plugin type '%s' for plugin '%s'", ptype, name)

    return plugin_configs
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_plugins.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: add plugin loader for session and code plugins"
```

---

### Task 5: Rewire daemon and discord_bot for plugins

**Files:**
- Modify: `src/disco_agent/daemon.py`
- Modify: `src/disco_agent/discord_bot.py`

**Step 1: Update daemon.py**

Remove all UE-specific workflow imports and the `_build_workflow` function. Replace with plugin loading and a generic workflow builder.

Key changes:
- Remove: `import disco_agent.workflows.compile`, `import disco_agent.workflows.package`, `import disco_agent.workflows.submit`
- Keep: `import disco_agent.workflows.analyze`, `import disco_agent.workflows.custom`
- Add: `from disco_agent.plugins import load_plugins`
- Replace `_build_workflow` with a generic version that works for all workflow types
- Call `load_plugins()` in `main()` after loading config

The generic `_build_workflow`:

```python
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
        # Code plugins may take additional kwargs — try generic approach
        return cls(
            task=task,
            queue=queue,
            notifier=notifier,
            repo_root=repo_root,
        )
```

In `main()`, after loading config, add:

```python
from disco_agent.plugins import load_plugins
load_plugins(config.plugins_raw, config.plugin_configs, str(config_dir))
```

**Step 2: Update discord_bot.py**

Remove hardcoded `!build`, `!package`, `!submit` command parsing. Replace with dynamic plugin command routing.

Change `parse_command`:
- Keep `!analyze`, `!run`, `!status`, `!cancel`, `!history`, `!help` as built-ins
- For any other `!command`, check if the command name (minus `!`) exists in `WORKFLOW_REGISTRY`. If so, parse arguments generically:

```python
from disco_agent.workflows import WORKFLOW_REGISTRY

# ... after all built-in checks, at the end of parse_command:

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
```

Update `__help` to dynamically list plugin commands:

```python
# Build dynamic command list
plugin_cmds = [
    name for name in WORKFLOW_REGISTRY
    if name not in ("analyze", "custom")
]
plugin_lines = "\n".join(f"!{cmd:<28s} (plugin)" for cmd in sorted(plugin_cmds))
```

**Step 3: Run full test suite**

```bash
uv run pytest -v
```

Expected: All tests pass. The `test_discord_bot.py` tests for `!build`, `!package`, `!submit` will now fail — update them in the next step.

**Step 4: Update discord_bot tests**

In `tests/test_discord_bot.py`:
- Remove `test_parse_build_command`, `test_parse_package_command`, `test_parse_package_default_platform`, `test_parse_submit_command`, `test_parse_build_missing_project` — these are now plugin responsibilities
- Add test for dynamic plugin command routing:

```python
def test_parse_dynamic_plugin_command():
    """A command matching a registered workflow should parse dynamically."""
    from disco_agent.workflows import WORKFLOW_REGISTRY
    from disco_agent.workflows.base import BaseWorkflow, WorkflowResult

    # Register a fake plugin command
    class FakeWorkflow(BaseWorkflow):
        async def execute(self):
            return WorkflowResult(success=True)

    WORKFLOW_REGISTRY["deploy"] = FakeWorkflow
    try:
        cmd = parse_command("!deploy my-app --region us-east-1")
        assert cmd is not None
        assert cmd["workflow"] == "deploy"
        assert cmd["project"] == "my-app"
        assert "--region us-east-1" in cmd["params"]["raw_args"]
    finally:
        del WORKFLOW_REGISTRY["deploy"]


def test_parse_unregistered_command_returns_none():
    cmd = parse_command("!nonexistent something")
    assert cmd is None
```

**Step 5: Run tests**

```bash
uv run pytest -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add -A && git commit -m "feat: wire daemon and discord_bot to use plugin system"
```

---

### Task 6: Move UE workflows to plugin directory

**Files:**
- Create: `plugins/ue/workflows.py` (from `src/disco_agent/workflows/compile.py` + `package.py`)
- Create: `plugins/ue/config.py`
- Create: `plugins/ue/__init__.py` (empty)
- Delete: `src/disco_agent/workflows/compile.py`
- Delete: `src/disco_agent/workflows/package.py`
- Delete: `src/disco_agent/workflows/submit.py`
- Move/update: `tests/test_compile.py` -> `tests/test_ue_plugin.py`

**Step 1: Create plugin directory**

```bash
mkdir -p plugins/ue/commands
```

**Step 2: Create plugins/ue/config.py**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UEPluginConfig:
    engine_path: Path = Path("C:/Program Files/Epic Games/UE_5.7/Engine")
    project_path: str = ""
    platform: str = "Win64"
    build_flags: list[str] = field(
        default_factory=lambda: ["-cook", "-stage", "-pak", "-unattended", "-nullrhi"]
    )
    max_retries: int = 3
    error_tail_lines: int = 200
    ue_source_path: str = ""
    compile_warning_usd: float = 5.0
    package_warning_usd: float = 5.0


def load_ue_config(raw: dict) -> UEPluginConfig:
    config = UEPluginConfig()
    for key, value in raw.items():
        if hasattr(config, key):
            current = getattr(config, key)
            if isinstance(current, Path):
                setattr(config, key, Path(value))
            else:
                setattr(config, key, value)
    return config
```

**Step 3: Create plugins/ue/workflows.py**

Move compile and package workflow code. Update imports from `disco_agent.*` (core modules they still need) and from the local plugin config:

```python
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from disco_agent.cost_tracker import CostTracker
from disco_agent.queue import TaskQueue
from disco_agent.utils import tail_lines
from disco_agent.workflows import register
from disco_agent.workflows.base import BaseWorkflow, Notifier, WorkflowResult

logger = logging.getLogger(__name__)


# --- Plugin config (loaded from [plugin-config.ue] in config.toml) ---

_plugin_config = None


def set_plugin_config(config):
    global _plugin_config
    _plugin_config = config


def _get_config():
    if _plugin_config is None:
        from plugins.ue.config import UEPluginConfig
        return UEPluginConfig()
    return _plugin_config


# --- UE build helpers ---

async def run_uat(
    engine_path: str | Path,
    project_path: str,
    platform: str,
    flags: list[str],
    cwd: str,
) -> tuple[int, str, str]:
    bat = Path(engine_path) / "Build" / "BatchFiles" / "RunUAT.bat"
    cmd = [
        str(bat),
        "BuildCookRun",
        f"-project={project_path}",
        f"-platform={platform}",
        *flags,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    returncode = proc.returncode if proc.returncode is not None else 1
    return (
        returncode,
        stdout_bytes.decode("utf-8", errors="replace"),
        stderr_bytes.decode("utf-8", errors="replace"),
    )


async def sdk_analyze_and_fix(error_log: str, repo_root: str, allowed_tools: list[str]):
    prompt = (
        "A UE BuildCookRun compile has failed. Analyze the error below and attempt to fix it.\n"
        "Focus on the actual compilation error, not warnings.\n\n"
        f"Build error log (last lines):\n```\n{error_log}\n```"
    )
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=allowed_tools,
            cwd=repo_root,
            permission_mode="bypassPermissions",
        ),
    ):
        yield message


# --- Workflows ---

@register("compile")
class CompileWorkflow(BaseWorkflow):
    def __init__(
        self,
        task: dict[str, Any],
        queue: TaskQueue,
        notifier: Notifier,
        repo_root: str,
        **kwargs,
    ):
        super().__init__(task=task, queue=queue, notifier=notifier)
        config = _get_config()
        self.ue_config = config
        self.cost_tracker = CostTracker(config.compile_warning_usd)
        self.repo_root = repo_root

    async def execute(self) -> WorkflowResult:
        config = self.ue_config
        max_retries = config.max_retries
        last_error = ""

        for attempt in range(1, max_retries + 1):
            if await self.is_cancelled():
                return WorkflowResult(
                    success=False,
                    error="Cancelled by user",
                    cost_usd=self.cost_tracker.total_cost_usd,
                )

            await self._send_update(
                f"Compile attempt {attempt}/{max_retries} for `{self.task['project']}`",
            )

            task_platform = self.task.get("platform") or config.platform
            task_project_path = self.task.get("project_path") or config.project_path

            exit_code, stdout, stderr = await run_uat(
                engine_path=config.engine_path,
                project_path=task_project_path,
                platform=task_platform,
                flags=config.build_flags,
                cwd=self.repo_root,
            )

            if exit_code == 0:
                return WorkflowResult(
                    success=True,
                    output=f"Build succeeded on attempt {attempt}",
                    cost_usd=self.cost_tracker.total_cost_usd,
                )

            last_error = stderr or stdout
            error_tail = tail_lines(last_error, config.error_tail_lines)

            if attempt >= max_retries:
                break

            await self._send_update(
                f"Build failed (attempt {attempt}). Analyzing error with Claude...",
            )

            stream = self._create_stream()

            async for message in sdk_analyze_and_fix(
                error_log=error_tail,
                repo_root=self.repo_root,
                allowed_tools=["Read", "Edit", "Glob", "Grep", "Bash"],
            ):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock) and stream:
                            await stream.append(block.text)
                        elif isinstance(block, ToolUseBlock) and stream:
                            await stream.append_tool_use(block.name, block.input)
                elif isinstance(message, ResultMessage):
                    if message.total_cost_usd is not None:
                        for w in self.cost_tracker.add_cost(message.total_cost_usd):
                            await self._send_update(w)

            if stream:
                await stream.finalize()

            await self._send_update("Fix attempted. Recompiling...")

        return WorkflowResult(
            success=False,
            error=f"Build failed after {max_retries} retries exhausted. Last error:\n{tail_lines(last_error, 50)}",
            cost_usd=self.cost_tracker.total_cost_usd,
        )


@register("package")
class PackageWorkflow(CompileWorkflow):
    """Package workflow -- same as compile but uses package budget threshold."""

    def __init__(self, task, queue, notifier, repo_root, **kwargs):
        super().__init__(task=task, queue=queue, notifier=notifier, repo_root=repo_root, **kwargs)
        config = _get_config()
        self.cost_tracker = CostTracker(config.package_warning_usd)
```

**Step 4: Create empty `plugins/ue/__init__.py`**

```bash
touch plugins/ue/__init__.py
```

**Step 5: Delete old workflow files from core**

```bash
rm src/disco_agent/workflows/compile.py
rm src/disco_agent/workflows/package.py
rm src/disco_agent/workflows/submit.py
```

**Step 6: Update plugins.py to initialize code plugin config**

In `_load_code_plugin`, after importing the module, call a `set_plugin_config` function if the plugin exposes one and there's config available:

```python
def _load_code_plugin(plugin: dict[str, Any], config_dir: str, plugin_configs: dict[str, Any]) -> None:
    # ... existing import logic ...

    # Pass plugin config if available
    name = plugin["name"]
    if name in plugin_configs and hasattr(module, "set_plugin_config"):
        module.set_plugin_config(plugin_configs[name])

    logger.info("Loaded code plugin '%s' from %s", name, workflows_file)
```

Update the UE plugin `set_plugin_config` to parse the raw dict:

```python
def set_plugin_config(raw: dict):
    from plugins.ue.config import load_ue_config
    global _plugin_config
    _plugin_config = load_ue_config(raw)
```

**Step 7: Update test_compile.py -> test_ue_plugin.py**

Rename the file and update imports to load the plugin workflow from its new location. Since code plugins use `@register`, we need to import the plugin module. The test mocks will need slight adjustments for the new constructor signature (`repo_root` instead of separate config objects):

```bash
mv tests/test_compile.py tests/test_ue_plugin.py
```

Update the test file to import from the plugin path and use the new constructor:

```python
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from disco_agent.workflows.base import WorkflowResult


@dataclass
class FakeMessage:
    type: str = "result"
    subtype: str = ""
    result: str = ""
    session_id: str = "sess-1"
    cost_usd: float = 0.0
    total_cost_usd: float = 0.0


@pytest.fixture(autouse=True)
def setup_ue_config():
    """Set up UE plugin config for tests."""
    import importlib.util, sys
    from pathlib import Path

    # Load the plugin module
    spec = importlib.util.spec_from_file_location(
        "disco_agent_plugin_ue",
        str(Path("plugins/ue/workflows.py")),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["disco_agent_plugin_ue"] = module
    spec.loader.exec_module(module)

    # Configure with test values
    from plugins.ue.config import UEPluginConfig
    module.set_plugin_config(UEPluginConfig(engine_path="C:/UE5"))
    yield
    # Clean up
    from disco_agent.workflows import WORKFLOW_REGISTRY
    WORKFLOW_REGISTRY.pop("compile", None)
    WORKFLOW_REGISTRY.pop("package", None)


@pytest.fixture
def task():
    return {
        "id": 1, "workflow": "compile", "project": "CitySample",
        "platform": "Win64", "params": "{}", "status": "running",
        "discord_channel_id": "chan1", "discord_message_id": "msg1",
        "requested_by": "user1",
    }


@pytest.fixture
def mock_queue():
    q = AsyncMock()
    q.is_cancelled = AsyncMock(return_value=False)
    return q


@pytest.fixture
def mock_notifier():
    return AsyncMock()


async def test_compile_success(task, mock_queue, mock_notifier):
    from disco_agent.workflows import WORKFLOW_REGISTRY
    CompileWorkflow = WORKFLOW_REGISTRY["compile"]

    wf = CompileWorkflow(
        task=task, queue=mock_queue, notifier=mock_notifier,
        repo_root="C:/Source/test",
    )

    with patch("disco_agent_plugin_ue.run_uat") as mock_uat:
        mock_uat.return_value = (0, "Build succeeded", "")
        result = await wf.execute()

    assert result.success is True
    mock_uat.assert_called_once()


async def test_compile_fail_then_sdk_fix(task, mock_queue, mock_notifier):
    from disco_agent.workflows import WORKFLOW_REGISTRY
    CompileWorkflow = WORKFLOW_REGISTRY["compile"]

    wf = CompileWorkflow(
        task=task, queue=mock_queue, notifier=mock_notifier,
        repo_root="C:/Source/test",
    )

    call_count = 0
    async def mock_uat_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (1, "", "error: undefined reference to foo")
        return (0, "Build succeeded", "")

    async def fake_query(*args, **kwargs):
        yield FakeMessage(type="result", result="Fixed", total_cost_usd=0.50)

    with (
        patch("disco_agent_plugin_ue.run_uat", side_effect=mock_uat_side_effect),
        patch("disco_agent_plugin_ue.sdk_analyze_and_fix", side_effect=fake_query),
    ):
        result = await wf.execute()

    assert result.success is True
    assert call_count == 2


async def test_compile_all_retries_exhausted(task, mock_queue, mock_notifier):
    from disco_agent.workflows import WORKFLOW_REGISTRY
    from plugins.ue.config import UEPluginConfig
    import disco_agent_plugin_ue
    disco_agent_plugin_ue.set_plugin_config(UEPluginConfig(engine_path="C:/UE5", max_retries=2))

    CompileWorkflow = WORKFLOW_REGISTRY["compile"]
    wf = CompileWorkflow(
        task=task, queue=mock_queue, notifier=mock_notifier,
        repo_root="C:/Source/test",
    )

    async def fake_query(*args, **kwargs):
        yield FakeMessage(type="result", result="Attempted fix", total_cost_usd=0.30)

    with (
        patch("disco_agent_plugin_ue.run_uat", return_value=(1, "", "error")),
        patch("disco_agent_plugin_ue.sdk_analyze_and_fix", side_effect=fake_query),
    ):
        result = await wf.execute()

    assert result.success is False


async def test_compile_cancelled_mid_retry(task, mock_queue, mock_notifier):
    from disco_agent.workflows import WORKFLOW_REGISTRY
    mock_queue.is_cancelled = AsyncMock(side_effect=[False, True])

    CompileWorkflow = WORKFLOW_REGISTRY["compile"]
    wf = CompileWorkflow(
        task=task, queue=mock_queue, notifier=mock_notifier,
        repo_root="C:/Source/test",
    )

    async def fake_query(*args, **kwargs):
        yield FakeMessage(type="result", result="fix", total_cost_usd=0.10)

    with (
        patch("disco_agent_plugin_ue.run_uat", return_value=(1, "", "error")),
        patch("disco_agent_plugin_ue.sdk_analyze_and_fix", side_effect=fake_query),
    ):
        result = await wf.execute()

    assert result.success is False
    assert "cancel" in result.error.lower()
```

**Step 8: Update test_workflows.py dispatch roundtrip test**

Remove the compile workflow roundtrip test (it's covered by `test_ue_plugin.py`). Keep the `register`, `is_cancelled`, thread tests since those test core behavior.

**Step 9: Run all tests**

```bash
uv run pytest -v
```

Expected: PASS

**Step 10: Commit**

```bash
git add -A && git commit -m "feat: move UE compile/package workflows to plugins/ue"
```

---

### Task 7: Create ue-research slash command and setup-ue command

**Files:**
- Create: `plugins/ue/commands/ue-research.md`
- Create: `.claude/commands/setup-ue.md`
- Delete: `.claude/commands/ue-research.md` (old version)
- Delete: `.claude/commands/rebuild.md` (UE-specific, no longer core)

**Step 1: Create updated ue-research.md**

Create `plugins/ue/commands/ue-research.md` with the UE source path read from config and auto-discovered repo locations. See design doc for full content. Key changes from old version:

- Replace hardcoded `C:/Source/UnrealEngine` with `$UE_SOURCE_PATH` variable
- Replace hardcoded repo source locations with instructions to auto-discover by scanning for `*.Build.cs`, `Source/` directories, `.uproject` files
- Update all version references to 5.7

**Step 2: Create setup-ue.md**

Create `.claude/commands/setup-ue.md`:

```markdown
---
description: Interactive setup for the UE build automation plugin
---

# Setup UE Plugin

Walk the user through configuring the Unreal Engine plugin for Disco-Agent.

## Steps

### 1. Detect Engine Install

Search for UE installations:
- Check `C:/Program Files/Epic Games/UE_5.*/Engine`
- Check common custom install paths
- Ask the user to confirm or provide their engine path

### 2. Find .uproject File

Scan the repo root for `.uproject` files:
```bash
find . -maxdepth 3 -name "*.uproject" 2>/dev/null
```
Present findings and ask the user to select one, or enter a path manually.

### 3. UE Source Path (optional)

Ask if the user has cloned the UE source from GitHub for API research:
- If yes, ask for the path (e.g., `C:/Source/UnrealEngine`)
- If no, explain this is optional and only needed for the `/ue-research` command

### 4. Write Config

Read the existing `config.toml` (create if it doesn't exist). Append the plugin configuration:

```toml
[[plugins]]
name = "ue"
type = "code"
path = "plugins/ue"

[plugin-config.ue]
engine_path = "<detected>"
project_path = "<selected>.uproject"
platform = "Win64"
build_flags = ["-cook", "-stage", "-pak", "-unattended", "-nullrhi"]
max_retries = 3
error_tail_lines = 200
ue_source_path = "<optional>"
compile_warning_usd = 5.0
package_warning_usd = 5.0
```

### 5. Verify

Run `disco-agent queue` to verify the config loads without errors.

Report the final configuration to the user.
```

**Step 3: Delete old commands**

```bash
rm .claude/commands/ue-research.md
rm .claude/commands/rebuild.md
```

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: add setup-ue command, move ue-research to plugin"
```

---

### Task 8: Update README, CLAUDE.md, and .gitignore

**Files:**
- Rewrite: `README.md`
- Rewrite: `CLAUDE.md`
- Modify: `.gitignore`

**Step 1: Rewrite README.md**

Rewrite to describe Disco-Agent as a general-purpose Discord-to-Claude daemon. Structure:

1. Header + description
2. Prerequisites (Python 3.11+, uv, Claude Code CLI, Discord bot token)
3. Quick start (uv sync, create bot, configure .env, configure config.toml, start)
4. Discord commands (built-in: analyze, run, status, cancel, history, help)
5. Threads & live output (same as before)
6. How it works (architecture diagram, updated)
7. Plugin system section:
   - Session plugins (config-only)
   - Code plugins (Python)
   - Example: UE build plugin (run `/setup-ue`)
8. UE Plugin section:
   - What it provides (compile, package commands)
   - Setup via `/setup-ue` or manual config
   - Optional: clone UE source from GitHub for `/ue-research`
9. Adding new plugins
10. Running tests
11. CLI reference

**Step 2: Rewrite CLAUDE.md**

Update to reflect new architecture: general-purpose daemon, plugin system, renamed module.

**Step 3: Update .gitignore**

Add `chat_history/` at root level (since we changed the history dir path). Keep existing entries.

**Step 4: Commit**

```bash
git add -A && git commit -m "docs: rewrite README and CLAUDE.md for disco-agent"
```

---

### Task 9: Final integration test — full round-trip

**Step 1: Run full test suite**

```bash
cd C:/Source/Disco-Agent && uv run pytest -v
```

Expected: ALL PASS

**Step 2: Verify the package installs**

```bash
uv run disco-agent --help 2>&1 || echo "Check usage string"
```

**Step 3: Verify config loading with example config**

```bash
cp config.toml.example config.toml.test
# Add a token to test loading
echo "DISCORD_BOT_TOKEN=test" > .env.test
```

**Step 4: Commit any fixes**

```bash
git add -A && git commit -m "chore: final integration fixes"
```
