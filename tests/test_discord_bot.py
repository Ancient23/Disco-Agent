import pytest

from disco_agent.discord_bot import parse_command


def test_parse_build_command():
    cmd = parse_command("!build CitySample")
    assert cmd is not None
    assert cmd["workflow"] == "compile"
    assert cmd["project"] == "CitySample"
    assert cmd["platform"] == "Win64"


def test_parse_package_command():
    cmd = parse_command("!package CitySample Linux")
    assert cmd is not None
    assert cmd["workflow"] == "package"
    assert cmd["project"] == "CitySample"
    assert cmd["platform"] == "Linux"


def test_parse_package_default_platform():
    cmd = parse_command("!package CitySample")
    assert cmd["platform"] == "Win64"


def test_parse_submit_command():
    cmd = parse_command("!submit CitySample --dry-run --app citysample")
    assert cmd is not None
    assert cmd["workflow"] == "submit"
    assert cmd["project"] == "CitySample"
    assert cmd["params"]["options"] == "--dry-run --app citysample"


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


def test_parse_build_missing_project():
    cmd = parse_command("!build")
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
