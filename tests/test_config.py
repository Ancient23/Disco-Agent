import os
from pathlib import Path

import pytest


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
analyze_warning_usd = 4.0
custom_warning_usd = 6.0
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
    assert config.budgets.analyze_warning_usd == 4.0
    assert config.budgets.custom_warning_usd == 6.0


def test_load_config_defaults(tmp_path):
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("""
[general]
[discord]
[budgets]
""")
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_BOT_TOKEN=tok\n")

    from disco_agent.config import load_config

    config = load_config(config_path=config_toml, env_path=env_file)
    assert config.general.poll_interval_seconds == 10
    assert config.budgets.analyze_warning_usd == 3.0
    assert config.budgets.custom_warning_usd == 5.0


def test_non_threaded_workflows_default_empty():
    from disco_agent.config import AgentConfig

    config = AgentConfig()
    assert config.discord.non_threaded_workflows == []


def test_non_threaded_workflows_loaded_from_toml(tmp_path):
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("""
[general]
[discord]
non_threaded_workflows = ["compile"]
[budgets]
""")
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_BOT_TOKEN=tok\n")

    from disco_agent.config import load_config

    config = load_config(config_path=config_toml, env_path=env_file)
    assert config.discord.non_threaded_workflows == ["compile"]


def test_load_config_missing_token_raises(tmp_path):
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("[general]\n[discord]\n[budgets]\n")
    env_file = tmp_path / ".env"
    env_file.write_text("")

    os.environ.pop("DISCORD_BOT_TOKEN", None)

    from disco_agent.config import load_config

    with pytest.raises(ValueError, match="DISCORD_BOT_TOKEN"):
        load_config(config_path=config_toml, env_path=env_file)


def test_config_has_no_ue_attrs():
    from disco_agent.config import AgentConfig

    config = AgentConfig()
    assert not hasattr(config, "ue")
    assert not hasattr(config, "conductor")
    assert not hasattr(config, "compile")


def test_config_loads_plugins_raw(tmp_path):
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("""
[general]
[discord]
[budgets]

[[plugins]]
name = "ue"
type = "code"
path = "plugins/ue"

[[plugins]]
name = "conductor"
type = "session"
path = "C:/Source/conductor-agent"
""")
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_BOT_TOKEN=tok\n")

    from disco_agent.config import load_config

    config = load_config(config_path=config_toml, env_path=env_file)
    assert len(config.plugins_raw) == 2
    assert config.plugins_raw[0]["name"] == "ue"
    assert config.plugins_raw[0]["type"] == "code"
    assert config.plugins_raw[1]["name"] == "conductor"
    assert config.plugins_raw[1]["type"] == "session"


def test_config_loads_plugin_configs(tmp_path):
    config_toml = tmp_path / "config.toml"
    config_toml.write_text("""
[general]
[discord]
[budgets]

[plugin-config.ue]
engine_path = "C:/Program Files/Epic Games/UE_5.7/Engine"
project_path = "Proj/MyProject/MyProject.uproject"
platform = "Win64"
max_retries = 3
""")
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_BOT_TOKEN=tok\n")

    from disco_agent.config import load_config

    config = load_config(config_path=config_toml, env_path=env_file)
    assert "ue" in config.plugin_configs
    assert config.plugin_configs["ue"]["engine_path"] == "C:/Program Files/Epic Games/UE_5.7/Engine"
    assert config.plugin_configs["ue"]["platform"] == "Win64"
    assert config.plugin_configs["ue"]["max_retries"] == 3
