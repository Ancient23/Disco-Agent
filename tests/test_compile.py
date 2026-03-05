from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from ue_agent.workflows.base import WorkflowResult


@dataclass
class FakeMessage:
    type: str = "result"
    subtype: str = ""
    result: str = ""
    session_id: str = "sess-1"
    cost_usd: float = 0.0


@pytest.fixture
def task():
    return {
        "id": 1,
        "workflow": "compile",
        "project": "CitySample",
        "platform": "Win64",
        "params": "{}",
        "status": "running",
        "discord_channel_id": "chan1",
        "discord_message_id": "msg1",
        "requested_by": "user1",
    }


@pytest.fixture
def mock_queue():
    q = AsyncMock()
    q.is_cancelled = AsyncMock(return_value=False)
    return q


@pytest.fixture
def mock_notifier():
    return AsyncMock()


async def test_compile_success(task, mock_queue, mock_notifier):
    from ue_agent.config import CompileConfig, UEConfig, BudgetConfig
    from ue_agent.workflows.compile import CompileWorkflow

    wf = CompileWorkflow(
        task=task,
        queue=mock_queue,
        notifier=mock_notifier,
        ue_config=UEConfig(engine_path="C:/UE5"),
        compile_config=CompileConfig(max_retries=3),
        budget_config=BudgetConfig(),
        repo_root="C:/Source/imp_UE_misc",
    )

    with patch("ue_agent.workflows.compile.run_uat") as mock_uat:
        mock_uat.return_value = (0, "Build succeeded", "")
        result = await wf.execute()

    assert result.success is True
    mock_uat.assert_called_once()


async def test_compile_fail_then_sdk_fix(task, mock_queue, mock_notifier):
    from ue_agent.config import CompileConfig, UEConfig, BudgetConfig
    from ue_agent.workflows.compile import CompileWorkflow

    wf = CompileWorkflow(
        task=task,
        queue=mock_queue,
        notifier=mock_notifier,
        ue_config=UEConfig(engine_path="C:/UE5"),
        compile_config=CompileConfig(max_retries=3),
        budget_config=BudgetConfig(),
        repo_root="C:/Source/imp_UE_misc",
    )

    call_count = 0

    async def mock_uat_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (1, "", "error: undefined reference to foo")
        return (0, "Build succeeded", "")

    async def fake_query(*args, **kwargs):
        msg = FakeMessage(type="result", result="Fixed the undefined reference", cost_usd=0.50)
        yield msg

    with (
        patch("ue_agent.workflows.compile.run_uat", side_effect=mock_uat_side_effect),
        patch("ue_agent.workflows.compile.sdk_analyze_and_fix", side_effect=fake_query),
    ):
        result = await wf.execute()

    assert result.success is True
    assert call_count == 2


async def test_compile_all_retries_exhausted(task, mock_queue, mock_notifier):
    from ue_agent.config import CompileConfig, UEConfig, BudgetConfig
    from ue_agent.workflows.compile import CompileWorkflow

    wf = CompileWorkflow(
        task=task,
        queue=mock_queue,
        notifier=mock_notifier,
        ue_config=UEConfig(engine_path="C:/UE5"),
        compile_config=CompileConfig(max_retries=2),
        budget_config=BudgetConfig(),
        repo_root="C:/Source/imp_UE_misc",
    )

    async def fake_query(*args, **kwargs):
        yield FakeMessage(type="result", result="Attempted fix", cost_usd=0.30)

    with (
        patch("ue_agent.workflows.compile.run_uat", return_value=(1, "", "error")),
        patch("ue_agent.workflows.compile.sdk_analyze_and_fix", side_effect=fake_query),
    ):
        result = await wf.execute()

    assert result.success is False
    assert "retries exhausted" in result.error.lower() or "failed" in result.error.lower()


async def test_compile_cancelled_mid_retry(task, mock_queue, mock_notifier):
    from ue_agent.config import CompileConfig, UEConfig, BudgetConfig
    from ue_agent.workflows.compile import CompileWorkflow

    mock_queue.is_cancelled = AsyncMock(side_effect=[False, True])

    wf = CompileWorkflow(
        task=task,
        queue=mock_queue,
        notifier=mock_notifier,
        ue_config=UEConfig(engine_path="C:/UE5"),
        compile_config=CompileConfig(max_retries=3),
        budget_config=BudgetConfig(),
        repo_root="C:/Source/imp_UE_misc",
    )

    async def fake_query(*args, **kwargs):
        yield FakeMessage(type="result", result="fix", cost_usd=0.10)

    with (
        patch("ue_agent.workflows.compile.run_uat", return_value=(1, "", "error")),
        patch("ue_agent.workflows.compile.sdk_analyze_and_fix", side_effect=fake_query),
    ):
        result = await wf.execute()

    assert result.success is False
    assert "cancel" in result.error.lower()
