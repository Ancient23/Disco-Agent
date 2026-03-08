import pytest

from disco_agent.discord_bot import parse_command


def test_parse_analyze_command():
    cmd = parse_command('!analyze "why does the 4D capture crash"')
    assert cmd is not None
    assert cmd["workflow"] == "analyze"
    assert "4D capture crash" in cmd["params"]["prompt"]


def test_parse_run_command():
    cmd = parse_command('!run "add error handling to s3_upload.py"')
    assert cmd is not None
    assert cmd["workflow"] == "custom"
    assert "error handling" in cmd["params"]["prompt"]


def test_parse_status_command():
    cmd = parse_command("!status")
    assert cmd is not None
    assert cmd["workflow"] == "__status"


def test_parse_cancel_command():
    cmd = parse_command("!cancel")
    assert cmd is not None
    assert cmd["workflow"] == "__cancel"


def test_parse_help_command():
    cmd = parse_command("!help")
    assert cmd is not None
    assert cmd["workflow"] == "__help"


def test_parse_unknown_command():
    cmd = parse_command("!unknown something")
    assert cmd is None


def test_parse_non_command():
    cmd = parse_command("hello everyone")
    assert cmd is None


def test_parse_dynamic_plugin_command():
    """A command matching a registered workflow should parse dynamically."""
    from disco_agent.workflows import WORKFLOW_REGISTRY
    from disco_agent.workflows.base import BaseWorkflow, WorkflowResult

    class FakeWorkflow(BaseWorkflow):
        async def execute(self):
            return WorkflowResult(success=True)

    WORKFLOW_REGISTRY["deploy"] = FakeWorkflow
    try:
        cmd = parse_command("!deploy my-app --region us-east-1")
        assert cmd is not None
        assert cmd["workflow"] == "deploy"
        assert cmd["project"] == "my-app"
        assert "--region us-east-1" in cmd["params"]["raw_args"]
    finally:
        del WORKFLOW_REGISTRY["deploy"]


def test_parse_unregistered_command_returns_none():
    cmd = parse_command("!nonexistent something")
    assert cmd is None


async def test_notifier_create_thread():
    from disco_agent.discord_bot import DiscordNotifier
    from unittest.mock import AsyncMock, MagicMock

    bot = MagicMock()
    mock_channel = AsyncMock()
    mock_message = AsyncMock()
    mock_thread = AsyncMock()
    mock_message.create_thread = AsyncMock(return_value=mock_thread)
    mock_thread.id = 999
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    bot.get_channel = MagicMock(return_value=mock_channel)

    notifier = DiscordNotifier(bot)
    thread_id = await notifier.create_thread("123", "456", "Task #1 — analyze")
    assert thread_id == "999"
    mock_message.create_thread.assert_called_once_with(name="Task #1 — analyze")


async def test_notifier_send_to_thread():
    from disco_agent.discord_bot import DiscordNotifier
    from unittest.mock import AsyncMock, MagicMock

    bot = MagicMock()
    mock_thread = AsyncMock()
    mock_sent = AsyncMock()
    mock_sent.id = 789
    mock_thread.send = AsyncMock(return_value=mock_sent)
    bot.get_channel = MagicMock(return_value=mock_thread)

    notifier = DiscordNotifier(bot)
    msg_id = await notifier.send_to_thread("999", "hello")
    assert msg_id == "789"


async def test_notifier_edit_message():
    from disco_agent.discord_bot import DiscordNotifier
    from unittest.mock import AsyncMock, MagicMock

    bot = MagicMock()
    mock_thread = AsyncMock()
    mock_msg = AsyncMock()
    mock_thread.fetch_message = AsyncMock(return_value=mock_msg)
    bot.get_channel = MagicMock(return_value=mock_thread)

    notifier = DiscordNotifier(bot)
    await notifier.edit_message("999", "789", "updated content")
    mock_msg.edit.assert_called_once()
