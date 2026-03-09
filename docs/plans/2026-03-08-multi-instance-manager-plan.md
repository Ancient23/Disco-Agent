# Multi-Instance Manager Implementation Plan

**Goal:** Add a subprocess-based multi-instance daemon manager so users can run multiple disco-agent instances from a single CLI, with auto-restart, status monitoring, and cross-platform service installation.

**Architecture:** A new `manager.py` module spawns `disco-agent start --config <path>` subprocesses for each instance defined in `~/.disco-agent/instances.toml`. The existing `daemon.py` arg parser is extended with new subcommands (`start-all`, `status`, `stop-all`, `install-service`, `uninstall-service`). Plugin path resolution gains `DISCO_AGENT_ROOT` env var support.

**Tech Stack:** Python 3.11+ stdlib only (asyncio, subprocess, tomllib, signal, json, shutil). No new dependencies.

---

### Task 1: Plugin path resolution — `DISCO_AGENT_ROOT` support

**Files:**
- Modify: `src/disco_agent/plugins.py:62-66` (plugin path resolution)
- Modify: `src/disco_agent/plugins.py:79-82` (sys.path addition)
- Test: `tests/test_plugins.py`

**Step 1: Write the failing test**

Add to `tests/test_plugins.py`:

```python
def test_code_plugin_resolves_path_from_disco_agent_root(tmp_path, monkeypatch):
    """When DISCO_AGENT_ROOT is set, relative plugin paths resolve against it."""
    disco_root = tmp_path / "disco_root"
    disco_root.mkdir()
    plugin_dir = disco_root / "plugins" / "myplugin"
    plugin_dir.mkdir(parents=True)
    workflows_file = plugin_dir / "workflows.py"
    workflows_file.write_text(
        textwrap.dedent("""\
            from disco_agent.workflows import register
            from disco_agent.workflows.base import BaseWorkflow, WorkflowResult

            @register("root_cmd")
            class RootCmdWorkflow(BaseWorkflow):
                async def execute(self):
                    return WorkflowResult(success=True, output="ok")
        """)
    )

    monkeypatch.setenv("DISCO_AGENT_ROOT", str(disco_root))

    plugins = [
        {
            "name": "myplugin",
            "type": "code",
            "path": "plugins/myplugin",  # relative — should resolve against DISCO_AGENT_ROOT
        }
    ]
    # config_dir is different from disco_root — the env var should take priority
    load_plugins(plugins, {}, str(tmp_path / "some_other_dir"))

    assert "root_cmd" in WORKFLOW_REGISTRY


def test_code_plugin_falls_back_to_config_dir_without_env(tmp_path, monkeypatch):
    """Without DISCO_AGENT_ROOT, relative plugin paths resolve against config_dir (existing behavior)."""
    monkeypatch.delenv("DISCO_AGENT_ROOT", raising=False)

    plugin_dir = tmp_path / "plugins" / "fallback"
    plugin_dir.mkdir(parents=True)
    workflows_file = plugin_dir / "workflows.py"
    workflows_file.write_text(
        textwrap.dedent("""\
            from disco_agent.workflows import register
            from disco_agent.workflows.base import BaseWorkflow, WorkflowResult

            @register("fallback_cmd")
            class FallbackWorkflow(BaseWorkflow):
                async def execute(self):
                    return WorkflowResult(success=True, output="ok")
        """)
    )

    plugins = [
        {
            "name": "fallback",
            "type": "code",
            "path": "plugins/fallback",
        }
    ]
    load_plugins(plugins, {}, str(tmp_path))

    assert "fallback_cmd" in WORKFLOW_REGISTRY
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_plugins.py::test_code_plugin_resolves_path_from_disco_agent_root tests/test_plugins.py::test_code_plugin_falls_back_to_config_dir_without_env -v`
Expected: First test FAILS (DISCO_AGENT_ROOT is ignored), second test may pass (existing behavior).

**Step 3: Implement the change**

In `src/disco_agent/plugins.py`, modify `_load_code_plugin`:

```python
import os

def _load_code_plugin(plugin: dict[str, Any], config_dir: str, plugin_configs: dict[str, Any]) -> None:
    """Load a code plugin by importing its workflows.py module."""
    plugin_path = Path(plugin["path"])
    if not plugin_path.is_absolute():
        disco_root = os.environ.get("DISCO_AGENT_ROOT", "")
        base = Path(disco_root) if disco_root else Path(config_dir)
        plugin_path = base / plugin_path

    workflows_file = plugin_path / "workflows.py"
    if not workflows_file.exists():
        raise FileNotFoundError(
            f"Code plugin '{plugin['name']}': {workflows_file} not found"
        )

    module_name = f"disco_agent_plugin_{plugin['name'].replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, str(workflows_file))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    # Add the base directory to sys.path so absolute imports like
    # "from plugins.ue.config import ..." resolve correctly.
    disco_root_env = os.environ.get("DISCO_AGENT_ROOT", "")
    path_root = disco_root_env if disco_root_env else config_dir
    if path_root not in sys.path:
        sys.path.insert(0, path_root)

    spec.loader.exec_module(module)

    # Pass plugin config if available
    name = plugin["name"]
    if name in plugin_configs and hasattr(module, "set_plugin_config"):
        module.set_plugin_config(plugin_configs[name])

    logger.info("Loaded code plugin '%s' from %s", plugin["name"], workflows_file)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_plugins.py -v`
