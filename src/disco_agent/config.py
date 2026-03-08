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
        if "general" in raw:
            _apply_section(config.general, raw["general"])
        if "discord" in raw:
            _apply_section(config.discord, raw["discord"])
        if "budgets" in raw:
            _apply_section(config.budgets, raw["budgets"])
        config.plugins_raw = raw.get("plugins", [])
        config.plugin_configs = raw.get("plugin-config", {})

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
