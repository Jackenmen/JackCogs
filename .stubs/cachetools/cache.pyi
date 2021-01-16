from typing import Callable, Generic, Iterator, Optional, TypeVar

from .abc import DefaultMapping as DefaultMapping

_KT = TypeVar("_KT")
_VT = TypeVar("_VT")

class Cache(DefaultMapping[_KT, _VT], Generic[_KT, _VT]):
    def __init__(self, maxsize: int, getsizeof: Optional[Callable[[_VT], int]] = ...) -> None: ...
    def __getitem__(self, key: _KT, cache_getitem: Callable[[_KT], _VT] = ...) -> _VT: ...
    def __setitem__(self, key: _KT, value: _VT, cache_setitem: Callable[[_KT, _VT], None] = ...) -> None: ...
    def __delitem__(self, key: _KT, cache_delitem: Callable[[_KT], None] = ...) -> None: ...
    def __iter__(self) -> Iterator[_KT]: ...
    def __len__(self) -> int: ...
    @property
    def maxsize(self) -> int:
        """
        The maximum size of the cache.
        """
        ...
    @property
    def currsize(self) -> int:
        """
        The current size of the cache.
        """
        ...
    @staticmethod
    def getsizeof(value: _VT) -> int:
        """
        Return the size of a cache element’s value.
        """
        ...
