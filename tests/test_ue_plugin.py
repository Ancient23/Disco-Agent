import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from disco_agent.workflows.base import WorkflowResult


@dataclass
class FakeMessage:
    type: str = "result"
    subtype: str = ""
    result: str = ""
    session_id: str = "sess-1"
    total_cost_usd: float = 0.0


@pytest.fixture(autouse=True)
def load_ue_plugin():
    """Load the UE plugin module and configure it for tests."""
    from disco_agent.workflows import WORKFLOW_REGISTRY

    # Load the plugin
    spec = importlib.util.spec_from_file_location(
        "disco_agent_plugin_ue",
        str(Path("plugins/ue/workflows.py")),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["disco_agent_plugin_ue"] = module

    # Save and restore registry state
    before = dict(WORKFLOW_REGISTRY)
    spec.loader.exec_module(module)

    # Configure with test values
    from plugins.ue.config import UEPluginConfig
    module.set_plugin_config(UEPluginConfig(engine_path=Path("C:/UE5")))

    yield module

    # Cleanup
    WORKFLOW_REGISTRY.clear()
    WORKFLOW_REGISTRY.update(before)
    sys.modules.pop("disco_agent_plugin_ue", None)


@pytest.fixture
def task():
    return {
        "id": 1, "workflow": "compile", "project": "CitySample",
        "platform": "Win64", "params": "{}", "status": "running",
        "discord_channel_id": "chan1", "discord_message_id": "msg1",
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


async def test_compile_success(task, mock_queue, mock_notifier, load_ue_plugin):
    from disco_agent.workflows import WORKFLOW_REGISTRY
    CompileWorkflow = WORKFLOW_REGISTRY["compile"]

    wf = CompileWorkflow(task=task, queue=mock_queue, notifier=mock_notifier, repo_root="C:/Source/test")

    with patch.object(load_ue_plugin, "run_uat", return_value=(0, "Build succeeded", "")):
        result = await wf.execute()

    assert result.success is True


async def test_compile_fail_then_sdk_fix(task, mock_queue, mock_notifier, load_ue_plugin):
    from disco_agent.workflows import WORKFLOW_REGISTRY
    CompileWorkflow = WORKFLOW_REGISTRY["compile"]

    wf = CompileWorkflow(task=task, queue=mock_queue, notifier=mock_notifier, repo_root="C:/Source/test")

    call_count = 0
    async def mock_uat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (1, "", "error: undefined reference")
        return (0, "Build succeeded", "")

    async def fake_sdk(*args, **kwargs):
        yield FakeMessage(type="result", result="Fixed", total_cost_usd=0.50)

    with (
        patch.object(load_ue_plugin, "run_uat", side_effect=mock_uat),
        patch.object(load_ue_plugin, "sdk_analyze_and_fix", side_effect=fake_sdk),
    ):
        result = await wf.execute()

    assert result.success is True
    assert call_count == 2


async def test_compile_all_retries_exhausted(task, mock_queue, mock_notifier, load_ue_plugin):
    from plugins.ue.config import UEPluginConfig
    load_ue_plugin.set_plugin_config(UEPluginConfig(engine_path=Path("C:/UE5"), max_retries=2))

    from disco_agent.workflows import WORKFLOW_REGISTRY
    CompileWorkflow = WORKFLOW_REGISTRY["compile"]
    wf = CompileWorkflow(task=task, queue=mock_queue, notifier=mock_notifier, repo_root="C:/Source/test")

    async def fake_sdk(*args, **kwargs):
        yield FakeMessage(type="result", result="Attempted fix", total_cost_usd=0.30)

    with (
        patch.object(load_ue_plugin, "run_uat", return_value=(1, "", "error")),
        patch.object(load_ue_plugin, "sdk_analyze_and_fix", side_effect=fake_sdk),
    ):
        result = await wf.execute()

    assert result.success is False


async def test_compile_cancelled(task, mock_queue, mock_notifier, load_ue_plugin):
    mock_queue.is_cancelled = AsyncMock(side_effect=[False, True])

    from disco_agent.workflows import WORKFLOW_REGISTRY
    CompileWorkflow = WORKFLOW_REGISTRY["compile"]
    wf = CompileWorkflow(task=task, queue=mock_queue, notifier=mock_notifier, repo_root="C:/Source/test")

    async def fake_sdk(*args, **kwargs):
        yield FakeMessage(type="result", result="fix", total_cost_usd=0.10)

    with (
        patch.object(load_ue_plugin, "run_uat", return_value=(1, "", "error")),
        patch.object(load_ue_plugin, "sdk_analyze_and_fix", side_effect=fake_sdk),
    ):
        result = await wf.execute()

    assert result.success is False
    assert "cancel" in result.error.lower()
