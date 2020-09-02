from typing import Callable, Iterator, Optional, Sequence, TypeVar

from .cache import Cache as Cache

_KT = TypeVar("_KT")
_VT = TypeVar("_VT")

class RRCache(Cache[_KT, _VT]):
    """Random Replacement (RR) cache implementation."""

    def __init__(
        self,
        maxsize: int,
        choice: Optional[Callable[[Sequence[_KT]], _KT]] = ...,
        getsizeof: Optional[Callable[[_VT], int]] = ...,
    ) -> None: ...
    def __getitem__(self, key: _KT, cache_getitem: Callable[[_KT], _VT] = ...) -> _VT: ...
    def __setitem__(self, key: _KT, value: _VT, cache_setitem: Callable[[_KT, _VT], None] = ...) -> None: ...
    def __delitem__(self, key: _KT, cache_delitem: Callable[[_KT], None] = ...) -> None: ...
    def __iter__(self) -> Iterator[_KT]: ...
    def __len__(self) -> int: ...
    @property
    def choice(self) -> Callable[[Sequence[_KT]], _KT]:
        """
        The `choice` function used by the cache.
        """
        ...