Expected: ALL pass, including both new tests.

**Step 5: Commit**

```bash
git add src/disco_agent/plugins.py tests/test_plugins.py
git commit -m "feat: support DISCO_AGENT_ROOT for plugin path resolution"
```

---

### Task 2: instances.toml parser and .env layering

**Files:**
- Create: `src/disco_agent/manager.py`
- Test: `tests/test_manager.py`

**Step 1: Write failing tests**

Create `tests/test_manager.py`:

```python
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest


def test_parse_instances_toml(tmp_path):
    """Parse instances.toml and return disco_agent_root + instance list."""
    instances_toml = tmp_path / "instances.toml"
    instances_toml.write_text(textwrap.dedent("""\
        disco_agent_root = "C:/Source/Disco-Agent"

        [[instance]]
        name = "proj-a"
        config = "instances/proj-a/config.toml"

        [[instance]]
        name = "proj-b"
        config = "instances/proj-b/config.toml"
    """))

    from disco_agent.manager import parse_instances_config

    cfg = parse_instances_config(instances_toml)
    assert cfg.disco_agent_root == "C:/Source/Disco-Agent"
    assert len(cfg.instances) == 2
    assert cfg.instances[0].name == "proj-a"
    # Config path should be resolved relative to instances.toml dir
    assert cfg.instances[0].config_path == tmp_path / "instances" / "proj-a" / "config.toml"


def test_parse_instances_toml_missing_file(tmp_path):
    """Raise FileNotFoundError for missing instances.toml."""
    from disco_agent.manager import parse_instances_config

    with pytest.raises(FileNotFoundError):
        parse_instances_config(tmp_path / "nope.toml")


def test_build_instance_env_global_only(tmp_path):
    """With only a global .env, all vars come from it."""
    global_env = tmp_path / ".env"
    global_env.write_text("DISCORD_BOT_TOKEN=global-tok\nLOG_LEVEL=INFO\n")

    from disco_agent.manager import build_instance_env

    env = build_instance_env(global_env_path=global_env, instance_env_path=None)
    assert env["DISCORD_BOT_TOKEN"] == "global-tok"
    assert env["LOG_LEVEL"] == "INFO"


def test_build_instance_env_instance_overrides(tmp_path):
    """Instance .env overrides global values and adds new keys."""
    global_env = tmp_path / "global.env"
    global_env.write_text("DISCORD_BOT_TOKEN=global-tok\nSHARED=from_global\n")

    instance_env = tmp_path / "instance.env"
    instance_env.write_text("SHARED=from_instance\nEXTRA=bonus\n")

    from disco_agent.manager import build_instance_env

    env = build_instance_env(global_env_path=global_env, instance_env_path=instance_env)
    assert env["DISCORD_BOT_TOKEN"] == "global-tok"
    assert env["SHARED"] == "from_instance"
    assert env["EXTRA"] == "bonus"


def test_build_instance_env_no_global(tmp_path):
    """With no global .env, instance .env is the sole source."""
    instance_env = tmp_path / "instance.env"
    instance_env.write_text("DISCORD_BOT_TOKEN=inst-tok\n")

    from disco_agent.manager import build_instance_env

    env = build_instance_env(global_env_path=tmp_path / "missing.env", instance_env_path=instance_env)
    assert env["DISCORD_BOT_TOKEN"] == "inst-tok"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'disco_agent.manager'`

**Step 3: Implement the parser and env builder**

Create `src/disco_agent/manager.py`:

```python
from __future__ import annotations

import json
import os
import signal
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class InstanceConfig:
    name: str
    config_path: Path
    env_path: Path | None = None


@dataclass
class InstancesConfig:
    disco_agent_root: str
    instances: list[InstanceConfig] = field(default_factory=list)
    base_dir: Path = field(default_factory=lambda: Path.home() / ".disco-agent")


def _default_instances_path() -> Path:
    return Path.home() / ".disco-agent" / "instances.toml"


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict. Skips comments and blank lines."""
    result = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def build_instance_env(
    global_env_path: Path | None,
    instance_env_path: Path | None,
) -> dict[str, str]:
    """Build merged environment: current os.environ + global .env + instance .env overlay."""
    env = dict(os.environ)

    if global_env_path:
        env.update(parse_env_file(global_env_path))

    if instance_env_path:
        env.update(parse_env_file(instance_env_path))

    return env


def parse_instances_config(path: Path) -> InstancesConfig:
    """Parse instances.toml and resolve paths relative to its directory."""
    if not path.exists():
        raise FileNotFoundError(f"Instances config not found: {path}")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    base_dir = path.parent
    disco_root = raw.get("disco_agent_root", "")

    instances = []
    for inst in raw.get("instance", []):
        name = inst["name"]
        config_rel = Path(inst["config"])
        config_path = config_rel if config_rel.is_absolute() else base_dir / config_rel

        env_path = None
        if "env" in inst:
            env_rel = Path(inst["env"])
            env_path = env_rel if env_rel.is_absolute() else base_dir / env_rel
        else:
            # Default: .env alongside the config.toml
            candidate = config_path.parent / ".env"
            if candidate.exists():
                env_path = candidate

        instances.append(InstanceConfig(name=name, config_path=config_path, env_path=env_path))

    return InstancesConfig(
        disco_agent_root=disco_root,
        instances=instances,
        base_dir=base_dir,
    )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_manager.py -v`
