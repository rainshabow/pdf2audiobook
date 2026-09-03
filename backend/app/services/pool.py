"""滑动窗口并发池。

与“预创建全部任务 + 信号量/分批等待”不同，这里使用固定数量的 worker 持续
消费队列：任意时刻最多 `concurrency` 个 worker 在运行，每当一个 worker 完成
当前项，立即从队列取出下一个排队项（滑动窗口）。

- concurrency < 0 或 None：不限并发（一次性调度全部项）
- concurrency >= 1：窗口大小即并发上限
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, TypeVar

T = TypeVar("T")


async def run_windowed(
    items: Iterable[T],
    concurrency: int | None,
    worker: Callable[[T], Awaitable[Any]],
    on_submit: Callable[[T], None] | None = None,
) -> None:
    """以滑动窗口方式并发执行 worker(item)。

    on_submit 在每项进入队列/调度前同步调用（用于“提交即推进进度”等统计）。
    任一 worker 抛错时立即终止其余 worker 并向上抛出该错误。
    """
    seq = list(items)
    if not seq:
        return
    if on_submit is not None:
        for it in seq:
            on_submit(it)

    # 不限并发：直接并发调度全部项
    if concurrency is None or concurrency < 0:
        tasks = [asyncio.create_task(worker(it)) for it in seq]
        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return

    limit = max(1, min(int(concurrency), len(seq)))
    queue: asyncio.Queue[T] = asyncio.Queue()
    for it in seq:
        queue.put_nowait(it)

    async def _consume() -> None:
        while True:
            it = await queue.get()
            try:
                await worker(it)
            finally:
                queue.task_done()

    workers = [asyncio.create_task(_consume()) for _ in range(limit)]
    join_task = asyncio.create_task(queue.join())
    try:
        done, _ = await asyncio.wait(
            {join_task, *workers}, return_when=asyncio.FIRST_COMPLETED)
        # worker 正常时永不自行结束；出现在 done 中的 worker 只可能是异常退出。
        # 即使它是最后一个排队项（queue.join 同时完成），也必须把异常抛出去。
        for t in workers:
            if t in done:
                await t
        # join 未完成但无异常 worker：理论不可达，防御性兜底
        if join_task not in done:
            raise RuntimeError("并发池 worker 提前退出")
    finally:
        join_task.cancel()
        for t in workers:
            t.cancel()
        await asyncio.gather(join_task, *workers, return_exceptions=True)
