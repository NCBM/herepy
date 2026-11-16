"""herecraft.kernel.host — the thread the loop runs on, and how work reaches it.

The Python half runs on one thread, and that thread is inside an event loop for the whole of its
life (ADR 0009). Java hands work to the loop through this module and nowhere else: `submit` when
nobody waits for the answer, `call_sync` when a cancellable event needs one. Everything a unit wrote
runs on the loop, so the interpreter is single-threaded in the only sense that matters — one loop.

The one thing that happens off the loop is the handover itself, which is what
`asyncio.run_coroutine_threadsafe` exists for: it schedules the work on the loop and answers a future.
A calling thread is only there to wait, and it waits in `Future.result(timeout)`, which releases the
GIL, so the loop keeps running while it does.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
import concurrent.futures
import inspect
import logging
import threading
import time
from typing import Any

logger = logging.getLogger("herecraft.kernel")

# How long a `call_sync` caller waits before the answer becomes "none". The caller is the game thread
# and a tick is 50 ms, so this is where a stalled dispatch has already cost ticks. The deadline is a
# policy, so it is written once, here, and every synchronous crossing pays the same one.
SYNC_TIMEOUT = 0.1

# What Java may name, and what runs. A name that is not here is refused with the names that are,
# rather than resolved as an attribute of wherever the caller happened to be.
_ENTRIES: dict[str, Callable[..., Awaitable[Any]]] = {}

_loop: asyncio.AbstractEventLoop | None = None
_host_thread: int | None = None

# Tasks started on the loop by name, kept until they finish: a pending task nobody refers to can be
# collected while it is still going to run.
_tasks: set[asyncio.Task[Any]] = set()


def entry(name: str) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Register the coroutine function Java reaches as ``name``."""

    def register(run: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        _ENTRIES[name] = run
        return run

    return register


def serve(load: Callable[[], Coroutine[Any, Any, None]]) -> None:
    """Run this thread's loop until it stops, with ``load`` as its first task.

    Called on the host thread as the last thing it does: the interpreter is bootstrapped before this
    and the loop's life is the thread's life, so the call does not return until shutdown. ``load``
    runs inside the loop rather than before it because loading a unit awaits now — a unit's scope
    disposal is a coroutine (ADR 0010 with ADR 0009 in place).
    """
    global _loop, _host_thread
    if _loop is not None:
        msg = "the host thread is already serving a loop"
        raise RuntimeError(msg)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _loop = loop
    _host_thread = threading.get_ident()
    logger.debug("host thread %d is serving", _host_thread)
    try:
        _keep(loop.create_task(load(), name="load"))
        loop.run_forever()
    finally:
        _close(loop)
        _loop = None
        _host_thread = None


def submit(target: str, *args: Any) -> None:
    """Hand ``target`` to the loop and answer without waiting for it."""
    loop, on_loop = _serving(target)
    if on_loop:
        _keep(loop.create_task(_invoke(target, args), name=target))
        return
    future = asyncio.run_coroutine_threadsafe(_invoke(target, args), loop)
    future.add_done_callback(_reported(target))


def call_sync(target: str, *args: Any) -> Any | None:
    """Ask the loop for ``target``'s answer, waiting no longer than :data:`SYNC_TIMEOUT`.

    Called from the loop thread this is a deadlock — the loop cannot answer while it waits for the
    answer — so it is refused instead of tolerated (ADR 0009). ``None`` answers a call that did not
    finish in time: the work is cancelled, and the caller's decision degrades to "no answer" rather
    than to a stalled game thread.
    """
    loop, on_loop = _serving(target)
    if on_loop:
        msg = (
            f"{target} asked for a synchronous answer from the thread that has to give it, so the "
            "wait would never end. A coroutine that needs to cross hands the work over with submit."
        )
        raise RuntimeError(msg)
    future = asyncio.run_coroutine_threadsafe(_invoke(target, args), loop)
    started = time.monotonic()
    try:
        return future.result(SYNC_TIMEOUT)
    except concurrent.futures.TimeoutError:
        _ = future.cancel()
        logger.warning(
            "%s did not answer within %.2f s: it was cancelled and the answer counts as none",
            target,
            time.monotonic() - started,
        )
        return None
    except asyncio.CancelledError:
        logger.warning("%s was cancelled before it answered", target)
        return None
    except Exception:
        logger.exception("%s failed while a caller waited for it", target)
        return None


def stop() -> None:
    """Ask the loop to finish; :func:`serve` closes it and returns.

    Safe from any thread, and unlike the other entries it does not go on the loop: `stop` is what
    ends the loop, so it cannot wait for the loop to run it.
    """
    loop = _loop
    if loop is None:
        return
    _ = loop.call_soon_threadsafe(loop.stop)


def _serving(target: str) -> tuple[asyncio.AbstractEventLoop, bool]:
    """The loop to hand ``target`` to, and whether the caller is already on it."""
    if _loop is None:
        msg = (
            f"{target} was submitted while the host loop is not serving, so nothing would run it. "
            "The loop starts with the host thread, before any unit is loaded."
        )
        raise RuntimeError(msg)
    return _loop, threading.get_ident() == _host_thread


async def _invoke(target: str, args: tuple[Any, ...]) -> Any:
    """Run one named entry; a plain function is as good as a coroutine, and both answer here."""
    run = _ENTRIES.get(target)
    if run is None:
        msg = f"no entry named {target!r} is registered; the entries are {sorted(_ENTRIES)}"
        raise KeyError(msg)
    result = run(*args)
    if inspect.isawaitable(result):
        return await result
    return result


def _keep(task: asyncio.Task[Any]) -> None:
    """Hold a task until it finishes, and report the failure it had if it had one."""
    _tasks.add(task)
    task.add_done_callback(_finished)


def _finished(task: asyncio.Task[Any]) -> None:
    _tasks.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.error("%s failed on the host loop", task.get_name(), exc_info=error)


def _reported(target: str) -> Callable[[concurrent.futures.Future[Any]], None]:
    """Name the task in the report, which a bare future's failure would not."""

    def report(future: concurrent.futures.Future[Any]) -> None:
        if future.cancelled():
            return
        error = future.exception()
        if error is not None:
            logger.error("%s failed on the host loop", target, exc_info=error)

    return report


def _close(loop: asyncio.AbstractEventLoop) -> None:
    """Cancel what the loop still holds and close it: this thread gets no second epoch."""
    pending = asyncio.all_tasks(loop)
    for task in pending:
        _ = task.cancel()
    if pending:
        _ = loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    _ = loop.run_until_complete(loop.shutdown_asyncgens())
    asyncio.set_event_loop(None)
    loop.close()
    logger.debug("host loop closed, %d task(s) cancelled", len(pending))