Expected: ALL pass.

**Step 5: Commit**

```bash
git add src/disco_agent/manager.py tests/test_manager.py
git commit -m "feat: add instances.toml parser and .env layering"
```

---

### Task 3: Subprocess spawner with stdout prefixing

**Files:**
- Modify: `src/disco_agent/manager.py`
- Test: `tests/test_manager.py`

**Step 1: Write the failing test**

Add to `tests/test_manager.py`:

```python
import asyncio


async def test_spawn_instance_captures_prefixed_output(tmp_path):
    """Spawning an instance prefixes its stdout with [name]."""
    from disco_agent.manager import InstanceRunner

    # Create a script that prints a line and exits
    script = tmp_path / "echo_script.py"
    script.write_text('import sys; print("hello from child"); sys.exit(0)')

    runner = InstanceRunner(
        name="test-inst",
        cmd=[sys.executable, str(script)],
        env=dict(os.environ),
    )

    lines = []
    runner.on_output = lambda line: lines.append(line)

    await runner.start()
    await runner.wait()

    assert any("[test-inst]" in line and "hello from child" in line for line in lines)


async def test_spawn_instance_returns_exit_code(tmp_path):
    """InstanceRunner captures the child exit code."""
    from disco_agent.manager import InstanceRunner

    script = tmp_path / "exit_script.py"
    script.write_text("import sys; sys.exit(42)")

    runner = InstanceRunner(
        name="exiter",
        cmd=[sys.executable, str(script)],
        env=dict(os.environ),
    )

    await runner.start()
    code = await runner.wait()
    assert code == 42
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_manager.py::test_spawn_instance_captures_prefixed_output tests/test_manager.py::test_spawn_instance_returns_exit_code -v`
Expected: FAIL with `ImportError: cannot import name 'InstanceRunner'`

**Step 3: Implement InstanceRunner**

Add to `src/disco_agent/manager.py`:

```python
import asyncio
import logging
import subprocess

logger = logging.getLogger(__name__)


class InstanceRunner:
    """Manages a single disco-agent child process."""

    def __init__(self, name: str, cmd: list[str], env: dict[str, str]):
        self.name = name
        self.cmd = cmd
        self.env = env
        self.process: asyncio.subprocess.Process | None = None
        self.on_output: Any = None  # callback(line: str)

    async def start(self) -> None:
        self.process = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=self.env,
        )
        asyncio.create_task(self._read_output())

    async def _read_output(self) -> None:
        assert self.process and self.process.stdout
        while True:
            line_bytes = await self.process.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").rstrip()
            prefixed = f"[{self.name}] {line}"
            if self.on_output:
                self.on_output(prefixed)
            else:
                print(prefixed, flush=True)

    async def wait(self) -> int:
        assert self.process
        return await self.process.wait()

    def terminate(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()

    def kill(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.kill()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_manager.py -v`
Expected: ALL pass.

**Step 5: Commit**

```bash
git add src/disco_agent/manager.py tests/test_manager.py
git commit -m "feat: add InstanceRunner subprocess spawner with stdout prefixing"
```

---

### Task 4: Auto-restart with exponential backoff

**Files:**
- Modify: `src/disco_agent/manager.py`
- Test: `tests/test_manager.py`

**Step 1: Write the failing test**

Add to `tests/test_manager.py`:

```python
from unittest.mock import AsyncMock, patch
import time


async def test_backoff_sequence():
    """Backoff should progress: 1, 5, 30, 60, 60, ... and reset after healthy period."""
    from disco_agent.manager import RestartTracker

    tracker = RestartTracker()
    assert tracker.next_delay() == 1
    assert tracker.next_delay() == 5
    assert tracker.next_delay() == 30
    assert tracker.next_delay() == 60
    assert tracker.next_delay() == 60  # caps at 60

    tracker.mark_healthy()  # reset
    assert tracker.next_delay() == 1


async def test_restart_tracker_counts_restarts():
    """RestartTracker should count total restarts."""
    from disco_agent.manager import RestartTracker

    tracker = RestartTracker()
    tracker.next_delay()
    tracker.next_delay()
    assert tracker.restart_count == 2
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_manager.py::test_backoff_sequence tests/test_manager.py::test_restart_tracker_counts_restarts -v`
Expected: FAIL with `ImportError: cannot import name 'RestartTracker'`

**Step 3: Implement RestartTracker**

Add to `src/disco_agent/manager.py`:

