import asyncio

import pytest

from app.services.pool import run_windowed


@pytest.mark.asyncio
async def test_windowed_bounds_concurrency_and_completes_all():
    lock = asyncio.Lock()
    active = 0
    max_active = 0
    done: list[int] = []

    async def worker(i: int) -> None:
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            await asyncio.sleep(0.02)
        finally:
            async with lock:
                active -= 1
        done.append(i)

    await run_windowed(range(12), 3, worker)
    assert sorted(done) == list(range(12))
    assert max_active == 3


@pytest.mark.asyncio
async def test_windowed_schedules_next_as_soon_as_slot_free():
    """并发 2：任一 worker 完成后，排队项应立刻被调度（滑动窗口）。"""
    started = asyncio.Queue()
    release: dict[int, asyncio.Event] = {}

    async def worker(i: int) -> None:
        ev = asyncio.Event()
        release[i] = ev
        await started.put(i)
        await ev.wait()

    task = asyncio.create_task(run_windowed(range(5), 2, worker))
    first = {await started.get(), await started.get()}
    assert first == {0, 1}  # 窗口先占满前两项

    # 释放 0 → 2 应立即开始（不等 1 完成）
    release[0].set()
    assert await asyncio.wait_for(started.get(), timeout=1) == 2
    # 再释放 1 → 3 开始
    release[1].set()
    assert await asyncio.wait_for(started.get(), timeout=1) == 3
    # 释放剩余项让任务收尾
    release[2].set()
    release[3].set()
    assert await asyncio.wait_for(started.get(), timeout=1) == 4
    release[4].set()
    await task
    assert task.done() and not task.cancelled()


@pytest.mark.asyncio
async def test_unlimited_concurrency_runs_all():
    lock = asyncio.Lock()
    active = 0
    max_active = 0

    async def worker(i: int) -> None:
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            await asyncio.sleep(0.02)
        finally:
            async with lock:
                active -= 1

    await run_windowed(range(8), -1, worker)
    assert max_active == 8


@pytest.mark.asyncio
async def test_worker_error_propagates_and_stops_pool():
    calls: list[int] = []

    async def worker(i: int) -> None:
        calls.append(i)
        await asyncio.sleep(0.01)
        if i == 2:
            raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await run_windowed(range(8), 2, worker)
    assert 2 in calls
    # 出错后其余排队项不再全部执行
    assert len(calls) < 8


@pytest.mark.asyncio
async def test_on_submit_called_for_each_item():
    submitted: list[int] = []

    async def worker(i: int) -> None:
        await asyncio.sleep(0)

    await run_windowed(range(5), 2, worker, on_submit=submitted.append)
    assert submitted == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_empty_items_noop():
    called = False

    async def worker(i: int) -> None:
        nonlocal called
        called = True

    await run_windowed([], 3, worker)
    assert not called
