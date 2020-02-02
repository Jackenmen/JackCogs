# this an incomplete stub of fuzzywuzzy library for use of cogs in this repo
# nobody made full stub for this library so only stuff used by this repo is typed

from typing import Callable, Dict, List, Tuple, TypeVar, Union, overload

T = TypeVar("T")
S = TypeVar("S")
@overload
def extract(
    query: T,
    choices: Dict[str, S],
    processor: Callable[[Union[T, S]], str] = ...,
    scorer: Callable[[str, str], int] = ...,
    limit: int = ...,
) -> List[Tuple[S, int, str]]: ...
@overload
def extract(
    query: T,
    choices: List[S],
    processor: Callable[[Union[T, S]], str] = ...,
    scorer: Callable[[str, str], int] = ...,
    limit: int = ...,
) -> List[Tuple[S, int]]: ...
