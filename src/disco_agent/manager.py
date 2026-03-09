from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BACKOFF_SEQUENCE = [1, 5, 30, 60]
_HEALTHY_THRESHOLD_SECONDS = 300  # 5 minutes


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
    """Parse a .env file into a dict. Skip comments and blank lines.

    Returns empty dict if the file doesn't exist.
    """
    result: dict[str, str] = {}
    path = Path(path)
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
    """Build merged environment: os.environ + global .env + instance .env overlay.

    Instance values override global values for the same keys.
    """
    env = dict(os.environ)

    if global_env_path is not None:
        global_vars = parse_env_file(Path(global_env_path))
        env.update(global_vars)

    if instance_env_path is not None:
        instance_vars = parse_env_file(Path(instance_env_path))
        env.update(instance_vars)

    return env


def parse_instances_config(path: Path) -> InstancesConfig:
    """Parse instances.toml into an InstancesConfig.

    Resolves ``config`` paths relative to the instances.toml directory.
    For ``env``: if the key is specified, use it (resolved relative to the
    instances.toml dir). Otherwise, default to ``.env`` alongside the
    config.toml if that file exists.

    Raises FileNotFoundError if the instances.toml doesn't exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"instances.toml not found: {path}")

    base_dir = path.parent

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    disco_agent_root = raw.get("disco_agent_root", "")

    instances: list[InstanceConfig] = []
    for entry in raw.get("instances", []):
        name = entry["name"]
        config_path = (base_dir / entry["config"]).resolve()

        if "env" in entry:
            env_path: Path | None = (base_dir / entry["env"]).resolve()
        else:
            # Default: .env alongside config.toml, only if it exists
            default_env = config_path.parent / ".env"
            env_path = default_env if default_env.exists() else None

        instances.append(
            InstanceConfig(name=name, config_path=config_path, env_path=env_path)
        )

    return InstancesConfig(
        disco_agent_root=disco_agent_root,
        instances=instances,
        base_dir=base_dir,
    )


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
