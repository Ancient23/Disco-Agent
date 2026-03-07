"""Test the thread reply detection and task enqueue flow."""

import pytest

from disco_agent.discord_bot import parse_command


class TestThreadReplyDetection:
    def test_plain_text_not_parsed_as_command(self):
        """Plain text in a thread should not parse as a command."""
        assert parse_command("what about the texture loading?") is None
        assert parse_command("can you fix that?") is None
        assert parse_command("") is None

    def test_bang_command_still_works_in_thread(self):
        """! commands should still be recognized even in a thread context."""
        result = parse_command('!run "fix it"')
        assert result is not None
        assert result["workflow"] == "custom"

    def test_analyze_command_still_works(self):
        result = parse_command('!analyze "why crash?"')
        assert result is not None
        assert result["workflow"] == "analyze"