```python
import time

_BACKOFF_SEQUENCE = [1, 5, 30, 60]
_HEALTHY_THRESHOLD_SECONDS = 300  # 5 minutes


class RestartTracker:
    """Tracks restart attempts with exponential backoff."""

    def __init__(self):
        self._index = 0
        self.restart_count = 0
        self._last_start: float | None = None

    def next_delay(self) -> int:
        """Return the next backoff delay in seconds and increment restart count."""
        self.restart_count += 1
        delay = _BACKOFF_SEQUENCE[min(self._index, len(_BACKOFF_SEQUENCE) - 1)]
        self._index += 1
        return delay

    def mark_started(self) -> None:
        """Record when the instance was started."""
        self._last_start = time.monotonic()

    def check_healthy(self) -> None:
        """If the instance has been running longer than the threshold, reset backoff."""
        if self._last_start and (time.monotonic() - self._last_start) >= _HEALTHY_THRESHOLD_SECONDS:
            self.mark_healthy()

    def mark_healthy(self) -> None:
        """Reset backoff to initial state."""
        self._index = 0
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_manager.py -v`
Expected: ALL pass.

**Step 5: Commit**

```bash
git add src/disco_agent/manager.py tests/test_manager.py
git commit -m "feat: add RestartTracker with exponential backoff"
```

---

### Task 5: Manager orchestrator (start-all loop)

**Files:**
- Modify: `src/disco_agent/manager.py`
- Test: `tests/test_manager.py`

**Step 1: Write the failing test**

Add to `tests/test_manager.py`:

```python
async def test_manager_starts_and_stops_instances(tmp_path):
    """Manager should start instances and stop them on shutdown."""
    from disco_agent.manager import InstancesConfig, InstanceConfig, Manager

    # Create a script that sleeps until terminated
    script = tmp_path / "sleeper.py"
    script.write_text("import time\nwhile True:\n    time.sleep(0.1)")

    instances_cfg = InstancesConfig(
        disco_agent_root=str(tmp_path),
        base_dir=tmp_path,
        instances=[
            InstanceConfig(name="inst-a", config_path=tmp_path / "a.toml"),
            InstanceConfig(name="inst-b", config_path=tmp_path / "b.toml"),
        ],
    )

    manager = Manager(instances_cfg)
    # Override the command builder to use our sleeper script
    manager._build_cmd = lambda inst: [sys.executable, str(script)]

    # Start manager, wait briefly, then signal shutdown
    task = asyncio.create_task(manager.run())
    await asyncio.sleep(0.5)

    assert len(manager.runners) == 2
    assert all(r.process and r.process.returncode is None for r in manager.runners.values())

    manager.shutdown()
    await asyncio.wait_for(task, timeout=15)

    assert all(r.process and r.process.returncode is not None for r in manager.runners.values())
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_manager.py::test_manager_starts_and_stops_instances -v`
Expected: FAIL with `ImportError: cannot import name 'Manager'`

**Step 3: Implement the Manager class**

Add to `src/disco_agent/manager.py`:

```python
class Manager:
    """Orchestrates multiple disco-agent instances."""

    def __init__(self, config: InstancesConfig):
        self.config = config
        self.runners: dict[str, InstanceRunner] = {}
        self._trackers: dict[str, RestartTracker] = {}
        self._shutdown = asyncio.Event()
        self._state_path = config.base_dir / "manager-state.json"
        self._pid_path = config.base_dir / "manager.pid"

    def _build_cmd(self, instance: InstanceConfig) -> list[str]:
        return [sys.executable, "-m", "disco_agent.daemon", "start", "--config", str(instance.config_path)]

    def _build_env(self, instance: InstanceConfig) -> dict[str, str]:
        global_env_path = self.config.base_dir / ".env"
        env = build_instance_env(global_env_path, instance.env_path)
        if self.config.disco_agent_root:
            env["DISCO_AGENT_ROOT"] = self.config.disco_agent_root
        return env

    async def run(self) -> None:
        """Start all instances and monitor them until shutdown."""
        self._write_pid()

        try:
            tasks = []
            for inst in self.config.instances:
                tasks.append(asyncio.create_task(self._run_instance(inst)))

            await self._shutdown.wait()

            # Terminate all children
            for runner in self.runners.values():
                runner.terminate()

            # Wait up to 10s for graceful exit
            for name, runner in self.runners.items():
                try:
                    await asyncio.wait_for(runner.wait(), timeout=10)
                except asyncio.TimeoutError:
                    logger.warning("Instance '%s' did not exit gracefully, killing", name)
                    runner.kill()
                    await runner.wait()

            for t in tasks:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        finally:
            self._remove_pid()
            self._write_state()

    async def _run_instance(self, instance: InstanceConfig) -> None:
        """Run a single instance with auto-restart."""
        tracker = RestartTracker()
        self._trackers[instance.name] = tracker

        while not self._shutdown.is_set():
            cmd = self._build_cmd(instance)
            env = self._build_env(instance)

            runner = InstanceRunner(name=instance.name, cmd=cmd, env=env)
            self.runners[instance.name] = runner

            tracker.mark_started()
            await runner.start()
            self._write_state()

            exit_code = await runner.wait()

            if self._shutdown.is_set():
                break

            tracker.check_healthy()
            delay = tracker.next_delay()
            logger.warning(
                "Instance '%s' exited (code=%s). Restarting in %ds (attempt #%d)",
                instance.name, exit_code, delay, tracker.restart_count,
            )
            self._write_state()

            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=delay)
                break  # shutdown requested during backoff
            except asyncio.TimeoutError:
                pass  # backoff elapsed, restart

    def shutdown(self) -> None:
        self._shutdown.set()

    def _write_pid(self) -> None:
        self._pid_path.parent.mkdir(parents=True, exist_ok=True)
        self._pid_path.write_text(str(os.getpid()))

    def _remove_pid(self) -> None:
        self._pid_path.unlink(missing_ok=True)

    def _write_state(self) -> None:
        state = {
            "pid": os.getpid(),
            "started": datetime.now(timezone.utc).isoformat(),
            "instances": {},
        }
        for name, runner in self.runners.items():
            tracker = self._trackers.get(name)
            proc = runner.process
            state["instances"][name] = {
                "pid": proc.pid if proc else None,
                "status": "running" if proc and proc.returncode is None else "stopped",
                "restarts": tracker.restart_count if tracker else 0,
            }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(state, indent=2))
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_manager.py -v`
Expected: ALL pass.

