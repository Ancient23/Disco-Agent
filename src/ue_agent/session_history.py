"""Persist and retrieve chat session history across bot restarts.

Sessions are stored as individual JSON files inside a ``chat_history/``
directory (one file per task).  Each file captures the workflow type,
the user prompt, the bot's output, cost, timestamp, and the requesting
Discord user so that future sessions can look up what was discussed
previously.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default location is <repo_root>/adw-agent/chat_history/
_DEFAULT_DIR_NAME = "chat_history"


def get_history_dir(repo_root: str) -> str:
    """Canonical path for the session history directory."""
    return str(Path(repo_root) / "adw-agent" / "chat_history")


def _history_dir(base_dir: str | Path | None = None) -> Path:
    """Return (and lazily create) the history directory."""
    if base_dir is not None:
        p = Path(base_dir)
    else:
        p = Path(_DEFAULT_DIR_NAME)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_session(
    *,
    task_id: int,
    workflow: str,
    prompt: str,
    output: str,
    cost_usd: float,
    requested_by: str,
    discord_channel_id: str,
    history_dir: str | Path | None = None,
) -> Path:
    """Write a completed session to disk and return the file path.

    This is best-effort — a write failure is logged but will not raise.
    """
    hdir = _history_dir(history_dir)
    now = datetime.now(timezone.utc)
    record: dict[str, Any] = {
        "task_id": task_id,
        "workflow": workflow,
        "prompt": prompt,
        "output": output,
        "cost_usd": cost_usd,
        "requested_by": requested_by,
        "discord_channel_id": discord_channel_id,
        "timestamp": now.isoformat(),
    }

    # Filename: <timestamp>_task<id>.json  (sortable by time)
    ts_slug = now.strftime("%Y%m%d_%H%M%S")
    filename = f"{ts_slug}_task{task_id}.json"
    filepath = hdir / filename

    try:
        filepath.write_text(json.dumps(record, indent=2), encoding="utf-8")
        logger.info("Saved session history → %s", filepath)
    except OSError:
        logger.warning("Failed to write session history to %s", filepath, exc_info=True)
    return filepath


def load_all_sessions(
    history_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Load every saved session, sorted oldest-first."""
    hdir = _history_dir(history_dir)
    sessions: list[dict[str, Any]] = []
    for fp in sorted(hdir.glob("*.json")):
        try:
            sessions.append(json.loads(fp.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping corrupt history file %s: %s", fp, exc)
    return sessions


def load_recent_sessions(
    n: int = 10,
    history_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return the *n* most recent sessions (newest-first)."""
    all_sessions = load_all_sessions(history_dir)
    return list(reversed(all_sessions[-n:]))


def search_sessions(
    query: str,
    *,
    history_dir: str | Path | None = None,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Substring search across prompts and outputs (case-insensitive)."""
    query_lower = query.lower()
    hits: list[dict[str, Any]] = []
    for session in reversed(load_all_sessions(history_dir)):
        text = f"{session.get('prompt', '')} {session.get('output', '')}"
        if query_lower in text.lower():
            hits.append(session)
            if len(hits) >= max_results:
                break
    return hits


def format_session_for_prompt(session: dict[str, Any], *, max_output_len: int = 1500) -> str:
    """Format a single session record into a human-readable summary."""
    output = session.get("output", "")
    if len(output) > max_output_len:
        output = output[:max_output_len] + "... (truncated)"

    return (
        f"[{session.get('timestamp', 'unknown time')}] "
        f"Task #{session.get('task_id', '?')} — {session.get('workflow', '?')} "
        f"(by {session.get('requested_by', 'unknown')})\n"
        f"  Prompt: {session.get('prompt', '')}\n"
        f"  Output: {output}\n"
    )


def inject_history_context(
    prompt: str,
    *,
    instruction: str,
    history_dir: str | Path | None = None,
) -> str:
    """Prepend recent session history to a prompt if any exists."""
    history_context = build_history_context(history_dir=history_dir)
    if not history_context:
        return prompt
    return (
        f"{history_context}\n"
        f"The user may reference previous sessions above. {instruction}\n\n"
        f"{prompt}"
    )


def build_history_context(
    history_dir: str | Path | None = None,
    max_sessions: int = 10,
) -> str:
    """Build a context block summarising recent sessions for injection into a
    new Claude prompt."""
    sessions = load_recent_sessions(n=max_sessions, history_dir=history_dir)
    if not sessions:
        return ""

    parts = ["=== Previous session history ==="]
    for s in sessions:
        parts.append(format_session_for_prompt(s))
    parts.append("=== End of session history ===\n")
    return "\n".join(parts)
