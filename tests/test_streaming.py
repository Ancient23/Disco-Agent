import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from disco_agent.streaming import StreamingDiscordMessage


@pytest.fixture
def mock_thread():
    thread = AsyncMock()
    sent_msg = AsyncMock()
    sent_msg.edit = AsyncMock()
    thread.send = AsyncMock(return_value=sent_msg)
    return thread


class TestStreamingDiscordMessage:
    async def test_append_sends_initial_message(self, mock_thread):
        stream = StreamingDiscordMessage(mock_thread, flush_interval=0)
        await stream.append("hello")
        await stream.flush()
        mock_thread.send.assert_called_once()

    async def test_append_edits_existing_message(self, mock_thread):
        stream = StreamingDiscordMessage(mock_thread, flush_interval=0)
        await stream.append("hello")
        await stream.flush()
        await stream.append(" world")
        await stream.flush()
        assert mock_thread.send.call_count == 1
        sent_msg = mock_thread.send.return_value
        sent_msg.edit.assert_called()

    async def test_rollover_on_max_length(self, mock_thread):
        stream = StreamingDiscordMessage(mock_thread, max_length=50, flush_interval=0)
        await stream.append("x" * 60)
        await stream.flush()
        assert mock_thread.send.call_count == 2

    async def test_append_tool_use(self, mock_thread):
        stream = StreamingDiscordMessage(mock_thread, flush_interval=0)
        await stream.append_tool_use("Read", {"file_path": "/src/foo.py"})
        await stream.flush()
        mock_thread.send.assert_called_once()
        call_args = mock_thread.send.call_args
        assert "Read" in call_args[1]["content"]

    async def test_finalize_sends_remaining(self, mock_thread):
        stream = StreamingDiscordMessage(mock_thread, flush_interval=0)
        await stream.append("buffered text")
        await stream.finalize()
        mock_thread.send.assert_called()
