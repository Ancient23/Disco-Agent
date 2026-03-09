# Multi-Instance Daemon Manager Design

**Date:** 2026-03-08
**Status:** Approved

## Problem

Running multiple disco-agent daemons (one per repo/project) requires manually launching separate processes with `--config` flags. No unified way to manage, monitor, or auto-restart instances. No cross-platform service installation.

## Decision Summary

- **Approach:** Subprocess spawner (each instance is an isolated OS process)
- **Auto-restart:** Yes, with exponential backoff (1s -> 5s -> 30s -> 60s, resets after 5min healthy)
- **Process model:** Foreground manager process + shipped service templates with install script
- **Logging:** Stdout with `[instance-name]` prefixes
- **CLI:** New subcommands on existing `disco-agent` entry point

## File Layout

```
~/.disco-agent/
├── instances.toml              # instance definitions
├── .env                        # global env (shared bot token)
├── manager.pid                 # PID file for running manager
├── manager-state.json          # per-instance status for `disco-agent status`
└── instances/
    ├── imp-ue-misc/
    │   ├── config.toml         # standard disco-agent config
    │   ├── .env                # optional, overrides+extends global .env
    │   └── tasks.db            # isolated task queue
    └── other-project/
        ├── config.toml
        └── tasks.db
```

## instances.toml Format

```toml
# Root where disco-agent source/plugins live.
# Relative plugin paths in instance configs resolve against this.
disco_agent_root = "C:/Source/Disco-Agent"

[[instances]]
name = "imp-ue-misc"
config = "instances/imp-ue-misc/config.toml"   # relative to instances.toml dir

[[instances]]
name = "other-project"
config = "instances/other-project/config.toml"
```

- `config` paths resolve relative to the directory containing `instances.toml`
- `.env` defaults to the same directory as the instance's config.toml

## .env Layering

The manager handles env layering before spawning children:

1. Read `~/.disco-agent/.env` (global) -> set env vars
2. Read instance-level `.env` if it exists -> overlay (override same keys, add new keys)
3. Pass merged environment to subprocess via `env` parameter

`config.py` is unchanged. By the time the child process runs, the environment has the correct values.

## New Module: `src/disco_agent/manager.py`

Responsibilities:

1. **Parse instances.toml** -- read `disco_agent_root` and instance list
2. **Resolve paths** -- config paths relative to instances.toml dir
3. **Env layering** -- global .env, then per-instance .env overlay
4. **Spawn children** -- `disco-agent start --config <resolved_path>` as subprocesses, setting `DISCO_AGENT_ROOT` env var
5. **Prefix stdout/stderr** -- read child output line-by-line, prefix with `[instance-name]`
6. **Auto-restart with backoff** -- 1s -> 5s -> 30s -> 60s; reset after 5 minutes of healthy uptime
7. **State file** -- write `manager-state.json` on state changes (instance start/stop/restart)
8. **PID file** -- write `manager.pid` on start, remove on clean exit
9. **Graceful shutdown** -- on SIGINT/SIGTERM (Ctrl+C on Windows), terminate children, wait 10s, force-kill

## CLI Changes

All additions to the existing `disco-agent` entry point in `daemon.py`:

```
disco-agent start [--config PATH]                        # unchanged
disco-agent queue [--config PATH]                        # unchanged
disco-agent start-all [--instances PATH] [--only NAME]   # new: launch via manager
disco-agent status [--instances PATH]                    # new: show instance status
disco-agent stop-all [--instances PATH]                  # new: graceful shutdown
disco-agent install-service [--instances PATH]           # new: install OS service
disco-agent uninstall-service                            # new: remove OS service
```

- `--instances` defaults to `~/.disco-agent/instances.toml`
- `stop-all` reads `manager.pid`, sends SIGTERM (Unix) / TerminateProcess (Windows)
- `status` reads `manager-state.json` and pretty-prints per-instance info (PID, status, uptime, restart count)

## Plugin Path Resolution Change

In `plugins.py`, `_load_code_plugin`:

```python
# Current:
if not plugin_path.is_absolute():
    plugin_path = Path(config_dir) / plugin_path

# New:
if not plugin_path.is_absolute():
    disco_root = os.environ.get("DISCO_AGENT_ROOT", "")
    base = Path(disco_root) if disco_root else Path(config_dir)
    plugin_path = base / plugin_path
```

Single-instance `disco-agent start` never sets `DISCO_AGENT_ROOT`, so behavior is unchanged.

The same `DISCO_AGENT_ROOT` is also added to `sys.path` for code plugin imports.

## Service Templates

Located in `service-templates/`:

### macOS: `com.disco-agent.manager.plist`
- launchd plist running `disco-agent start-all`
- Stdout/stderr -> `~/Library/Logs/disco-agent.log`

### Windows: `disco-agent-task.xml` (or PowerShell script)
- Task Scheduler entry triggered on user login
- Runs `disco-agent start-all`

### Install/Uninstall Commands
- `disco-agent install-service` detects OS, copies plist / registers task
- `disco-agent uninstall-service` reverses the installation
- Templates in `service-templates/` remain as reference
