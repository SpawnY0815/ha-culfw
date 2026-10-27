"""Start and stop the tasks of the protocol layer."""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

type CreateTask = Callable[[Coroutine[Any, Any, None], str], asyncio.Task[None]]


def start_task(coro: Coroutine[Any, Any, None], name: str) -> asyncio.Task[None]:
    """Start a named task on the running loop; the default task factory."""
    return asyncio.create_task(coro, name=name)


async def cancel_task(task: asyncio.Task[None]) -> None:
    """Cancel a task and wait until it ended.

    The cancellation of the task is the expected end, so it is not raised, but an
    error that ended the task is. A cancellation of the caller is raised too.
    Awaiting the task could not tell the two apart and would swallow a request to
    stop that was meant for the caller.
    """
    task.cancel()
    await asyncio.wait({task})
    if not task.cancelled():
        task.result()
