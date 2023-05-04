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

from typing import Any

from strictyaml import YAMLValidationError

from .checks import (
    check_cog_data_path_use,
    check_command_docstrings,
    check_key_order,
    check_package_end_user_data_statements,
)
from .cli import Options, WriteBack
from .file_generators import generate_repo_info_file, process_cogs
from .results import Results
from .schema import load_info_yaml
from .transformations import update_class_docstrings, update_license_headers
from .typedefs import CogsDict, InfoYAMLDict, RepoInfoDict, SharedFieldsDict


class InfoGenMainCommand:
    """
    Main (default) infogen command.

    This object is used per whole run as a main context for all components.
    """

    def __init__(self) -> None:
        self.success = True
        self.options = Options.from_argv()
        self.results = Results(self.options)
        self.ready = False
        self.data: InfoYAMLDict
        self.cogs: CogsDict
        self.repo_info: RepoInfoDict
        self.shared_fields: SharedFieldsDict

    def verbose_print(self, *objects: Any) -> None:
        if self.options.verbose:
            print(*objects)

    vprint = verbose_print

    def load_info_yaml(self) -> None:
        data = load_info_yaml()

        self.data = data
        self.cogs = data["cogs"]
        self.repo_info = data["repo"]
        self.shared_fields = data["shared_fields"]

    def run(self) -> bool:
        self.vprint("Loading info.yaml...")
        try:
            self.load_info_yaml()
        except YAMLValidationError as e:
            print(str(e))
            return False

        self.vprint("Checking order in sections...")
        self.success &= check_key_order(self)

        self.vprint("Preparing repo's info.json...")
        self.success &= generate_repo_info_file(self)

        self.vprint("Preparing info.json files for cogs...")
        if not process_cogs(self):
            return False

        self.vprint("Updating class docstrings...")
        self.success &= update_class_docstrings(self)
        self.vprint("Updating license headers...")
        self.success &= update_license_headers(self)
        self.vprint("Checking for cog_data_path usage...")
        self.success &= check_cog_data_path_use(self)
        self.vprint("Checking for missing help docstrings...")
        self.success &= check_command_docstrings(self)
        self.vprint("Checking for missing end user data statements...")
        self.success &= check_package_end_user_data_statements(self)

        self.vprint("\n---\n")

        self.results.finish_and_print_results()

        if self.options.write_back is not WriteBack.YES:
            self.success &= not self.results.files_changed

        return self.success
