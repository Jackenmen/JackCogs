"""
Copyright 2018-2020 Jakub Kuczys (https://github.com/jack1142)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import sys
from strictyaml import YAMLValidationError

from .checks import (
    check_cog_data_path_use,
    check_command_docstrings,
    check_key_order,
    check_package_end_user_data_statements,
)
from .file_generators import generate_repo_info_file, process_cogs
from .schema import load_info_yaml
from .transformations import update_class_docstrings


# TODO: allow author in COG_KEYS and merge them with repo/shared fields lists
# TODO: auto-format to proper key order


def main() -> bool:
    print("Loading info.yaml...")
    try:
        data = load_info_yaml()
    except YAMLValidationError as e:
        print(str(e))
        return False

    success = True

    print("Checking order in sections...")
    success &= check_key_order(data)

    cogs = data["cogs"]
    repo_info = data["repo"]

    print("Preparing repo's info.json...")
    generate_repo_info_file(repo_info)

    print("Preparing info.json files for cogs...")
    if not process_cogs(data):
        return False

    print("Updating class docstrings...")
    update_class_docstrings(cogs, repo_info)
    print("Checking for cog_data_path usage...")
    success &= check_cog_data_path_use(cogs)
    print("Checking for missing help docstrings...")
    success &= check_command_docstrings(cogs)
    print("Checking for missing end user data statements...")
    success &= check_package_end_user_data_statements(cogs)

    print("Done!")
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(int(not success))
