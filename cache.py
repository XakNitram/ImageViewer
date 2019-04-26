from typing import Dict, Hashable, TypeVar, Mapping, Callable
from collections import OrderedDict
from sys import getsizeof, stderr
from itertools import chain
from collections import deque
try:
    from reprlib import repr
except ImportError:
    pass


# ****** Types ******
_VT = TypeVar("_VT")


def total_size(o, handlers={}, verbose=False):
    """ Returns the approximate memory footprint an object and all of its contents.

    Automatically finds the contents of the following builtin containers and
    their subclasses:  tuple, list, deque, dict, set and frozenset.
    To search other containers, add handlers to iterate over their contents:

        handlers = {SomeContainerClass: iter,
                    OtherContainerClass: OtherContainerClass.get_elements}

    """
    dict_handler = lambda d: chain.from_iterable(d.items())
    all_handlers: Dict[type, Callable] = {
        tuple: iter,
        list: iter,
        deque: iter,
        dict: dict_handler,
        set: iter,
        frozenset: iter,
    }

    all_handlers.update(handlers)     # user handlers take precedence
    seen = set()                      # track which object id's have already been seen
    default_size = getsizeof(0)       # estimate sizeof object without __sizeof__

    def sizeof(o):
        if id(o) in seen:       # do not double count the same object
            return 0
        seen.add(id(o))
        s = getsizeof(o, default_size)

        if verbose:
            print(s, type(o), repr(o), file=stderr)

        for typ, handler in all_handlers.items():
            try:
                if isinstance(o, typ):
                    s += sum(map(sizeof, handler(o)))
                    break
            except TypeError:
                print(f"Errored in size function. Type that caused error: {typ}", file=stderr)
                continue
        return s

    return sizeof(o)


class Cache(OrderedDict, Dict[Hashable, _VT]):
    __slots__ = ("max_size", "default_factory")

    def __init__(self, max_size: int, default_factory: type = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_size = max_size
        self.default_factory = default_factory

    def _cull(self):

        if total_size(self) > self.max_size and len(self) > 1:
            oldest = next(iter(self))
            del self[oldest]

    def __setitem__(self, key: Hashable, value: _VT):
        super().__setitem__(key, value)
        self._cull()

    def __getitem__(self, key: Hashable):
        try:
            value = super().__getitem__(key)
            self.move_to_end(key)
        except KeyError:
            if self.default_factory is None:
                raise
            else:
                value = self.default_factory()
                self[key] = value

        self._cull()

        return value

    def update(self, __m: Mapping[Hashable, _VT], **kwargs: _VT):
        super().update(__m, **kwargs)
        self._cull()
