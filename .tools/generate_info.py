from collections.abc import Sequence
from pathlib import Path
import json
import re
import typing

from redbot import VersionInfo
from strictyaml import (
    load as yaml_load,
    Bool,
    EmptyDict,
    EmptyList,
    Enum,
    Map,
    MapPattern,
    Optional,
    Regex,
    ScalarValidator,
    Seq,
    Str,
    Url,
)
from strictyaml.exceptions import YAMLValidationError, YAMLSerializationError
from strictyaml.utils import is_string
from strictyaml.yamllocation import YAMLChunk


ROOT_PATH = Path(__file__).absolute().parent.parent


class PythonVersion(ScalarValidator):
    REGEX = re.compile(r"(\d+)\.(\d+)\.(\d+)")

    def __init__(self) -> None:
        self._matching_message = "when expecting Python version (MAJOR.MINOR.MICRO)"

    def validate_scalar(self, chunk: YAMLChunk) -> typing.List[int]:
        match = self.REGEX.fullmatch(chunk.contents)
        if match is None:
            raise YAMLValidationError(
                self._matching_message, "found non-matching string", chunk
            )
        return [int(group) for group in match.group(1, 2, 3)]

    def to_yaml(self, data: typing.Any) -> str:
        if isinstance(data, Sequence):
            if len(data) != 3:
                raise YAMLSerializationError(
                    f"expected a sequence of 3 elements, got {len(data)} elements"
                )
            for item in data:
                if not isinstance(item, int):
                    raise YAMLSerializationError(
                        f"expected int, got '{item}' of type '{type(item).__name__}'"
                    )
                if item < 0:
                    raise YAMLSerializationError(
                        f"expected non-negative int, got {item}"
                    )
            return ".".join(str(segment) for segment in data)
        if is_string(data):
            # we just validated that it's a string
            version_string = typing.cast(str, data)
            if self.REGEX.fullmatch(version_string) is None:
                raise YAMLSerializationError(
                    "expected Python version (MAJOR.MINOR.MICRO),"
                    f" got '{version_string}'"
                )
            return version_string
        raise YAMLSerializationError(
            "expected string or sequence,"
            f" got '{data}' of type '{type(data).__name__}'"
        )


REPO_KEYS = {
    "name": Str(),  # Downloader doesn't use this but I can set friendlier name
    "short": Str(),
    "description": Str(),
    "install_msg": Str(),
    "author": Seq(Str()),
}
COMMON_KEYS = {
    Optional("min_bot_version"): Regex(VersionInfo._VERSION_STR_PATTERN),
    Optional("max_bot_version"): Regex(VersionInfo._VERSION_STR_PATTERN),
    Optional("min_python_version"): PythonVersion(),
    Optional("hidden", False): Bool(),
    Optional("disabled", False): Bool(),
    Optional("type", "COG"): Enum(["COG", "SHARED_LIBRARY"]),
}
SHARED_FIELDS_KEYS = {
    **COMMON_KEYS,
    "install_msg": Str(),
    "author": Seq(Str()),
}
COG_KEYS = {
    **COMMON_KEYS,
    "name": Str(),  # Downloader doesn't use this but I can set friendlier name
    "short": Str(),
    "description": Str(),
    Optional("install_msg"): Str(),
    Optional("required_cogs", {}): EmptyDict() | MapPattern(Str(), Url()),
    Optional("requirements", []): EmptyList() | Seq(Str()),
    Optional("tags", []): EmptyList() | Seq(Str()),
}
SCHEMA = Map(
    {
        "repo": Map(REPO_KEYS),
        "shared_fields": Map(SHARED_FIELDS_KEYS),
        "cogs": MapPattern(Str(), Map(COG_KEYS)),
    }
)


def main() -> None:
    print("Loading info.yaml...")
    with open("info.yaml") as fp:
        data = yaml_load(fp.read(), SCHEMA).data

    print("Preparing repo's info.json...")
    repo_info = data["repo"]
    repo_info["install_msg"] = repo_info["install_msg"].format_map(
        {"repo_name": repo_info["name"]}
    )
    with open(ROOT_PATH / "info.json", "w") as fp:
        json.dump(repo_info, fp, indent=4)

    requirements: typing.Set[str] = set()
    print("Preparing info.json files for cogs...")
    shared_fields = data["shared_fields"]
    cogs = data["cogs"]
    for pkg_name, cog_info in cogs.items():
        requirements.update(cog_info["requirements"])
        print(f"Preparing info.json for {pkg_name} cog...")
        output = shared_fields.copy()
        output.update(cog_info)
        replacements = {
            "repo_name": repo_info["name"],
            "cog_name": output["name"],
        }
        for to_replace in ("short", "description", "install_msg"):
            output[to_replace] = output[to_replace].format_map(replacements)

        with open(ROOT_PATH / pkg_name / "info.json", "w") as fp:
            json.dump(output, fp, indent=4)

    print("Preparing requirements file for CI...")
    with open(ROOT_PATH / ".ci/requirements/all_cogs.txt", "w") as fp:
        fp.write("Red-DiscordBot\n")
        for requirement in requirements:
            fp.write(f"{requirement}\n")

    print("Done!")


if __name__ == "__main__":
    main()
