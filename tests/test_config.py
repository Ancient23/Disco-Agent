import os
from pathlib import Path

import pytest


def test_load_config_from_toml(tmp_path):
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("""
[general]
poll_interval_seconds = 15
db_path = "my_tasks.db"

[ue]
engine_path = "C:/UE5"
project_path = "Proj/CitySample/CitySample.uproject"
platform = "Win64"
build_flags = ["-cook", "-stage"]

[discord]
command_channel_id = "123456"
required_role = "Builders"

[conductor]
conductor_agent_path = "conductor-agent"

[budgets]
compile_warning_usd = 10.0
package_warning_usd = 10.0
submit_warning_usd = 5.0
analyze_warning_usd = 3.0
custom_warning_usd = 5.0

[compile]
max_retries = 5
error_tail_lines = 100
""")
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_BOT_TOKEN=test-token-123\n")

    from ue_agent.config import load_config

    config = load_config(config_path=config_toml, env_path=env_file)
    assert config.general.poll_interval_seconds == 15
    assert config.general.db_path == "my_tasks.db"
    assert config.ue.engine_path == Path("C:/UE5")
    assert config.ue.platform == "Win64"
    assert config.discord.command_channel_id == "123456"
    assert config.discord.required_role == "Builders"
    assert config.discord.bot_token == "test-token-123"
    assert config.budgets.compile_warning_usd == 10.0
    assert config.compile.max_retries == 5


def test_load_config_defaults(tmp_path):
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("""
[general]
[ue]
engine_path = "C:/UE5"
[discord]
[conductor]
[budgets]
[compile]
""")
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_BOT_TOKEN=tok\n")

    from ue_agent.config import load_config

    config = load_config(config_path=config_toml, env_path=env_file)
    assert config.general.poll_interval_seconds == 10
    assert config.compile.max_retries == 3
    assert config.budgets.compile_warning_usd == 5.0


def test_non_threaded_workflows_default_empty():
    from ue_agent.config import AgentConfig

    config = AgentConfig()
    assert config.discord.non_threaded_workflows == []


def test_non_threaded_workflows_loaded_from_toml(tmp_path):
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("""
[general]
[ue]
[discord]
non_threaded_workflows = ["compile"]
[conductor]
[budgets]
[compile]
""")
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_BOT_TOKEN=tok\n")

    from ue_agent.config import load_config

    config = load_config(config_path=config_toml, env_path=env_file)
    assert config.discord.non_threaded_workflows == ["compile"]


def test_load_config_missing_token_raises(tmp_path):
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("[general]\n[ue]\n[discord]\n[conductor]\n[budgets]\n[compile]\n")
    env_file = tmp_path / ".env"
    env_file.write_text("")

    os.environ.pop("DISCORD_BOT_TOKEN", None)

    from ue_agent.config import load_config

    with pytest.raises(ValueError, match="DISCORD_BOT_TOKEN"):
        load_config(config_path=config_toml, env_path=env_file)
