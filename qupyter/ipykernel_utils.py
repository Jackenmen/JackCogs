# Copyright 2018-present Jakub Kuczys (https://github.com/Jackenmen)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
import functools
import inspect
import sys
from typing import Any, Dict, Generator, List, Literal, Optional

from ipykernel.iostream import OutStream
from ipykernel.ipkernel import IPythonKernel
from ipykernel.kernelapp import IPKernelApp
from ipykernel.zmqshell import ZMQInteractiveShell
from IPython.core.interactiveshell import ExecutionResult, _asyncio_runner
from ipython_genutils.py3compat import safe_unicode
from tornado import gen, ioloop
from traitlets.traitlets import Bool
from zmq.eventloop.zmqstream import ZMQStream


def clear_singleton_instances() -> None:
    """Clear singleton instances."""
    RedIPKernelApp.clear_instance()
    RedIPythonKernel.clear_instance()
    RedZMQInteractiveShell.clear_instance()


def embed_kernel(
    local_ns: Dict[str, Any],
    *,
    execution_key: Optional[bytes] = None,
    **kwargs: Any,
) -> RedIPKernelApp:
    """
    Embed and start an IPython kernel in a given scope.

    Parameters
    ----------
    local_ns: Dict[str, Any]
        The namespace to load into IPython user namespace.
    execution_key: bytes, optional
        The execution key used for signing messages.
    kwargs: various, optional
        Further keyword args are relayed to the RedIPKernelApp constructor,
        allowing configuration of the Kernel. Will only have an effect
        on the first embed_kernel call for a given process.
    """
    # get the app if it exists, or set it up if it doesn't
    if RedIPKernelApp.initialized():
        app = RedIPKernelApp.instance()
    else:
        app = RedIPKernelApp.instance(**kwargs)
        if execution_key is not None:
            app.session.key = execution_key
        app.initialize([])

    app.kernel.user_ns = local_ns
    app.shell.set_completer_frame()
    app.start()
    return app


class ForceFalse(Bool):
    def validate(self, obj: object, value: Any) -> Literal[False]:
        super().validate(obj, value)
        return False

    def from_string(self, s: str) -> Literal[False]:
        super().from_string(s)
        return False


class RedZMQInteractiveShell(ZMQInteractiveShell):
    # prevents the shell from closing the event loop, when exiting
    exit_now = ForceFalse()


class RedIPythonKernel(IPythonKernel):
    shell_class = RedZMQInteractiveShell

    @gen.coroutine
    def shutdown_request(
        self, stream: ZMQStream, ident: List[bytes], parent: Dict[str, Any]
    ) -> None:
        """
        I shouldn't be doing what I'm doing here, but who cares?

        Basically prevents `exit` command in Jupyter console from closing
        the kernel and taking Red (or rather its event loop) with it.
        """
        self.session.send(
            stream, "shutdown_reply", {"status": "abort"}, parent, ident=ident
        )

    @gen.coroutine
    def do_execute(
        self,
        code: str,
        silent: bool,
        store_history: bool = True,
        user_expressions: Optional[Dict[str, str]] = None,
        allow_stdin: bool = False,
    ) -> Generator[Any, Any, Dict[str, Any]]:
        """
        Copied from IPythonKernel.do_execute(), stripped from comments.

        Only thing that was modified is running non-async code
        that uses `loop.run_in_executor()` instead to avoid blocking the bot.
        While Dev cog's eval doesn't do this, with IPython there are reasons,
        why it's good to do it like this (e.g. using the shell magic cell).
        """
        shell = self.shell

        self._forward_input(allow_stdin)

        reply_content: Dict[str, Any] = {}
        if hasattr(shell, "run_cell_async") and hasattr(shell, "should_run_async"):
            run_cell = shell.run_cell_async
            should_run_async = shell.should_run_async
        else:

            def should_run_async(*args: Any, **kwargs: Any) -> Literal[False]:
                return False

            # mypy has its issues with this
            @gen.coroutine
            def run_cell(*args: Any, **kwargs: Any) -> ExecutionResult:
                return shell.run_cell(*args, **kwargs)

        try:

            if (
                _asyncio_runner
                and should_run_async(code)
                and shell.loop_runner is _asyncio_runner
                and asyncio.get_event_loop().is_running()
            ):
                coro = run_cell(code, store_history=store_history, silent=silent)
                coro_future = asyncio.ensure_future(coro)

                with self._cancel_on_sigint(coro_future):
                    res = None
                    try:
                        res = yield coro_future
                    finally:
                        shell.events.trigger("post_execute")
                        if not silent:
                            shell.events.trigger("post_run_cell", res)
            else:
                loop = asyncio.get_event_loop()
                # run non-async code in executor unlike the super-method
                res = yield loop.run_in_executor(
                    None,
                    functools.partial(
                        shell.run_cell, code, store_history=store_history, silent=silent
                    ),
                )
        finally:
            self._restore_input()

        if res.error_before_exec is not None:
            err = res.error_before_exec
        else:
            err = res.error_in_exec

        if res.success:
            reply_content["status"] = "ok"
        else:
            reply_content["status"] = "error"

            reply_content.update(
                {
                    "traceback": shell._last_traceback or [],
                    "ename": str(type(err).__name__),
                    "evalue": safe_unicode(err),
                }
            )

            e_info = dict(
                engine_uuid=self.ident,
                engine_id=self.int_id,
                method="execute",
            )
            reply_content["engine_info"] = e_info

        reply_content["execution_count"] = shell.execution_count - 1

        if "traceback" in reply_content:
            self.log.info(
                "Exception in execute request:\n%s",
                "\n".join(reply_content["traceback"]),
            )

        if reply_content["status"] == "ok":
            reply_content["user_expressions"] = shell.user_expressions(
                user_expressions or {}
            )
        else:
            reply_content["user_expressions"] = {}

        reply_content["payload"] = shell.payload_manager.read_payload()
        shell.payload_manager.clear_payload()

        return reply_content


