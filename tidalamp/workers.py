"""Work the app does off its own methods: threads, and what outlives the UI.

`thread_worker` is Textual's `@work` for the objects that are not widgets.
`@work` only decorates a method of a DOM node: it asks ``self`` to run the
worker. The app's and the browser's collaborators are plain objects,
each with the node it works for in ``node``. `thread_worker` runs the method
on that node, so its group and its exclusivity mean what they meant while the
method lived on the node itself: an exclusive worker still cancels only the
workers of its own group, on the same node.

`call_from_thread` is how a worker's thread hands its answer to the UI, also
when the app has stopped meanwhile, and `quiet_after_teardown` lets a timer
that fires during the exit find no widgets without raising.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import inspect
import threading
from collections.abc import Callable
from concurrent.futures import CancelledError
from typing import Any, Concatenate, ParamSpec, Protocol, TypeVar, cast

from textual.app import App, ScreenStackError
from textual.css.query import NoMatches
from textual.dom import DOMNode
from textual.worker import Worker


class OwnsNode(Protocol):
    @property
    def node(self) -> DOMNode: ...


Owner = TypeVar("Owner", bound=OwnsNode)
Params = ParamSpec("Params")
Result = TypeVar("Result")


def thread_worker(
    *, group: str = "default", exclusive: bool = True
) -> Callable[
    [Callable[Concatenate[Owner, Params], Result]],
    Callable[Concatenate[Owner, Params], Worker[Result]],
]:
    """`@work(thread=True, exclusive=..., group=...)` for ``self.node``."""

    def decorator(
        method: Callable[Concatenate[Owner, Params], Result],
    ) -> Callable[Concatenate[Owner, Params], Worker[Result]]:
        @functools.wraps(method)
        def start(
            self: Owner, *args: Params.args, **kwargs: Params.kwargs
        ) -> Worker[Result]:
            work: Callable[[], Any] = functools.partial(method, self, *args, **kwargs)
            return cast(
                "Worker[Result]",
                self.node.run_worker(
                    work,
                    name=method.__name__,
                    group=group,
                    exclusive=exclusive,
                    thread=True,
                ),
            )

        return start

    return decorator


# How often a thread waiting on the UI looks up to see whether the app has
# stopped under it. Only a call made as the app closes ever waits this long.
THREAD_CALL_POLL = 0.1


def call_from_thread(
    app: App, callback: Callable[..., Any], *args: Any, **kwargs: Any
) -> Any:
    """Textual's, for a thread worker that finishes after the app has.

    Nothing stops a worker from finishing while the app closes, and then
    Textual's version raises inside that thread ("App is not running"),
    runs the callback against widgets that are already gone, or, when the
    loop stops before getting to it, waits for it forever and holds
    asyncio.run() on the thread. Once the app has stopped there is no
    screen left to update, so the call is dropped and returns None, which
    no caller reads. While the app runs this is Textual's call unchanged,
    exceptions included.
    """
    loop = app._loop
    if loop is None or not app.is_running:
        return None
    if threading.get_ident() == app._thread_id:
        raise RuntimeError("call_from_thread must run off the app's thread")

    async def run_callback() -> Any:
        if not app.is_running:
            return None
        with app._context():
            result = callback(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result

    pending = run_callback()
    try:
        future = asyncio.run_coroutine_threadsafe(pending, loop)
    except RuntimeError:  # the loop closed between the check and here
        pending.close()
        return None
    while True:
        try:
            return future.result(timeout=THREAD_CALL_POLL)
        except TimeoutError:
            if not loop.is_running():
                # Never going to be run: close it, or Python says so on
                # the way out ("coroutine ... was never awaited").
                future.cancel()
                with contextlib.suppress(RuntimeError, ValueError):
                    pending.close()
                return None
            if not app.is_running:
                future.cancel()
                return None
        except CancelledError:
            if app.is_running:
                raise
            return None


def quiet_after_teardown(method: Callable[..., Any]) -> Callable[..., Any]:
    """Let a timer or a resize that arrives during exit find nothing, quietly.

    Textual's own shutdown tears the screens down, and a tick or a resize
    already queued can still run after that and look for widgets that are
    gone, or even for a screen when the stack is already empty. There is
    nothing left to update then. While the app is running the error goes
    through: a widget or a screen missing then is a real fault. It decorates
    the app's own methods and its collaborators', which ask their ``app``.
    """

    @functools.wraps(method)
    def guarded(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return method(self, *args, **kwargs)
        except (NoMatches, ScreenStackError):
            # The app itself, or a collaborator's: they all carry it in `app`.
            owner = self if isinstance(self, App) else getattr(self, "app", self)
            if getattr(owner, "_running", True):
                raise
            return None

    return guarded
