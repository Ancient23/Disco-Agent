import asyncio
import json
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


async def test_manager_starts_and_stops_instances(tmp_path):
    """Manager should start instances and stop them on shutdown."""
    import asyncio

    from disco_agent.manager import InstanceConfig, InstancesConfig, Manager

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


def test_show_status_reads_state_file(tmp_path, capsys):
    """show_status should pretty-print the manager-state.json contents."""
    import json

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
    pid_file = tmp_path / "manager.pid"

    show_status(state_file, pid_file)

    output = capsys.readouterr().out
    assert "proj-a" in output
    assert "running" in output
    assert "proj-b" in output
    assert "not running (stale state)" in output


def test_show_status_missing_file(tmp_path, capsys):
    """show_status should print a message when no state file exists."""
    from disco_agent.manager import show_status

    show_status(tmp_path / "nope.json", tmp_path / "manager.pid")
    output = capsys.readouterr().out
    assert "not running" in output.lower()


def test_stop_all_sends_signal(tmp_path):
    """stop_all should read PID file and attempt to terminate the process."""
    from disco_agent.manager import stop_all

    pid_file = tmp_path / "manager.pid"
    pid_file.write_text("99999999")  # non-existent PID

    # Should not raise even if process doesn't exist
    stop_all(pid_file)


def test_parse_args_start_all(monkeypatch):
    """start-all subcommand should be parsed with --instances and --only."""
    monkeypatch.setattr("sys.argv", ["disco-agent", "start-all", "--instances", "/tmp/i.toml", "--only", "proj-a"])
    from disco_agent.daemon import _parse_args
    sub, opts = _parse_args()
    assert sub == "start-all"
    assert opts["instances"] == Path("/tmp/i.toml")
    assert opts["only"] == "proj-a"


def test_parse_args_status(monkeypatch):
    """status subcommand should be recognized."""
    monkeypatch.setattr("sys.argv", ["disco-agent", "status"])
    from disco_agent.daemon import _parse_args
    sub, opts = _parse_args()
    assert sub == "status"


def test_parse_args_stop_all(monkeypatch):
    """stop-all subcommand should be recognized."""
    monkeypatch.setattr("sys.argv", ["disco-agent", "stop-all"])
    from disco_agent.daemon import _parse_args
    sub, opts = _parse_args()
    assert sub == "stop-all"


def test_parse_args_existing_start(monkeypatch):
    """Existing start subcommand with --config should still work."""
    monkeypatch.setattr("sys.argv", ["disco-agent", "start", "--config", "/tmp/c.toml"])
    from disco_agent.daemon import _parse_args
    sub, opts = _parse_args()
    assert sub == "start"
    assert opts["config"] == Path("/tmp/c.toml")


def test_parse_args_default_start(monkeypatch):
    """No subcommand defaults to start."""
    monkeypatch.delenv("DISCO_AGENT_CONFIG", raising=False)
    monkeypatch.setattr("sys.argv", ["disco-agent"])
    from disco_agent.daemon import _parse_args
    sub, opts = _parse_args()
    assert sub == "start"


async def test_manager_handles_shutdown_cleanly(tmp_path):
    """Manager should shut down cleanly when shutdown() is called."""
    from disco_agent.manager import InstanceConfig, InstancesConfig, Manager

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

    # Simulate shutdown signal
    manager.shutdown()
    await asyncio.wait_for(task, timeout=15)

    runner = manager.runners["sig-test"]
    assert runner.process and runner.process.returncode is not None


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

    root_str = str(tmp_path).replace("\\", "/")
    instances_toml = tmp_path / "instances.toml"
    instances_toml.write_text(
        f'disco_agent_root = "{root_str}"\n\n'
        f'[[instances]]\nname = "test-proj"\nconfig = "instances/test-proj/config.toml"\n'
    )

    cfg = parse_instances_config(instances_toml)
    assert cfg.disco_agent_root == root_str
    assert len(cfg.instances) == 1
    assert cfg.instances[0].name == "test-proj"

    # Create a script that prints env vars and sleeps briefly
    script = tmp_path / "env_printer.py"
    script.write_text(
        "import os, time\n"
        "print(f'TOKEN={os.environ.get(\"DISCORD_BOT_TOKEN\", \"missing\")}')\n"
        "print(f'ROOT={os.environ.get(\"DISCO_AGENT_ROOT\", \"missing\")}')\n"
        "time.sleep(1)\n"
    )

    manager = Manager(cfg)
    manager._build_cmd = lambda inst: [sys.executable, str(script)]

    task = asyncio.create_task(manager.run())
    await asyncio.sleep(2)

    # Verify state file was written
    state_path = tmp_path / "manager-state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text())
    assert "test-proj" in state["instances"]

    # Verify PID file was written
    pid_path = tmp_path / "manager.pid"
    assert pid_path.exists()

    manager.shutdown()
    await asyncio.wait_for(task, timeout=15)

    # PID file should be cleaned up after shutdown
    assert not pid_path.exists()
