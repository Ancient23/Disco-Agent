from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


_PLIST_NAME = "com.disco-agent.manager.plist"
_TASK_NAME = "DiscoAgentManager"


def _launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def _run_cmd(cmd: list[str]) -> None:
    subprocess.run(cmd, check=False)


def _find_disco_agent_exe() -> str:
    """Find the disco-agent executable path."""
    exe = shutil.which("disco-agent")
    return exe or "disco-agent"


def install_service(instances_path: Path) -> None:
    """Install disco-agent manager as an OS service."""
    if sys.platform == "darwin":
        _install_macos(instances_path)
    elif sys.platform == "win32":
        _install_windows(instances_path)
    else:
        print(f"Unsupported platform: {sys.platform}")
        sys.exit(1)


def uninstall_service() -> None:
    """Remove the disco-agent manager OS service."""
    if sys.platform == "darwin":
        _uninstall_macos()
    elif sys.platform == "win32":
        _uninstall_windows()
    else:
        print(f"Unsupported platform: {sys.platform}")
        sys.exit(1)


def _install_macos(instances_path: Path) -> None:
    disco_exe = _find_disco_agent_exe()
    log_path = Path.home() / "Library" / "Logs" / "disco-agent.log"

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.disco-agent.manager</string>
    <key>ProgramArguments</key>
    <array>
        <string>{disco_exe}</string>
        <string>start-all</string>
        <string>--instances</string>
        <string>{instances_path.resolve()}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>"""

    dest = _launch_agents_dir() / _PLIST_NAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(plist_content)

    _run_cmd(["launchctl", "load", str(dest)])
    print(f"Installed launchd service: {dest}")
    print(f"Logs: {log_path}")


def _uninstall_macos() -> None:
    dest = _launch_agents_dir() / _PLIST_NAME
    if dest.exists():
        _run_cmd(["launchctl", "unload", str(dest)])
        dest.unlink()
        print(f"Removed launchd service: {dest}")
    else:
        print("Service not installed.")


def _install_windows(instances_path: Path) -> None:
    disco_exe = _find_disco_agent_exe()
    _run_cmd([
        "schtasks", "/create",
        "/tn", _TASK_NAME,
        "/tr", f'"{disco_exe}" start-all --instances "{instances_path.resolve()}"',
        "/sc", "onlogon",
        "/rl", "limited",
        "/f",
    ])
    print(f"Installed Windows scheduled task: {_TASK_NAME}")


def _uninstall_windows() -> None:
    _run_cmd(["schtasks", "/delete", "/tn", _TASK_NAME, "/f"])
    print(f"Removed Windows scheduled task: {_TASK_NAME}")
