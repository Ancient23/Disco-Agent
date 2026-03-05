"""Edit-in-place streaming output for Discord threads."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_FLUSH_INTERVAL = 1.5
_DEFAULT_MAX_LENGTH = 1800


class StreamingDiscordMessage:
    """Manages edit-in-place Discord messages for live streaming output.

    Buffers incoming text and periodically flushes it to a Discord thread,
    editing the current message in place.  When the buffer exceeds *max_length*
    the current message is finalised and a new one is started.
    """

    def __init__(
        self,
        thread: Any,
        *,
        max_length: int = _DEFAULT_MAX_LENGTH,
        flush_interval: float = _DEFAULT_FLUSH_INTERVAL,
    ):
        self._thread = thread
        self._max_length = max_length
        self._flush_interval = flush_interval
        self._buffer = ""
        self._current_msg: Any | None = None
        self._last_flush: float = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def append(self, text: str) -> None:
        """Add *text* to the buffer, rolling over or flushing as needed."""
        self._buffer += text
        if len(self._buffer) > self._max_length:
            await self._rollover()
        elif self._should_flush():
            await self.flush()

    async def append_tool_use(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        """Append a formatted tool-use indicator line."""
        summary = _summarize_tool_input(tool_name, tool_input)
        await self.append(f"\n`> {tool_name}` {summary}\n")

    async def flush(self) -> None:
        """Send or edit the Discord message with the current buffer."""
        if not self._buffer:
            return
        content = self._buffer[: self._max_length]
        if self._current_msg is None:
            self._current_msg = await self._thread.send(content=content)
        else:
            await self._current_msg.edit(content=content)
        self._last_flush = time.monotonic()

    async def finalize(self) -> None:
        """Flush any remaining buffered text."""
        if self._buffer:
            await self.flush()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _rollover(self) -> None:
        """Finalise the current message and start a new one with overflow."""
        overflow = self._buffer[self._max_length :]
        self._buffer = self._buffer[: self._max_length]
        await self.flush()
        self._current_msg = None
        self._buffer = overflow
        if self._buffer:
            await self.flush()

    def _should_flush(self) -> bool:
        if self._flush_interval <= 0:
            return True
        return (time.monotonic() - self._last_flush) >= self._flush_interval


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------


def _summarize_tool_input(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Return a short human-readable summary of *tool_input*."""
    if tool_name in ("Read", "Glob"):
        return tool_input.get("file_path", tool_input.get("pattern", ""))
    if tool_name in ("Edit", "Write"):
        return tool_input.get("file_path", "")
    if tool_name == "Grep":
        return f'"{tool_input.get("pattern", "")}"'
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return cmd[:80] + ("..." if len(cmd) > 80 else "")
    return ""
