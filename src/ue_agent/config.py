from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GeneralConfig:
    poll_interval_seconds: int = 10
    db_path: str = "tasks.db"


@dataclass
class UEConfig:
    engine_path: Path = Path("C:/Program Files/Epic Games/UE_5.3/Engine")
    project_path: str = "Proj/CitySample/CitySample.uproject"
    platform: str = "Win64"
    build_flags: list[str] = field(
        default_factory=lambda: ["-cook", "-stage", "-pak", "-unattended", "-nullrhi"]
    )


@dataclass
class DiscordConfig:
    bot_token: str = ""
    command_channel_id: str = ""
    required_role: str = "BuildOps"


@dataclass
class ConductorConfig:
    conductor_agent_path: str = "conductor-agent"


@dataclass
class BudgetConfig:
    compile_warning_usd: float = 5.0
    package_warning_usd: float = 5.0
    submit_warning_usd: float = 2.0
    analyze_warning_usd: float = 3.0
    custom_warning_usd: float = 5.0


@dataclass
class CompileConfig:
    max_retries: int = 3
    error_tail_lines: int = 200


@dataclass
class AgentConfig:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    ue: UEConfig = field(default_factory=UEConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    conductor: ConductorConfig = field(default_factory=ConductorConfig)
    budgets: BudgetConfig = field(default_factory=BudgetConfig)
    compile: CompileConfig = field(default_factory=CompileConfig)


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
        if "ue" in raw:
            _apply_section(config.ue, raw["ue"])
        if "discord" in raw:
            _apply_section(config.discord, raw["discord"])
        if "conductor" in raw:
            _apply_section(config.conductor, raw["conductor"])
        if "budgets" in raw:
            _apply_section(config.budgets, raw["budgets"])
        if "compile" in raw:
            _apply_section(config.compile, raw["compile"])

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
