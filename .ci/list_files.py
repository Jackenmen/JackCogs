"""List files that should be checked with current Python version.

Usage: list_files.py

NOTE: Python versions required by different Red versions are currently hard-coded.
Note for contributors:
  This code has to run on Python 3.6+
"""
import sys
import yaml
from pathlib import Path

from redbot import VersionInfo

max_red_versions = {
    (3, 6): VersionInfo.from_str("3.1.0"),
    (3, 7): VersionInfo.from_str("3.2.0"),
    (3, 8): None,
}
python_version = sys.version_info
max_red_version = max_red_versions[python_version[:2]]

# assuming that only the newest version has `None`
if max_red_version is None:
    print("./")
    sys.exit(0)

ROOT_PATH = Path(__file__).absolute().parent.parent

with open(ROOT_PATH / "info.yaml") as fp:
    data = yaml.safe_load(fp)

cogs = data["cogs"]
folder_list = []
for pkg_name, cog_data in cogs.items():
    add_to_files = True
    min_bot_version = cog_data.get("min_bot_version")
    if min_bot_version is not None:
        version_info = VersionInfo.from_str(min_bot_version)
        if version_info >= max_red_version:
            continue

    min_python_version = cog_data.get("min_python_version")
    if min_python_version is not None:
        # we're ignoring micro version here, matrix should use the newest version anyway
        version_info = tuple(map(int, min_bot_version.split(".")[:2]))
        if version_info > python_version:
            continue

    folder_list.append(pkg_name)

print(" ".join(folder_list))