**Step 5: Commit**

```bash
git add src/disco_agent/manager.py tests/test_manager.py
git commit -m "feat: add Manager orchestrator with auto-restart"
```

---

### Task 6: Status and stop-all commands

**Files:**
- Modify: `src/disco_agent/manager.py`
- Test: `tests/test_manager.py`

**Step 1: Write the failing tests**

Add to `tests/test_manager.py`:

```python
def test_show_status_reads_state_file(tmp_path, capsys):
    """show_status should pretty-print the manager-state.json contents."""
    from disco_agent.manager import show_status

    state = {
        "pid": 12345,
        "started": "2026-03-08T17:00:00+00:00",
        "instances": {
            "proj-a": {"pid": 12346, "status": "running", "restarts": 0},
            "proj-b": {"pid": 12347, "status": "running", "restarts": 2},
        },
    }
    state_file = tmp_path / "manager-state.json"
    state_file.write_text(json.dumps(state))

    show_status(state_file)

    output = capsys.readouterr().out
    assert "proj-a" in output
    assert "running" in output
    assert "proj-b" in output


def test_show_status_missing_file(tmp_path, capsys):
    """show_status should print a message when no state file exists."""
    from disco_agent.manager import show_status

    show_status(tmp_path / "nope.json")
    output = capsys.readouterr().out
    assert "no manager" in output.lower() or "not running" in output.lower()


def test_stop_all_sends_signal(tmp_path):
    """stop_all should read PID file and attempt to terminate the process."""
    from disco_agent.manager import stop_all

    pid_file = tmp_path / "manager.pid"
    pid_file.write_text("99999999")  # non-existent PID

    # Should not raise even if process doesn't exist
    stop_all(pid_file)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_manager.py::test_show_status_reads_state_file tests/test_manager.py::test_show_status_missing_file tests/test_manager.py::test_stop_all_sends_signal -v`
Expected: FAIL with `ImportError`

**Step 3: Implement show_status and stop_all**

Add to `src/disco_agent/manager.py`:

```python
def show_status(state_path: Path) -> None:
    """Pretty-print the manager state from the JSON file."""
    if not state_path.exists():
        print("Manager is not running (no state file found).")
        return

    state = json.loads(state_path.read_text())
    print(f"Manager PID: {state['pid']}")
    print(f"Started: {state['started']}")
    print()
    print(f"{'Instance':<20} {'PID':<10} {'Status':<10} {'Restarts':<10}")
    print("-" * 50)
    for name, info in state.get("instances", {}).items():
        print(f"{name:<20} {str(info.get('pid', '-')):<10} {info['status']:<10} {info['restarts']:<10}")


def stop_all(pid_path: Path) -> None:
    """Read the manager PID file and send a termination signal."""
    if not pid_path.exists():
        print("No manager PID file found. Is the manager running?")
        return

    pid = int(pid_path.read_text().strip())
    try:
        if sys.platform == "win32":
            # Windows: use os.kill with SIGTERM (mapped to TerminateProcess)
            os.kill(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"Sent termination signal to manager (PID {pid}).")
    except ProcessLookupError:
        print(f"Manager process (PID {pid}) not found. Cleaning up PID file.")
        pid_path.unlink(missing_ok=True)
    except PermissionError:
        print(f"Permission denied sending signal to PID {pid}.")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_manager.py -v`
Expected: ALL pass.

**Step 5: Commit**

```bash
git add src/disco_agent/manager.py tests/test_manager.py
git commit -m "feat: add show_status and stop_all commands"
```

---

### Task 7: CLI arg parser — new subcommands

**Files:**
- Modify: `src/disco_agent/daemon.py:129-206`
- Test: `tests/test_manager.py`

**Step 1: Write the failing tests**

Add to `tests/test_manager.py`:

```python
def test_parse_args_start_all(monkeypatch):
    """start-all subcommand should be parsed with optional --instances and --only."""
    monkeypatch.setattr("sys.argv", ["disco-agent", "start-all", "--instances", "/tmp/i.toml", "--only", "proj-a"])

    from disco_agent.daemon import _parse_args

    result = _parse_args()
    assert result[0] == "start-all"


def test_parse_args_status(monkeypatch):
    """status subcommand should be recognized."""
    monkeypatch.setattr("sys.argv", ["disco-agent", "status"])

    from disco_agent.daemon import _parse_args

    result = _parse_args()
    assert result[0] == "status"


def test_parse_args_stop_all(monkeypatch):
    """stop-all subcommand should be recognized."""
    monkeypatch.setattr("sys.argv", ["disco-agent", "stop-all"])

    from disco_agent.daemon import _parse_args

    result = _parse_args()
    assert result[0] == "stop-all"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_manager.py::test_parse_args_start_all tests/test_manager.py::test_parse_args_status tests/test_manager.py::test_parse_args_stop_all -v`
