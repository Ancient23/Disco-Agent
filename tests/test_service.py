from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def test_install_service_macos(tmp_path, monkeypatch):
    """On macOS, install_service should copy plist to LaunchAgents."""
    monkeypatch.setattr("sys.platform", "darwin")

    launch_agents = tmp_path / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True)

    from disco_agent.service import install_service

    with patch("disco_agent.service._launch_agents_dir", return_value=launch_agents), \
         patch("disco_agent.service._run_cmd") as mock_run:
        install_service(tmp_path / "instances.toml")

    plist = launch_agents / "com.disco-agent.manager.plist"
    assert plist.exists()
    content = plist.read_text()
    assert "disco-agent" in content
    assert "start-all" in content


def test_install_service_windows(tmp_path, monkeypatch):
    """On Windows, install_service should call schtasks."""
    monkeypatch.setattr("sys.platform", "win32")

    from disco_agent.service import install_service

    with patch("disco_agent.service._run_cmd") as mock_run:
        install_service(tmp_path / "instances.toml")

    mock_run.assert_called_once()
    call_args = str(mock_run.call_args)
    assert "schtasks" in call_args.lower()


def test_uninstall_service_macos(tmp_path, monkeypatch):
    """On macOS, uninstall_service should remove plist and unload."""
    monkeypatch.setattr("sys.platform", "darwin")

    launch_agents = tmp_path / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True)
    plist = launch_agents / "com.disco-agent.manager.plist"
    plist.write_text("<plist>test</plist>")

    from disco_agent.service import uninstall_service

    with patch("disco_agent.service._launch_agents_dir", return_value=launch_agents), \
         patch("disco_agent.service._run_cmd"):
        uninstall_service()

    assert not plist.exists()
