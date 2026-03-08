import json

import pytest


@pytest.fixture
async def queue(tmp_path):
    from disco_agent.queue import TaskQueue

    db_path = str(tmp_path / "test.db")
    q = TaskQueue(db_path)
    await q.initialize()
    yield q
    await q.close()


async def test_enqueue_and_fetch(queue):
    task_id = await queue.enqueue(
        workflow="compile",
        project="CitySample",
        platform="Win64",
        params={"flags": ["-cook"]},
        discord_channel_id="chan1",
        discord_message_id="msg1",
        requested_by="user1",
    )
    assert task_id == 1

    task = await queue.fetch_next()
    assert task is not None
    assert task["id"] == 1
    assert task["workflow"] == "compile"
    assert task["project"] == "CitySample"
    assert task["status"] == "running"
    assert task["started_at"] is not None
    assert json.loads(task["params"]) == {"flags": ["-cook"]}


async def test_fetch_returns_none_when_empty(queue):
    task = await queue.fetch_next()
    assert task is None


async def test_fifo_order(queue):
    await queue.enqueue(
        workflow="compile", project="A", platform="Win64", params={},
        discord_channel_id="c", discord_message_id="m1", requested_by="u",
    )
    await queue.enqueue(
        workflow="submit", project="B", platform="Win64", params={},
        discord_channel_id="c", discord_message_id="m2", requested_by="u",
    )
    task = await queue.fetch_next()
    assert task["project"] == "A"


async def test_complete_task(queue):
    task_id = await queue.enqueue(
        workflow="compile", project="X", platform="Win64", params={},
        discord_channel_id="c", discord_message_id="m", requested_by="u",
    )
    await queue.fetch_next()
    await queue.complete(task_id, result={"exit_code": 0, "cost_usd": 0.12})

    task = await queue.get(task_id)
    assert task["status"] == "completed"
    assert task["finished_at"] is not None
    result = json.loads(task["result"])
    assert result["exit_code"] == 0


async def test_fail_task(queue):
    task_id = await queue.enqueue(
        workflow="compile", project="X", platform="Win64", params={},
        discord_channel_id="c", discord_message_id="m", requested_by="u",
    )
    await queue.fetch_next()
    await queue.fail(task_id, result={"error": "build failed"})

    task = await queue.get(task_id)
    assert task["status"] == "failed"


async def test_cancel_task(queue):
    task_id = await queue.enqueue(
        workflow="compile", project="X", platform="Win64", params={},
        discord_channel_id="c", discord_message_id="m", requested_by="u",
    )
    await queue.cancel(task_id)

    task = await queue.get(task_id)
    assert task["status"] == "cancelled"


async def test_is_cancelled(queue):
    task_id = await queue.enqueue(
        workflow="compile", project="X", platform="Win64", params={},
        discord_channel_id="c", discord_message_id="m", requested_by="u",
    )
    assert await queue.is_cancelled(task_id) is False
    await queue.cancel(task_id)
    assert await queue.is_cancelled(task_id) is True


async def test_list_pending(queue):
    await queue.enqueue(
        workflow="compile", project="A", platform="Win64", params={},
        discord_channel_id="c", discord_message_id="m", requested_by="u",
    )
    await queue.enqueue(
        workflow="submit", project="B", platform="Win64", params={},
        discord_channel_id="c", discord_message_id="m", requested_by="u",
    )
    tasks = await queue.list_active()
    assert len(tasks) == 2