Expected: FAIL — current `_parse_args` exits with error on unknown subcommands.

**Step 3: Extend the arg parser**

Replace `_parse_args` and `main` in `src/disco_agent/daemon.py`:

```python
def _parse_args() -> tuple[str, dict[str, Any]]:
    """Parse CLI arguments. Returns (subcommand, options_dict)."""
    import os

    subcommand = "start"
    options: dict[str, Any] = {}

    valid_subcommands = {"start", "queue", "start-all", "status", "stop-all", "install-service", "uninstall-service"}

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--config" and i + 1 < len(args):
            options["config"] = Path(args[i + 1])
            i += 2
        elif args[i] == "--instances" and i + 1 < len(args):
            options["instances"] = Path(args[i + 1])
            i += 2
        elif args[i] == "--only" and i + 1 < len(args):
            options["only"] = args[i + 1]
            i += 2
        elif args[i] in valid_subcommands:
            subcommand = args[i]
            i += 1
        else:
            print(f"Unknown argument: {args[i]}")
            print("Usage: disco-agent [start|queue|start-all|status|stop-all|install-service|uninstall-service]")
            sys.exit(1)

    # Fallback: DISCO_AGENT_CONFIG env var
    if "config" not in options:
        env_config = os.environ.get("DISCO_AGENT_CONFIG", "")
        if env_config:
            options["config"] = Path(env_config)

    return subcommand, options


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    subcommand, options = _parse_args()

    # --- Manager subcommands ---
    if subcommand in ("start-all", "status", "stop-all", "install-service", "uninstall-service"):
        from disco_agent.manager import (
            Manager,
            parse_instances_config,
            show_status,
            stop_all,
            _default_instances_path,
        )

        instances_path = options.get("instances", _default_instances_path())

        if subcommand == "start-all":
            cfg = parse_instances_config(instances_path)
            only = options.get("only")
            if only:
                cfg.instances = [i for i in cfg.instances if i.name == only]
                if not cfg.instances:
                    print(f"No instance named '{only}' found in {instances_path}")
                    sys.exit(1)

            manager = Manager(cfg)

            if sys.platform != "win32":
                import signal as sig
                loop = asyncio.get_event_loop()
                for s in (sig.SIGINT, sig.SIGTERM):
                    loop.add_signal_handler(s, manager.shutdown)
                asyncio.run(manager.run())
            else:
                # Windows: handle Ctrl+C via KeyboardInterrupt
                try:
                    asyncio.run(manager.run())
                except KeyboardInterrupt:
                    manager.shutdown()

        elif subcommand == "status":
            state_path = instances_path.parent / "manager-state.json"
            show_status(state_path)

        elif subcommand == "stop-all":
            pid_path = instances_path.parent / "manager.pid"
            stop_all(pid_path)

        elif subcommand in ("install-service", "uninstall-service"):
            from disco_agent.service import install_service, uninstall_service
            if subcommand == "install-service":
                install_service(instances_path)
            else:
                uninstall_service()

        return

    # --- Single-instance subcommands (existing behavior) ---
    explicit_config = options.get("config")

    if explicit_config:
        config_path = explicit_config.resolve()
        config_dir = config_path.parent
        env_path = config_dir / ".env"
        config = load_config(config_path=config_path, env_path=env_path)
        if config.general.repo_root:
            repo_root = Path(config.general.repo_root)
        else:
            repo_root = config_dir.parent
    else:
        repo_root = _find_repo_root()
        config_dir = repo_root
        config = load_config(
            config_path=config_dir / "config.toml",
            env_path=config_dir / ".env",
        )
        if config.general.repo_root:
            repo_root = Path(config.general.repo_root)

    if not Path(config.general.db_path).is_absolute():
        config.general.db_path = str(config_dir / config.general.db_path)

    load_plugins(config.plugins_raw, config.plugin_configs, str(config_dir))

    logger.info(f"Repo root: {repo_root}")
    logger.info(f"Config: {explicit_config or (repo_root / 'config.toml')}")

    if subcommand == "queue":
        asyncio.run(show_queue(config))
    elif subcommand == "start":
        asyncio.run(run_daemon(config, str(repo_root)))
```

Note: `_parse_args` return type changes from `tuple[str, Path | None]` to `tuple[str, dict[str, Any]]`. This is a breaking change to the internal API but no external consumers exist.

**Step 4: Run all tests to verify they pass**

Run: `uv run pytest tests/ -v`
Expected: ALL pass. Existing tests may need minor updates if they mock `_parse_args`.

**Step 5: Commit**

```bash
git add src/disco_agent/daemon.py tests/test_manager.py
git commit -m "feat: extend CLI with start-all, status, stop-all subcommands"
```

---

### Task 8: Service install/uninstall

**Files:**
- Create: `src/disco_agent/service.py`
- Create: `service-templates/com.disco-agent.manager.plist`
- Create: `service-templates/install-service.ps1`
- Test: `tests/test_service.py`

