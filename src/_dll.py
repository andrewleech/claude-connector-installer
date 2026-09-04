"""Shared ffi.open() wrapper used by every windows-ffi package."""

import ffi


def open_dll(name):
    """Open `name`, raising ImportError (rather than OSError) on failure.

    ImportError lets a caller that only needs the DLL for optional
    functionality fall back to a degraded mode with a plain try/except
    ImportError, the same way a missing Python module would.
    """
    try:
        return ffi.open(name)
    except OSError as e:
        raise ImportError("failed to open {!r}: {}".format(name, e))
