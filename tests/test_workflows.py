import pytest

from ue_agent.workflows import WORKFLOW_REGISTRY, register
from ue_agent.workflows.base import BaseWorkflow, WorkflowResult


async def test_register_decorator():
    @register("test_wf")
    class TestWorkflow(BaseWorkflow):
        async def execute(self) -> WorkflowResult:
            return WorkflowResult(success=True, output="done")

    assert "test_wf" in WORKFLOW_REGISTRY
    assert WORKFLOW_REGISTRY["test_wf"] is TestWorkflow

    del WORKFLOW_REGISTRY["test_wf"]


async def test_base_workflow_is_cancelled(tmp_path):
    from ue_agent.queue import TaskQueue

    q = TaskQueue(str(tmp_path / "test.db"))
    await q.initialize()
    task_id = await q.enqueue(
        workflow="compile", project="X", platform="Win64", params={},
        discord_channel_id="c", discord_message_id="m", requested_by="u",
    )
    task = await q.fetch_next()

    class DummyNotifier:
        async def send_status(self, channel_id, message): pass
        async def send_result(self, channel_id, message_id, result): pass

    wf = _make_concrete_workflow(task=task, queue=q, notifier=DummyNotifier())
    assert await wf.is_cancelled() is False
    await q.cancel(task_id)
    assert await wf.is_cancelled() is True

    await q.close()


def _make_concrete_workflow(**kwargs):
    class ConcreteWorkflow(BaseWorkflow):
        async def execute(self) -> WorkflowResult:
            return WorkflowResult(success=True, output="ok")

    return ConcreteWorkflow(**kwargs)


async def test_workflow_creates_thread_when_enabled():
    from unittest.mock import AsyncMock
    from ue_agent.workflows.base import BaseWorkflow, WorkflowResult

    class FakeWorkflow(BaseWorkflow):
        async def execute(self) -> WorkflowResult:
            assert self.thread_id != ""
            return WorkflowResult(success=True, output="done")

    task = {
        "id": 1, "workflow": "analyze", "project": "",
        "discord_channel_id": "chan1", "discord_message_id": "msg1",
        "requested_by": "user1",
    }
    queue = AsyncMock()
    notifier = AsyncMock()
    notifier.create_thread = AsyncMock(return_value="thread123")
    notifier.send_to_thread = AsyncMock(return_value="msg999")

    wf = FakeWorkflow(task=task, queue=queue, notifier=notifier)
    wf.use_threads = True
    result = await wf.run()
    assert result.success
    notifier.create_thread.assert_called_once()


async def test_workflow_skips_thread_when_disabled():
    from unittest.mock import AsyncMock
    from ue_agent.workflows.base import BaseWorkflow, WorkflowResult

    class FakeWorkflow(BaseWorkflow):
        async def execute(self) -> WorkflowResult:
            assert self.thread_id == ""
            return WorkflowResult(success=True, output="done")

    task = {
        "id": 1, "workflow": "compile", "project": "X",
        "discord_channel_id": "chan1", "discord_message_id": "msg1",
        "requested_by": "user1",
    }
    queue = AsyncMock()
    notifier = AsyncMock()

    wf = FakeWorkflow(task=task, queue=queue, notifier=notifier)
    wf.use_threads = False
    result = await wf.run()
    assert result.success
    notifier.create_thread.assert_not_called()


async def test_workflow_dispatch_roundtrip(tmp_path):
    """Full roundtrip: enqueue -> fetch -> build workflow -> run."""
    from unittest.mock import AsyncMock, patch
    from ue_agent.queue import TaskQueue
    from ue_agent.workflows.base import WorkflowResult

    q = TaskQueue(str(tmp_path / "test.db"))
    await q.initialize()

    task_id = await q.enqueue(
        workflow="compile", project="TestProj", platform="Win64", params={},
        discord_channel_id="c", discord_message_id="m", requested_by="u",
    )
    task = await q.fetch_next()

    notifier = AsyncMock()

    import ue_agent.workflows.compile  # noqa: F401
    from ue_agent.config import UEConfig, CompileConfig, BudgetConfig

    with patch("ue_agent.workflows.compile.run_uat", return_value=(0, "ok", "")):
        from ue_agent.workflows.compile import CompileWorkflow
        wf = CompileWorkflow(
            task=task, queue=q, notifier=notifier,
            ue_config=UEConfig(engine_path="C:/UE5"),
            compile_config=CompileConfig(),
            budget_config=BudgetConfig(),
            repo_root="/tmp",
        )
        result = await wf.run()

    assert result.success is True
    final = await q.get(task_id)
    assert final["status"] == "completed"

    await q.close()
