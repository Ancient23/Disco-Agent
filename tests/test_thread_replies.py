"""Test the thread reply detection and task enqueue flow."""

import json
import pytest
from unittest.mock import AsyncMock

from disco_agent.discord_bot import parse_command
from disco_agent.workflows.base import BaseWorkflow, WorkflowResult


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


class TestThreadReplyWorkflowReuse:
    """Test that thread reply tasks reuse the existing thread."""

    async def test_thread_reply_reuses_existing_thread(self):
        """When params contain thread_id, the workflow should reuse the thread
        instead of creating a new one."""

        class FakeWorkflow(BaseWorkflow):
            async def execute(self) -> WorkflowResult:
                # thread_id should be set to the existing thread, not a new one
                assert self.thread_id == "99999"
                return WorkflowResult(success=True, output="replied")

        task = {
            "id": 2,
            "workflow": "custom",
            "project": "",
            "discord_channel_id": "99999",
            "discord_message_id": "msg_reply",
            "requested_by": "user1",
            "params": json.dumps({
                "prompt": "fix the other thing",
                "thread_context": "[assistant] previous output",
                "thread_id": "99999",
            }),
        }
        queue = AsyncMock()
        notifier = AsyncMock()
        notifier.send_to_thread = AsyncMock(return_value="msg_id")

        wf = FakeWorkflow(task=task, queue=queue, notifier=notifier)
        wf.use_threads = True  # daemon sets this; run() should override to False
        result = await wf.run()

        assert result.success
        # Should NOT create a new thread — it reuses the existing one
        notifier.create_thread.assert_not_called()
        # Should send completion to the existing thread
        notifier.send_to_thread.assert_called()
