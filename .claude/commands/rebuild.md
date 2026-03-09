---
description: Clean cache and reinstall disco-agent globally
---

# Rebuild Global Install

Clean the uv cache and reinstall the `disco-agent` tool globally so it picks up the latest source changes.

## Steps

1. Run `uv cache clean disco-agent` to clear stale wheel cache
2. Run `uv tool install . --reinstall` to rebuild and reinstall
3. Verify the install by running `disco-agent --help`

```bash
uv cache clean disco-agent && uv tool install . --reinstall
```

Report the output to confirm success.
