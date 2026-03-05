import json
import os
import tempfile
from pathlib import Path

import pytest

from ue_agent.session_history import (
    build_history_context,
    format_session_for_prompt,
    load_all_sessions,
    load_recent_sessions,
    save_session,
    search_sessions,
)


@pytest.fixture()
def history_dir(tmp_path):
    """Provide a fresh temporary directory for each test."""
    d = tmp_path / "chat_history"
    d.mkdir()
    return str(d)


def _save(history_dir, task_id=1, workflow="analyze", prompt="test?", output="answer"):
    return save_session(
        task_id=task_id,
        workflow=workflow,
        prompt=prompt,
        output=output,
        cost_usd=0.05,
        requested_by="tester#1234",
        discord_channel_id="111",
        history_dir=history_dir,
    )


class TestSaveAndLoad:
    def test_save_creates_json_file(self, history_dir):
        path = _save(history_dir)
        assert path.exists()
        assert path.suffix == ".json"

    def test_saved_file_contains_expected_keys(self, history_dir):
        path = _save(history_dir)
        data = json.loads(path.read_text())
        for key in ("task_id", "workflow", "prompt", "output", "cost_usd",
                     "requested_by", "discord_channel_id", "timestamp"):
            assert key in data

    def test_load_all_returns_saved_sessions(self, history_dir):
        _save(history_dir, task_id=1, prompt="first")
        _save(history_dir, task_id=2, prompt="second")
        sessions = load_all_sessions(history_dir)
        assert len(sessions) == 2
        assert sessions[0]["prompt"] == "first"
        assert sessions[1]["prompt"] == "second"

    def test_load_recent_returns_newest_first(self, history_dir):
        _save(history_dir, task_id=1, prompt="old")
        _save(history_dir, task_id=2, prompt="new")
        recent = load_recent_sessions(n=5, history_dir=history_dir)
        assert recent[0]["prompt"] == "new"
        assert recent[1]["prompt"] == "old"

    def test_load_recent_respects_limit(self, history_dir):
        for i in range(5):
            _save(history_dir, task_id=i, prompt=f"p{i}")
        recent = load_recent_sessions(n=2, history_dir=history_dir)
        assert len(recent) == 2

    def test_load_all_empty_dir(self, history_dir):
        assert load_all_sessions(history_dir) == []


class TestSearch:
    def test_search_by_prompt(self, history_dir):
        _save(history_dir, task_id=1, prompt="crash on frame 200")
        _save(history_dir, task_id=2, prompt="build failure")
        hits = search_sessions("crash", history_dir=history_dir)
        assert len(hits) == 1
        assert hits[0]["task_id"] == 1

    def test_search_by_output(self, history_dir):
        _save(history_dir, task_id=1, prompt="question", output="the texture was corrupt")
        hits = search_sessions("texture", history_dir=history_dir)
        assert len(hits) == 1

    def test_search_case_insensitive(self, history_dir):
        _save(history_dir, task_id=1, prompt="Crash Bug")
        hits = search_sessions("crash bug", history_dir=history_dir)
        assert len(hits) == 1

    def test_search_no_results(self, history_dir):
        _save(history_dir, task_id=1, prompt="unrelated")
        assert search_sessions("nonexistent", history_dir=history_dir) == []

    def test_search_max_results(self, history_dir):
        for i in range(10):
            _save(history_dir, task_id=i, prompt=f"crash {i}")
        hits = search_sessions("crash", history_dir=history_dir, max_results=3)
        assert len(hits) == 3


class TestFormatting:
    def test_format_session_for_prompt(self, history_dir):
        path = _save(history_dir, prompt="why crash?", output="because X")
        data = json.loads(path.read_text())
        text = format_session_for_prompt(data)
        assert "why crash?" in text
        assert "because X" in text
        assert "analyze" in text

    def test_format_truncates_long_output(self, history_dir):
        long_output = "x" * 5000
        path = _save(history_dir, output=long_output)
        data = json.loads(path.read_text())
        text = format_session_for_prompt(data, max_output_len=100)
        assert "truncated" in text
        assert len(text) < 5000


class TestBuildHistoryContext:
    def test_empty_when_no_sessions(self, history_dir):
        assert build_history_context(history_dir=history_dir) == ""

    def test_includes_header_and_footer(self, history_dir):
        _save(history_dir, prompt="hello")
        ctx = build_history_context(history_dir=history_dir)
        assert "Previous session history" in ctx
        assert "End of session history" in ctx

    def test_includes_session_content(self, history_dir):
        _save(history_dir, prompt="what went wrong?", output="the shader failed")
        ctx = build_history_context(history_dir=history_dir)
        assert "what went wrong?" in ctx
        assert "the shader failed" in ctx


class TestParseHistoryCommand:
    """Test that parse_command handles !history correctly."""

    def test_history_no_args(self):
        from ue_agent.discord_bot import parse_command
        cmd = parse_command("!history")
        assert cmd is not None
        assert cmd["workflow"] == "__history"
        assert cmd["params"]["search"] == ""

    def test_history_with_search(self):
        from ue_agent.discord_bot import parse_command
        cmd = parse_command("!history crash bug")
        assert cmd is not None
        assert cmd["workflow"] == "__history"
        assert cmd["params"]["search"] == "crash bug"

    def test_history_with_quoted_search(self):
        from ue_agent.discord_bot import parse_command
        cmd = parse_command('!history "frame 200"')
        assert cmd is not None
        assert cmd["params"]["search"] == "frame 200"
