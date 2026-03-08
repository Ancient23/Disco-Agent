from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from disco_agent.workflows.base import WorkflowResult
from disco_agent.workflows.session import AgentSessionWorkflow


def _make_task(prompt: str = "do something") -> dict:
    return {
        "id": 42,
        "workflow": "test-session",
        "project": "TestProject",
        "discord_channel_id": "chan1",
        "discord_message_id": "msg1",
        "requested_by": "tester",
        "params": {"prompt": prompt},
    }


def _make_workflow(
    task: dict | None = None,
    session_cwd: str = "/tmp/project",
    allowed_tools: list[str] | None = None,
    budget_warning_usd: float = 5.0,
    repo_root: str = "/tmp/repo",
) -> AgentSessionWorkflow:
    if task is None:
        task = _make_task()
    if allowed_tools is None:
        allowed_tools = ["Read", "Bash"]

    queue = AsyncMock()
    notifier = AsyncMock()
    notifier.get_thread = MagicMock(return_value=None)

    wf = AgentSessionWorkflow(
        task=task,
        queue=queue,
        notifier=notifier,
        session_cwd=session_cwd,
        allowed_tools=allowed_tools,
        budget_warning_usd=budget_warning_usd,
        repo_root=repo_root,
    )
    # Skip thread creation for unit tests
    wf.use_threads = False
    return wf


async def test_session_workflow_runs_sdk_query(tmp_path):
    """Mock the query function to yield a ResultMessage with output.
    Verify the workflow returns success with the expected output and cost."""

    mock_result = MagicMock()
    mock_result.__class__ = type("ResultMessage", (), {})
    # Build a real-looking ResultMessage mock
    result_msg = MagicMock()
    result_msg.total_cost_usd = 0.42
    result_msg.result = "analysis complete"

    # Make isinstance checks work
    from claude_agent_sdk.types import ResultMessage

    result_msg.__class__ = ResultMessage

    async def fake_query(prompt, options):
        yield result_msg

    wf = _make_workflow(repo_root=str(tmp_path))

    with patch("disco_agent.workflows.session.query", side_effect=fake_query):
        with patch("disco_agent.workflows.session.save_session"):
            result = await wf.execute()

    assert result.success is True
    assert result.output == "analysis complete"
    assert result.cost_usd == pytest.approx(0.42)


async def test_session_workflow_uses_configured_tools(tmp_path):
    """Mock query to capture the ClaudeAgentOptions passed.
    Verify allowed_tools matches what was configured."""
    from claude_agent_sdk.types import ResultMessage

    captured_options = {}

    result_msg = MagicMock()
    result_msg.__class__ = ResultMessage
    result_msg.total_cost_usd = 0.0
    result_msg.result = "ok"

    async def fake_query(prompt, options):
        captured_options["options"] = options
        yield result_msg

    tools = ["Read", "Glob", "Grep", "Bash", "Edit"]
    wf = _make_workflow(allowed_tools=tools, repo_root=str(tmp_path))

    with patch("disco_agent.workflows.session.query", side_effect=fake_query):
        with patch("disco_agent.workflows.session.save_session"):
            await wf.execute()

    assert captured_options["options"].allowed_tools == tools


async def test_session_workflow_uses_configured_cwd(tmp_path):
    """Verify the cwd in the SDK options matches session_cwd."""
    from claude_agent_sdk.types import ResultMessage

    captured_options = {}

    result_msg = MagicMock()
    result_msg.__class__ = ResultMessage
    result_msg.total_cost_usd = 0.0
    result_msg.result = "ok"

    async def fake_query(prompt, options):
        captured_options["options"] = options
        yield result_msg

    wf = _make_workflow(session_cwd="/my/custom/dir", repo_root=str(tmp_path))

    with patch("disco_agent.workflows.session.query", side_effect=fake_query):
        with patch("disco_agent.workflows.session.save_session"):
            await wf.execute()

    assert captured_options["options"].cwd == "/my/custom/dir"


async def test_session_workflow_no_prompt_returns_error():
    """Task with empty prompt should return WorkflowResult(success=False)."""
    task = _make_task(prompt="")
    wf = _make_workflow(task=task)

    result = await wf.execute()

    assert result.success is False
    assert "No prompt" in result.error
