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

"""
This an incomplete stub of ipykernel library for use of cogs in this repo.
Nobody have made a full stub for this library so only stuff used by this repo is typed.
"""

from typing import Optional, Protocol

import zmq
from IPython.core.application import BaseIPythonApplication
from IPython.core.shellapp import InteractiveShellApp
from jupyter_client.connect import ConnectionFileMixin
from jupyter_client.session import Session

class _Thread(Protocol):
    def start(self) -> None: ...

class IPKernelApp(BaseIPythonApplication, InteractiveShellApp, ConnectionFileMixin):
    control_port: int
    hb_port: int
    iopub_port: int
    shell_port: int
    stdin_port: int
    trio_loop: bool
    poller: Optional[_Thread]
    session: Session
    control_socket: Optional[zmq.Socket]
    shell_socket: Optional[zmq.Socket]
    stdin_socket: Optional[zmq.Socket]
    connection_file: str
    connection_dir: str
    def cleanup_connection_file(self) -> None: ...
    def close(self) -> None: ...
