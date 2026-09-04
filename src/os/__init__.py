"""Adds CPython's Windows-only os additions on top of the built-in os.

Everything else (file/dir/stat handling) comes from the built-in `uos`
unchanged. Like unix-ffi/os relative to python-stdlib/os, this package fully
replaces the "os" package name rather than layering on top of
python-stdlib/os (the two can't be combined, since both install to the same
"os/__init__.py" path) -- install this instead of python-stdlib/os on
ports/windows, not alongside it. Packages that only add to "os" rather than
replacing it, such as os-path and pathlib, layer on top of this package fine.

Only spawnv/spawnl are provided; the env-passing spawnve/spawnle are not
implemented on this port.
"""

from uos import *

try:
    from . import path
except ImportError:
    pass

from ._stat import stat_result, stat

import array
import uctypes

from _wstr import wstr
from _dll import open_dll

try:
    _ucrtbase = open_dll("ucrtbase.dll")
except ImportError:
    # Keep the rest of `os` (from uos, above) usable even if the CRT DLL
    # can't be opened; only the functions below need it.
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
    # int _waccess(const wchar_t *path, int mode);
    _waccess = _ucrtbase.func("i", "_waccess", "pi")
    # int _getpid(void);
    _getpid = _ucrtbase.func("i", "_getpid", "")
    # int _pipe(int *pfds, unsigned int psize, int textmode);
    _pipe = _ucrtbase.func("i", "_pipe", "pIi")
    # int _dup(int fd);
    _dup = _ucrtbase.func("i", "_dup", "i")
    # int _close(int fd);
    _close = _ucrtbase.func("i", "_close", "i")
    # intptr_t _get_osfhandle(int fd);
    _get_osfhandle = _ucrtbase.func("p", "_get_osfhandle", "i")
    # int _read(int fd, void *buffer, unsigned int count);
    _read = _ucrtbase.func("i", "_read", "ipI")
    # int _write(int fd, const void *buffer, unsigned int count);
    _write = _ucrtbase.func("i", "_write", "ipI")

try:
    _shell32 = open_dll("shell32.dll")
except ImportError:
    _shell32 = None

if _shell32:
    # HINSTANCE ShellExecuteW(HWND hwnd, LPCWSTR lpOperation, LPCWSTR lpFile,
    #   LPCWSTR lpParameters, LPCWSTR lpDirectory, INT nShowCmd);
    # Return type is "p": HINSTANCE is an opaque handle-sized value, not an
    # actual instance handle on success -- only its numeric value (<=32 is a
    # legacy error code) is ever inspected here.
    _ShellExecuteW = _shell32.func("p", "ShellExecuteW", "pppppi")

try:
    _kernel32 = open_dll("kernel32.dll")
except ImportError:
    _kernel32 = None

if _kernel32:
    # BOOL SetHandleInformation(HANDLE hObject, DWORD dwMask, DWORD dwFlags);
    _SetHandleInformation = _kernel32.func("i", "SetHandleInformation", "pII")

# Real CPython os.P_* / CRT process.h _P_* values.
P_WAIT = 0
P_NOWAIT = 1
P_OVERLAY = 2
P_NOWAITO = 3
P_DETACH = 4

# Real CPython os.*_OK values. X_OK has no Windows equivalent (there's no
# per-file executable permission bit), so access() treats it as F_OK, same as
# CPython's own Windows implementation.
F_OK = 0
R_OK = 4
W_OK = 2
X_OK = 1

_SW_SHOWNORMAL = 1
_O_BINARY = 0x8000
_HANDLE_FLAG_INHERIT = 0x1

_errno_buf = array.array("i", [0])


def get_errno():
    _get_errno(uctypes.addressof(_errno_buf))
    return _errno_buf[0]


def check_error(ret):
    # Every CRT call bound above returns -1 and sets errno on failure.
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


def spawnl(mode, path, *args):
    return spawnv(mode, path, args)


def access(path, mode):
    return _waccess(wstr(path), mode & (R_OK | W_OK)) == 0


def getpid():
    return _getpid()


def startfile(path, operation="open"):
    r = _ShellExecuteW(0, wstr(operation), wstr(path), 0, 0, _SW_SHOWNORMAL)
    if r <= 32:
        raise OSError(r)


def pipe():
    fds = array.array("i", [0, 0])
    check_error(_pipe(uctypes.addressof(fds), 4096, _O_BINARY))
    return fds[0], fds[1]


def dup(fd):
    return check_error(_dup(fd))


def close(fd):
    return check_error(_close(fd))


def read(fd, n):
    buf = bytearray(n)
    r = check_error(_read(fd, buf, n))
    return bytes(buf[:r])


def write(fd, buf):
    return check_error(_write(fd, buf, len(buf)))


class _PopenFile:
    # Windows CRT file descriptors (from pipe()/dup() above) are private to
    # whichever CRT DLL created them -- ucrtbase.dll here -- unlike POSIX
    # fds, which are real kernel-level descriptors shared process-wide.
    # MicroPython's own builtins.open() goes through a different CRT
    # instance, so it can't be handed one of these; every operation on it
    # has to stay on the ucrtbase read/write/close bound above instead.
    def __init__(self, fd, mode):
        self._fd = fd
        self._binary = "b" in mode

    def read(self, n=-1):
        if n is not None and n >= 0:
            data = read(self._fd, n)
        else:
            chunks = []
            while True:
                chunk = read(self._fd, 4096)
                if not chunk:
                    break
                chunks.append(chunk)
            data = b"".join(chunks)
        return data if self._binary else data.decode()

    def write(self, data):
        if isinstance(data, str):
            data = data.encode()
        return write(self._fd, data)

    def close(self):
        close(self._fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def popen(cmd, mode="r"):
    # There's no fork() on Windows, so unlike unix-ffi/os's popen() this
    # can't rewire a forked child's own descriptors before it execs. Instead
    # it rewires *this* process's std handle, spawns (CreateProcess, invoked
    # by spawnl below, duplicates inheritable handles into the child
    # synchronously, before returning), then immediately restores it -- the
    # child already has its own copy of the pipe end by then.
    i, o = pipe()
    if mode[0] == "w":
        i, o = o, i
    std_fd = 1 if mode[0] == "r" else 0

    # pipe() fds are inheritable by default. Without this, CreateProcess
    # would also hand the spawned child our own end (i), since Windows
    # inherits every inheritable handle open at spawn time, not just
    # whichever fd number happens to sit at std_fd -- leaving the child
    # holding it open and the intended reader/writer never seeing EOF.
    _SetHandleInformation(_get_osfhandle(i), _HANDLE_FLAG_INHERIT, 0)

    comspec = getenv("ComSpec") or (getenv("SystemRoot") + "\\System32\\cmd.exe")
    saved = dup(std_fd)
    close(std_fd)
    dup(o)
    close(o)
    # Same P_NOWAIT handle leak noted on spawnv -- the child is never waited on.
    spawnl(P_NOWAIT, comspec, comspec, "/c", cmd)
    close(std_fd)
    dup(saved)
    close(saved)

    return _PopenFile(i, mode)
