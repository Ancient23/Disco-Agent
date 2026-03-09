import os
import sys
from pathlib import Path

import pytest


def test_parse_instances_toml(tmp_path):
    """Parse valid instances.toml, verify disco_agent_root, instance count, resolved config paths."""
    instances_toml = tmp_path / "instances.toml"
    instances_toml.write_text("""
disco_agent_root = "C:/Source/Disco-Agent"

[[instances]]
name = "bot-alpha"
config = "alpha/config.toml"

[[instances]]
name = "bot-beta"
config = "beta/config.toml"
env = "beta/.env.beta"
""")

    # Create the config files so the paths are valid
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "config.toml").write_text("[general]\n")
    (tmp_path / "alpha" / ".env").write_text("TOKEN=alpha\n")
    (tmp_path / "beta").mkdir()
    (tmp_path / "beta" / "config.toml").write_text("[general]\n")
    (tmp_path / "beta" / ".env.beta").write_text("TOKEN=beta\n")

    from disco_agent.manager import parse_instances_config

    cfg = parse_instances_config(instances_toml)

    assert cfg.disco_agent_root == "C:/Source/Disco-Agent"
    assert len(cfg.instances) == 2

    alpha = cfg.instances[0]
    assert alpha.name == "bot-alpha"
    assert alpha.config_path == tmp_path / "alpha" / "config.toml"
    # No explicit env, so it should default to .env alongside config.toml
    assert alpha.env_path == tmp_path / "alpha" / ".env"

    beta = cfg.instances[1]
    assert beta.name == "bot-beta"
    assert beta.config_path == tmp_path / "beta" / "config.toml"
    # Explicit env path specified
    assert beta.env_path == tmp_path / "beta" / ".env.beta"


def test_parse_instances_toml_missing_file(tmp_path):
    """Raise FileNotFoundError for missing instances.toml."""
    from disco_agent.manager import parse_instances_config

    with pytest.raises(FileNotFoundError):
        parse_instances_config(tmp_path / "nonexistent" / "instances.toml")


def test_parse_instances_toml_default_env_missing(tmp_path):
    """When no env key and no .env alongside config.toml, env_path should be None."""
    instances_toml = tmp_path / "instances.toml"
    instances_toml.write_text("""
disco_agent_root = "C:/Source/Disco-Agent"

[[instances]]
name = "bot-no-env"
config = "noenv/config.toml"
""")
    (tmp_path / "noenv").mkdir()
    (tmp_path / "noenv" / "config.toml").write_text("[general]\n")
    # Intentionally do NOT create a .env file

    from disco_agent.manager import parse_instances_config

    cfg = parse_instances_config(instances_toml)
    assert cfg.instances[0].env_path is None


def test_build_instance_env_global_only(tmp_path):
    """Only global .env, verify all vars come from it."""
    global_env = tmp_path / "global.env"
    global_env.write_text("GLOBAL_KEY=global_value\nSHARED=from_global\n")

    from disco_agent.manager import build_instance_env

    env = build_instance_env(global_env, None)

    assert env["GLOBAL_KEY"] == "global_value"
    assert env["SHARED"] == "from_global"


def test_build_instance_env_instance_overrides(tmp_path):
    """Instance .env overrides global + adds new keys."""
    global_env = tmp_path / "global.env"
    global_env.write_text("SHARED=from_global\nGLOBAL_ONLY=gval\n")

    instance_env = tmp_path / "instance.env"
    instance_env.write_text("SHARED=from_instance\nINSTANCE_ONLY=ival\n")

    from disco_agent.manager import build_instance_env

    env = build_instance_env(global_env, instance_env)

    assert env["SHARED"] == "from_instance"
    assert env["GLOBAL_ONLY"] == "gval"
    assert env["INSTANCE_ONLY"] == "ival"


def test_build_instance_env_no_global(tmp_path):
    """No global .env file, instance .env is sole source."""
    instance_env = tmp_path / "instance.env"
    instance_env.write_text("INSTANCE_KEY=ivalue\n")

    from disco_agent.manager import build_instance_env

    # Pass a non-existent global path
    env = build_instance_env(tmp_path / "nonexistent.env", instance_env)

    assert env["INSTANCE_KEY"] == "ivalue"


def test_parse_env_file(tmp_path):
    """parse_env_file handles comments, blank lines, and key=value pairs."""
    env_file = tmp_path / ".env"
    env_file.write_text("""
# This is a comment
KEY1=value1
  KEY2 = value2

# Another comment
KEY3=value with spaces
""")

    from disco_agent.manager import parse_env_file

    result = parse_env_file(env_file)
    assert result["KEY1"] == "value1"
    assert result["KEY2"] == "value2"
    assert result["KEY3"] == "value with spaces"
    assert len(result) == 3


def test_parse_env_file_missing(tmp_path):
    """parse_env_file returns empty dict for missing file."""
    from disco_agent.manager import parse_env_file

    result = parse_env_file(tmp_path / "nope.env")
    assert result == {}


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
