from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from disco_agent.workflows import WORKFLOW_REGISTRY
from disco_agent.workflows.session import AgentSessionWorkflow

logger = logging.getLogger(__name__)


def _make_session_workflow_class(
    command_name: str,
    session_cwd: str,
    allowed_tools: list[str],
    budget_warning_usd: float,
) -> type:
    """Dynamically create a workflow class for a session plugin command."""

    class _SessionPluginWorkflow(AgentSessionWorkflow):
        def __init__(self, task, queue, notifier, repo_root, **kwargs):
            super().__init__(
                task=task,
                queue=queue,
                notifier=notifier,
                session_cwd=session_cwd,
                allowed_tools=allowed_tools,
                budget_warning_usd=budget_warning_usd,
                repo_root=repo_root,
            )

    _SessionPluginWorkflow.__name__ = f"SessionPlugin_{command_name}"
    _SessionPluginWorkflow.__qualname__ = f"SessionPlugin_{command_name}"
    return _SessionPluginWorkflow


def _load_session_plugin(plugin: dict[str, Any]) -> list[str]:
    """Register session plugin commands. Returns list of registered command names."""
    commands = plugin.get("commands", [])
    path = plugin["path"]
    allowed_tools = plugin.get("allowed_tools", ["Read", "Glob", "Grep", "Bash"])
    budget = plugin.get("budget_warning_usd", 5.0)

    registered = []
    for cmd in commands:
        if cmd in WORKFLOW_REGISTRY:
            raise ValueError(
                f"Command '{cmd}' already registered — "
                f"plugin '{plugin['name']}' conflicts with an existing workflow"
            )
        cls = _make_session_workflow_class(cmd, path, allowed_tools, budget)
        WORKFLOW_REGISTRY[cmd] = cls
        registered.append(cmd)
        logger.info("Registered session plugin command: !%s -> %s", cmd, path)

    return registered


def _load_code_plugin(plugin: dict[str, Any], config_dir: str, plugin_configs: dict[str, Any]) -> None:
    """Load a code plugin by importing its workflows.py module."""
    plugin_path = Path(plugin["path"])
    if not plugin_path.is_absolute():
        plugin_path = Path(config_dir) / plugin_path

    workflows_file = plugin_path / "workflows.py"
    if not workflows_file.exists():
        raise FileNotFoundError(
            f"Code plugin '{plugin['name']}': {workflows_file} not found"
        )

    module_name = f"disco_agent_plugin_{plugin['name'].replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, str(workflows_file))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    # Add config_dir (repo root) to sys.path so absolute imports like
    # "from plugins.ue.config import ..." resolve correctly.
    if config_dir not in sys.path:
        sys.path.insert(0, config_dir)

    spec.loader.exec_module(module)

    # Pass plugin config if available
    name = plugin["name"]
    if name in plugin_configs and hasattr(module, "set_plugin_config"):
        module.set_plugin_config(plugin_configs[name])

    logger.info("Loaded code plugin '%s' from %s", plugin["name"], workflows_file)


def load_plugins(
    plugins_raw: list[dict[str, Any]],
    plugin_configs: dict[str, dict[str, Any]],
    config_dir: str,
) -> dict[str, dict[str, Any]]:
    """Load all plugins from config. Returns plugin_configs for downstream use."""
    for plugin in plugins_raw:
        ptype = plugin.get("type", "session")
        name = plugin.get("name", "unnamed")

        if ptype == "session":
            _load_session_plugin(plugin)
        elif ptype == "code":
            _load_code_plugin(plugin, config_dir, plugin_configs)
        else:
            logger.warning("Unknown plugin type '%s' for plugin '%s'", ptype, name)

    return plugin_configs
