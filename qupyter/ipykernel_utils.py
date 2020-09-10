# Copyright 2018-2020 Jakub Kuczys (https://github.com/jack1142)
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

from typing import Any, Dict, List, Literal

from ipykernel.ipkernel import IPythonKernel
from ipykernel.kernelapp import IPKernelApp
from ipykernel.zmqshell import ZMQInteractiveShell
from tornado import gen, ioloop
from traitlets.traitlets import Bool
from zmq.eventloop.zmqstream import ZMQStream


def clear_singleton_instances() -> None:
    """Clear singleton instances."""
    RedIPKernelApp.clear_instance()
    RedIPythonKernel.clear_instance()
    RedZMQInteractiveShell.clear_instance()


def embed_kernel(local_ns: Dict[str, Any], **kwargs: Any) -> RedIPKernelApp:
    """
    Embed and start an IPython kernel in a given scope.

    Parameters
    ----------
    local_ns: Dict[str, Any]
        The namespace to load into IPython user namespace.
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

    # incorrect type hint in tornado
    # might get fixed by: https://github.com/tornadoweb/tornado/pull/2909
    @gen.coroutine  # type: ignore[arg-type]
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


class RedIPKernelApp(IPKernelApp):
    kernel_class = RedIPythonKernel
    kernel: RedIPythonKernel
    quiet = False  # this prevents ipykernel from suppressing console output
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
