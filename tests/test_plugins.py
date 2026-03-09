from __future__ import annotations

import textwrap
from unittest.mock import AsyncMock, MagicMock

import pytest

from disco_agent.plugins import load_plugins
from disco_agent.workflows import WORKFLOW_REGISTRY


@pytest.fixture(autouse=True)
def clean_registry():
    before = set(WORKFLOW_REGISTRY.keys())
    yield
    for key in set(WORKFLOW_REGISTRY.keys()) - before:
        del WORKFLOW_REGISTRY[key]


def test_load_session_plugin_registers_commands():
    """Session plugin with two commands should register both in WORKFLOW_REGISTRY."""
    plugins = [
        {
            "name": "ops",
            "type": "session",
            "path": "/tmp/ops",
            "commands": ["deploy", "rollback"],
        }
    ]
    load_plugins(plugins, {}, ".")

    assert "deploy" in WORKFLOW_REGISTRY
    assert "rollback" in WORKFLOW_REGISTRY


def test_load_code_plugin(tmp_path):
    """Code plugin with a workflows.py that registers a command via @register."""
    plugin_dir = tmp_path / "my_plugin"
    plugin_dir.mkdir()
    workflows_file = plugin_dir / "workflows.py"
    workflows_file.write_text(
        textwrap.dedent("""\
            from disco_agent.workflows import register
            from disco_agent.workflows.base import BaseWorkflow, WorkflowResult

            @register("my_cmd")
            class MyCmdWorkflow(BaseWorkflow):
                async def execute(self):
                    return WorkflowResult(success=True, output="hello")
        """)
    )

    plugins = [
        {
            "name": "my-plugin",
            "type": "code",
            "path": str(plugin_dir),
        }
    ]
    load_plugins(plugins, {}, str(tmp_path))

    assert "my_cmd" in WORKFLOW_REGISTRY


def test_duplicate_command_raises():
    """Two session plugins both registering 'deploy' should raise ValueError."""
    plugins = [
        {
            "name": "ops-a",
            "type": "session",
            "path": "/tmp/a",
            "commands": ["deploy"],
        },
        {
            "name": "ops-b",
            "type": "session",
            "path": "/tmp/b",
            "commands": ["deploy"],
        },
    ]

    with pytest.raises(ValueError, match=r"deploy.*already registered"):
        load_plugins(plugins, {}, ".")


def test_session_plugin_workflow_has_correct_cwd():
    """Instantiate the workflow class and verify session_cwd and allowed_tools."""
    plugins = [
        {
            "name": "checker",
            "type": "session",
            "path": "/opt/checker",
            "commands": ["check"],
            "allowed_tools": ["Read", "Grep"],
            "budget_warning_usd": 2.5,
        }
    ]
    load_plugins(plugins, {}, ".")

    cls = WORKFLOW_REGISTRY["check"]

    task = {
        "id": 1,
        "workflow": "check",
        "project": "test",
        "discord_channel_id": "ch1",
        "discord_message_id": "msg1",
        "params": "{}",
    }
    queue = AsyncMock()
    notifier = AsyncMock()
    notifier.get_thread = MagicMock(return_value=None)

    wf = cls(task=task, queue=queue, notifier=notifier, repo_root="/tmp/repo")
    assert wf.session_cwd == "/opt/checker"
    assert wf.allowed_tools == ["Read", "Grep"]


def test_no_plugins_is_fine():
    """Empty plugin list should not raise."""
    result = load_plugins([], {}, ".")
    assert result == {}


def test_plugin_config_passed_to_code_plugin(tmp_path):
    """Code plugin with set_plugin_config should receive its config dict."""
    plugin_dir = tmp_path / "configurable"
    plugin_dir.mkdir()
    workflows_file = plugin_dir / "workflows.py"
    workflows_file.write_text(
        textwrap.dedent("""\
            _received_config = None

            def set_plugin_config(cfg):
                global _received_config
                _received_config = cfg
        """)
    )

    plugins = [
        {
            "name": "configurable",
            "type": "code",
            "path": str(plugin_dir),
        }
    ]
    plugin_configs = {"configurable": {"api_key": "secret123", "timeout": 30}}
    load_plugins(plugins, plugin_configs, str(tmp_path))

    import sys

    module = sys.modules["disco_agent_plugin_configurable"]
    assert module._received_config == {"api_key": "secret123", "timeout": 30}


def test_code_plugin_resolves_path_from_disco_agent_root(tmp_path, monkeypatch):
    """When DISCO_AGENT_ROOT is set, relative plugin paths resolve against it."""
    # Create the plugin under a "root" directory that is NOT config_dir
    root_dir = tmp_path / "agent_root"
    root_dir.mkdir()
    plugin_dir = root_dir / "plugins" / "myplugin"
    plugin_dir.mkdir(parents=True)
    workflows_file = plugin_dir / "workflows.py"
    workflows_file.write_text(
        textwrap.dedent("""\
            from disco_agent.workflows import register
            from disco_agent.workflows.base import BaseWorkflow, WorkflowResult

            @register("root_cmd")
            class RootCmdWorkflow(BaseWorkflow):
                async def execute(self):
                    return WorkflowResult(success=True, output="from root")
        """)
    )

    # config_dir points somewhere else entirely
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    monkeypatch.setenv("DISCO_AGENT_ROOT", str(root_dir))

    plugins = [
        {
            "name": "myplugin",
            "type": "code",
            "path": "plugins/myplugin",  # relative path
        }
    ]
    load_plugins(plugins, {}, str(config_dir))

    assert "root_cmd" in WORKFLOW_REGISTRY


def test_code_plugin_falls_back_to_config_dir_without_env(tmp_path, monkeypatch):
    """Without DISCO_AGENT_ROOT, relative paths resolve against config_dir."""
    monkeypatch.delenv("DISCO_AGENT_ROOT", raising=False)

    plugin_dir = tmp_path / "plugins" / "fallback"
    plugin_dir.mkdir(parents=True)
    workflows_file = plugin_dir / "workflows.py"
    workflows_file.write_text(
        textwrap.dedent("""\
            from disco_agent.workflows import register
            from disco_agent.workflows.base import BaseWorkflow, WorkflowResult

            @register("fallback_cmd")
            class FallbackCmdWorkflow(BaseWorkflow):
                async def execute(self):
                    return WorkflowResult(success=True, output="fallback")
        """)
    )

    plugins = [
        {
            "name": "fallback",
            "type": "code",
            "path": "plugins/fallback",  # relative path
        }
    ]
    load_plugins(plugins, {}, str(tmp_path))

    assert "fallback_cmd" in WORKFLOW_REGISTRY
