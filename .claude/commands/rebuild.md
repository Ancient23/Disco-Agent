---
description: Clean cache and reinstall ue-agent globally
---

# Rebuild Global Install

Clean the uv cache and reinstall the `ue-agent` tool globally so it picks up the latest source changes.

## Steps

1. Run `uv cache clean ue-agent` from the `adw-agent/` directory to clear stale wheel cache
2. Run `uv tool install . --reinstall` from the `adw-agent/` directory to rebuild and reinstall
3. Verify the install by running `ue-agent --help` or checking the version

```bash
cd adw-agent && uv cache clean ue-agent && uv tool install . --reinstall
```

Report the output to confirm success.
