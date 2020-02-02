# this an incomplete stub of pillow library for use of cogs in this repo
# nobody made full stub for this library so only stuff used by this repo is typed

from typing import Any, Optional, Tuple

XY = Tuple[int, int]
Size = XY

class ImageFont:
    def getsize(self, text: str, *args: Any, **kwargs: Any) -> Size: ...

# not very correct but good enough for my usage
def truetype(
    font: str = ...,
    size: int = ...,
    index: int = ...,
    encoding: str = ...,
    layout_engine: Optional[Any] = ...,
) -> ImageFont: ...
