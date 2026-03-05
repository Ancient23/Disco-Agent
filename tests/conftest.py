import pytest


@pytest.fixture
async def tmp_queue(tmp_path):
    """Provide an initialized TaskQueue backed by a temp SQLite file."""
    from ue_agent.queue import TaskQueue

    db_path = str(tmp_path / "test_tasks.db")
    q = TaskQueue(db_path)
    await q.initialize()
    yield q
    await q.close()
