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
