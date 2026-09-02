"""Adds CPython's Windows-only os.spawn* functions on top of the built-in os.

Everything else (file/dir/stat handling) comes from the built-in `uos`
unchanged. Like unix-ffi/os relative to python-stdlib/os, this package fully
replaces the "os" package name rather than layering on top of
python-stdlib/os (the two can't be combined, since both install to the same
"os" path) -- install this instead of python-stdlib/os on ports/windows, not
alongside it.

spawnve/spawnle are currently disabled: on this runtime, calling _wspawnve
from inside a function crashes the interpreter (STATUS_ACCESS_VIOLATION),
which is unavoidable for any real caller since spawnve() itself is a
function. spawnv/spawnl (no env argument, via _wspawnv) do not exhibit this
and are unaffected.
"""

from uos import *

import array
import uctypes
import ffi

from _wstr import wstr


def _dll(name):
    try:
        return ffi.open(name)
    except OSError as e:
        raise ImportError("failed to open {!r}: {}".format(name, e))


try:
    _ucrtbase = _dll("ucrtbase.dll")
except ImportError:
    # Keep the rest of `os` (from uos, above) usable even if the CRT DLL
    # can't be opened; only spawn* actually need it.
    _ucrtbase = None

if _ucrtbase:
    # intptr_t _wspawnv(int mode, const wchar_t *cmdname, const wchar_t *const *argv);
    # Return type is "p" (pointer-sized), not "l": intptr_t is pointer-width,
    # but C `long` is only 32 bits on Windows (LLP64), which would truncate
    # the result on a 64-bit build.
    _wspawnv = _ucrtbase.func("p", "_wspawnv", "ipp")
    # errno_t _get_errno(int *pValue). Read via ucrtbase directly rather than
    # the built-in os.errno(): that reads the errno of whichever CRT
    # MicroPython itself is linked against, which for a MinGW build is
    # msvcrt.dll, not ucrtbase.dll -- a different errno location entirely.
    _get_errno = _ucrtbase.func("i", "_get_errno", "p")

# Real CPython os.P_* / CRT process.h _P_* values.
P_WAIT = 0
P_NOWAIT = 1
P_OVERLAY = 2
P_NOWAITO = 3
P_DETACH = 4

_errno_buf = array.array("i", [0])


def get_errno():
    _get_errno(uctypes.addressof(_errno_buf))
    return _errno_buf[0]


def check_error(ret):
    # _wspawnv returns -1 and sets the CRT errno on failure.
    if ret == -1:
        raise OSError(get_errno())
    return ret


def _argv(args):
    if not args:
        raise ValueError("spawnv() arg 2 must not be empty")
    if not args[0]:
        raise ValueError("spawnv() arg 2 first element cannot be empty")
    _bufs = [wstr(a) for a in args]  # must outlive the spawn call below
    ptrs = array.array("P", [uctypes.addressof(b) for b in _bufs] + [0])
    return _bufs, ptrs


def spawnv(mode, path, args):
    # Note: P_NOWAIT/P_NOWAITO/P_DETACH return a live process handle with no
    # way here to wait on or close it (no os.waitpid equivalent yet) -- only
    # P_WAIT is fully round-trippable for now.
    _bufs, argv = _argv(args)
    path_buf = wstr(path)
    r = _wspawnv(mode, path_buf, argv)
    return check_error(r)


def spawnve(mode, path, args, env):
    raise NotImplementedError(
        "os.spawnve is disabled on this runtime: _wspawnve crashes the "
        "interpreter when called from inside a function, see the os module "
        "docstring"
    )


def spawnl(mode, path, *args):
    return spawnv(mode, path, args)


def spawnle(mode, path, *args):
    env = args[-1]
    return spawnve(mode, path, args[:-1], env)
