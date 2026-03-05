from __future__ import annotations


def tail_lines(text: str, n: int) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n:])


def truncate_for_discord(text: str, max_len: int = 1900) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n... (truncated)"