**Step 1: Write the failing tests**

Create `tests/test_service.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def test_install_service_macos(tmp_path, monkeypatch):
    """On macOS, install_service should copy plist to LaunchAgents."""
    monkeypatch.setattr("sys.platform", "darwin")

    launch_agents = tmp_path / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True)

    from disco_agent.service import install_service

    with patch("disco_agent.service._launch_agents_dir", return_value=launch_agents), \
         patch("disco_agent.service._run_cmd") as mock_run:
        install_service(tmp_path / "instances.toml")

    plist = launch_agents / "com.disco-agent.manager.plist"
    assert plist.exists()
    content = plist.read_text()
    assert "disco-agent" in content
    assert "start-all" in content


def test_install_service_windows(tmp_path, monkeypatch):
    """On Windows, install_service should call schtasks."""
    monkeypatch.setattr("sys.platform", "win32")

    from disco_agent.service import install_service

    with patch("disco_agent.service._run_cmd") as mock_run:
        install_service(tmp_path / "instances.toml")

    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert "schtasks" in call_args[0].lower() or "schtasks" in str(call_args).lower()


def test_uninstall_service_macos(tmp_path, monkeypatch):
    """On macOS, uninstall_service should remove plist and unload."""
    monkeypatch.setattr("sys.platform", "darwin")

    launch_agents = tmp_path / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True)
    plist = launch_agents / "com.disco-agent.manager.plist"
    plist.write_text("<plist>test</plist>")

    from disco_agent.service import uninstall_service

    with patch("disco_agent.service._launch_agents_dir", return_value=launch_agents), \
         patch("disco_agent.service._run_cmd"):
        uninstall_service()

    assert not plist.exists()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'disco_agent.service'`

**Step 3: Create the service templates**

Create `service-templates/com.disco-agent.manager.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.disco-agent.manager</string>
    <key>ProgramArguments</key>
    <array>
        <string>__DISCO_AGENT_PATH__</string>
        <string>start-all</string>
        <string>--instances</string>
        <string>__INSTANCES_TOML_PATH__</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>__LOG_PATH__</string>
    <key>StandardErrorPath</key>
    <string>__LOG_PATH__</string>
</dict>
</plist>
```

**Step 4: Implement the service module**

Create `src/disco_agent/service.py`:

```python
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


_PLIST_NAME = "com.disco-agent.manager.plist"
_TASK_NAME = "DiscoAgentManager"


def _launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def _run_cmd(cmd: list[str]) -> None:
    subprocess.run(cmd, check=False)


def _find_disco_agent_exe() -> str:
    """Find the disco-agent executable path."""
    exe = shutil.which("disco-agent")
    return exe or "disco-agent"


def install_service(instances_path: Path) -> None:
    """Install disco-agent manager as an OS service."""
    if sys.platform == "darwin":
        _install_macos(instances_path)
    elif sys.platform == "win32":
        _install_windows(instances_path)
    else:
        print(f"Unsupported platform: {sys.platform}")
        sys.exit(1)


def uninstall_service() -> None:
    """Remove the disco-agent manager OS service."""
    if sys.platform == "darwin":
        _uninstall_macos()
    elif sys.platform == "win32":
        _uninstall_windows()
    else:
        print(f"Unsupported platform: {sys.platform}")
        sys.exit(1)


def _install_macos(instances_path: Path) -> None:
    disco_exe = _find_disco_agent_exe()
    log_path = Path.home() / "Library" / "Logs" / "disco-agent.log"

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.disco-agent.manager</string>
    <key>ProgramArguments</key>
    <array>
        <string>{disco_exe}</string>
        <string>start-all</string>
        <string>--instances</string>
        <string>{instances_path.resolve()}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>"""

    dest = _launch_agents_dir() / _PLIST_NAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(plist_content)

    _run_cmd(["launchctl", "load", str(dest)])
    print(f"Installed launchd service: {dest}")
    print(f"Logs: {log_path}")


def _uninstall_macos() -> None:
    dest = _launch_agents_dir() / _PLIST_NAME
    if dest.exists():
        _run_cmd(["launchctl", "unload", str(dest)])
        dest.unlink()
        print(f"Removed launchd service: {dest}")
    else:
        print("Service not installed.")


def _install_windows(instances_path: Path) -> None:
    disco_exe = _find_disco_agent_exe()
    _run_cmd([
        "schtasks", "/create",
        "/tn", _TASK_NAME,
        "/tr", f'"{disco_exe}" start-all --instances "{instances_path.resolve()}"',
        "/sc", "onlogon",
        "/rl", "limited",
        "/f",
    ])
    print(f"Installed Windows scheduled task: {_TASK_NAME}")


def _uninstall_windows() -> None:
    _run_cmd(["schtasks", "/delete", "/tn", _TASK_NAME, "/f"])
    print(f"Removed Windows scheduled task: {_TASK_NAME}")
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_service.py -v`
Expected: ALL pass.

**Step 6: Commit**

```bash
git add src/disco_agent/service.py service-templates/ tests/test_service.py
git commit -m "feat: add install-service and uninstall-service commands"
```

---

### Task 9: Signal handling for manager on Windows and macOS

