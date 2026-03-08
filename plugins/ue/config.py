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
    """Parse a raw dict (from [plugin-config.ue]) into UEPluginConfig."""
    config = UEPluginConfig()
    for key, value in raw.items():
        if hasattr(config, key):
            current = getattr(config, key)
            if isinstance(current, Path):
                setattr(config, key, Path(value))
            else:
                setattr(config, key, value)
    return config