class RedOutStream(OutStream):
    """
    Prevents ipykernel from suppressing console output,
    while keeping IPython's output from showing up in console.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.__echo = None
        if self.name == "stdout":
            self.__echo = sys.__stdout__
        elif self.name == "stderr":
            self.__echo = sys.__stderr__

    def _flush(self) -> None:
        if self.__echo is not None:
            self.__echo.flush()
        super()._flush()

    # blame the upstream for not returning int here
    def write(self, string: str) -> None:  # type: ignore[override]
        # is this hacky? yes
        # does it work? also yes
        try:
            frame = inspect.currentframe()
            while frame is not None:
                if frame.f_code.co_name == "run_code" and getattr(
                    inspect.getmodule(frame), "__name__", ""
                ).startswith("IPython"):
                    break
                frame = frame.f_back
            else:
                # if we don't find a `run_code` frame, we should echo to console
                if self.__echo is not None:
                    self.__echo.write(string)
                # we could probably return here, but writing to IPython's stream
                # could be helpful if someone spawns a background task
        finally:
            del frame
        super().write(string)


class RedIPKernelApp(IPKernelApp):
    kernel_class = RedIPythonKernel
    kernel: RedIPythonKernel
    outstream_class = "qupyter.ipykernel_utils.RedOutStream"
    kernel_name = "IPython Kernel for Red"

    def start(self) -> None:
        """
        Same as IPKernelApp.start(),
        but doesn't try to run the event loop on its own.
        """
        if self.subapp is not None:
            raise RuntimeError("RedIPKernelApp does not support subapps!")
        if self.trio_loop:
            raise RuntimeError("RedIPKernelApp does not support trio loop!")

        if self.poller is not None:
            self.poller.start()
        self.kernel.start()
        self.io_loop = ioloop.IOLoop.current()

    def close(self) -> None:
        # cause ipykernel only handled this, because it was closing the whole loop
        for socket in (self.stdin_socket, self.shell_socket, self.control_socket):
            if socket is not None:
                self.io_loop.remove_handler(socket)
        super().close()

    def init_sys_modules(self) -> None:
        """Explicitly overwrite this to do nothing in embedded app."""

    def log_connection_info(self) -> None:
        """
        This would just be overridden to do nothing,
        but apparently this method is also supposed to store ports...
        """
        self.ports = {
            "shell": self.shell_port,
            "iopub": self.iopub_port,
            "stdin": self.stdin_port,
            "hb": self.hb_port,
            "control": self.control_port,
        }