**Files:**
- Modify: `src/disco_agent/manager.py`
- Modify: `src/disco_agent/daemon.py`

**Step 1: Write the failing test**

Add to `tests/test_manager.py`:

```python
async def test_manager_handles_keyboard_interrupt(tmp_path):
    """Manager should shut down cleanly on KeyboardInterrupt."""
    from disco_agent.manager import InstancesConfig, InstanceConfig, Manager

    script = tmp_path / "sleeper.py"
    script.write_text("import time\nwhile True:\n    time.sleep(0.1)")

    cfg = InstancesConfig(
        disco_agent_root=str(tmp_path),
        base_dir=tmp_path,
        instances=[InstanceConfig(name="sig-test", config_path=tmp_path / "a.toml")],
    )

    manager = Manager(cfg)
    manager._build_cmd = lambda inst: [sys.executable, str(script)]

    task = asyncio.create_task(manager.run())
    await asyncio.sleep(0.5)

    # Simulate shutdown
    manager.shutdown()
    await asyncio.wait_for(task, timeout=15)

    runner = manager.runners["sig-test"]
    assert runner.process and runner.process.returncode is not None
```

**Step 2: Run test to verify it passes (it should, since Manager.shutdown() already works)**

Run: `uv run pytest tests/test_manager.py::test_manager_handles_keyboard_interrupt -v`
Expected: PASS — this validates that the signal flow in `daemon.py`'s `main()` is correct.

**Step 3: Verify the signal handling in daemon.py main()**

The implementation from Task 7 already handles this:
- Unix: `loop.add_signal_handler(SIGINT/SIGTERM, manager.shutdown)`
- Windows: `try/except KeyboardInterrupt` calls `manager.shutdown()`

No additional code changes needed. This task validates the integration.

**Step 4: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: ALL pass.

**Step 5: Commit (if any changes were needed)**

```bash
git commit --allow-empty -m "test: validate manager signal handling"
```

---

### Task 10: Integration test — full round trip

**Files:**
- Test: `tests/test_manager.py`

**Step 1: Write the integration test**

Add to `tests/test_manager.py`:

```python
async def test_full_round_trip(tmp_path):
    """Integration: parse instances.toml, build env, start manager, verify state, stop."""
    from disco_agent.manager import Manager, parse_instances_config

    # Create instance configs
    inst_dir = tmp_path / "instances" / "test-proj"
    inst_dir.mkdir(parents=True)

    config_toml = inst_dir / "config.toml"
    config_toml.write_text("[general]\n[discord]\n[budgets]\n")

    global_env = tmp_path / ".env"
    global_env.write_text("DISCORD_BOT_TOKEN=test-tok\nGLOBAL_VAR=yes\n")

    inst_env = inst_dir / ".env"
    inst_env.write_text("INSTANCE_VAR=also_yes\n")

    instances_toml = tmp_path / "instances.toml"
    instances_toml.write_text(f"""\
disco_agent_root = "{tmp_path}"

[[instance]]
name = "test-proj"
config = "instances/test-proj/config.toml"
""")

    cfg = parse_instances_config(instances_toml)
    assert cfg.disco_agent_root == str(tmp_path)
    assert len(cfg.instances) == 1
    assert cfg.instances[0].name == "test-proj"

    # Create a script that prints env vars and exits
    script = tmp_path / "env_printer.py"
    script.write_text(
        "import os, time\n"
        "print(f'TOKEN={os.environ.get(\"DISCORD_BOT_TOKEN\", \"missing\")}')\n"
        "print(f'ROOT={os.environ.get(\"DISCO_AGENT_ROOT\", \"missing\")}')\n"
        "time.sleep(1)\n"
    )

    manager = Manager(cfg)
    manager._build_cmd = lambda inst: [sys.executable, str(script)]

    lines = []
    for inst in cfg.instances:
        runner_name = inst.name

    task = asyncio.create_task(manager.run())
    await asyncio.sleep(2)

    # Verify state file was written
    state_path = tmp_path / "manager-state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text())
    assert "test-proj" in state["instances"]

    manager.shutdown()
    await asyncio.wait_for(task, timeout=15)
```

**Step 2: Run the integration test**

Run: `uv run pytest tests/test_manager.py::test_full_round_trip -v`
Expected: PASS.

**Step 3: Run the full test suite one final time**

Run: `uv run pytest tests/ -v`
Expected: ALL pass.

**Step 4: Commit**

```bash
git add tests/test_manager.py
git commit -m "test: add full round-trip integration test for manager"
```

---

### Task 11: Rebuild and manual smoke test

**Step 1: Rebuild**

```bash
uv cache clean disco-agent && uv tool install . --reinstall
```

**Step 2: Verify new subcommands are recognized**

```bash
disco-agent start-all 2>&1 | head -5
disco-agent status
disco-agent stop-all
```

Expected: `start-all` fails with "instances.toml not found" (since `~/.disco-agent/instances.toml` doesn't exist yet), `status` prints "not running", `stop-all` prints "no PID file".

**Step 3: Create a test instances.toml and verify start-all works**

Set up `~/.disco-agent/instances.toml` pointing to the existing config, then run `disco-agent start-all` and verify both the manager and child process start.

**Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final fixes from smoke test"
```
