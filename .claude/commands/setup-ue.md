---
description: Interactive setup for the UE build automation plugin
---

# Setup UE Plugin

Walk the user through configuring the Unreal Engine plugin for Disco-Agent.

## Prerequisites

- Disco-Agent repository cloned
- `config.toml` exists (copy from `config.toml.example` if needed)
- Unreal Engine installed locally

## Steps

### 1. Detect Engine Install

Search common UE installation paths:
```bash
ls -d "C:/Program Files/Epic Games/UE_5."*/Engine 2>/dev/null
ls -d "D:/Program Files/Epic Games/UE_5."*/Engine 2>/dev/null
ls -d "E:/Epic Games/UE_5."*/Engine 2>/dev/null
```

Present findings and ask the user to confirm or provide their engine path. Default to the latest version found.

### 2. Find .uproject File

Scan from the configured `repo_root` (or CWD) for `.uproject` files:
```bash
find . -maxdepth 4 -name "*.uproject" 2>/dev/null
```

If multiple found, ask the user to select one. If none found, ask for the path manually.

### 3. UE Source Path (optional)

Ask if the user has cloned the Unreal Engine source from GitHub for API research:
- If yes, ask for the path (e.g., `C:/Source/UnrealEngine`)
- Verify the path contains `Engine/Source/Runtime/`
- If no, explain this is optional and only needed for the `/ue-research` command

### 4. Write Config

Read the existing `config.toml`. Append (or update if already present) the plugin configuration:

```toml
[[plugins]]
name = "ue"
type = "code"
path = "plugins/ue"

[plugin-config.ue]
engine_path = "<detected path>"
project_path = "<selected .uproject relative path>"
platform = "Win64"
build_flags = ["-cook", "-stage", "-pak", "-unattended", "-nullrhi"]
max_retries = 3
error_tail_lines = 200
ue_source_path = "<optional path or empty>"
compile_warning_usd = 5.0
package_warning_usd = 5.0
```

### 5. Verify

After writing the config, verify it loads without errors by checking the TOML parses correctly.

Report the final configuration to the user and explain:
- `!build <project>` and `!package <project>` commands are now available
- If `ue_source_path` was set, `/ue-research` is available for API validation
