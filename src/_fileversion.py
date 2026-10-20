"""Read a PE file's ProductVersion string and order picolet git-derived versions.

Version strings come from picolet's `version = "git"` scheme:
  "0.1.0"                    exactly on a tag
  "0.1.1.dev3+gabc1234"      3 commits past v0.1.0
  "0.0.0.dev12+gabc1234"     no tag reachable
  any of the above + ".dirty"
"""

import array

from _wstr import wstr, from_wstr_bytes


def version_key(text):
    """Sortable key for a version string; None if it can't be parsed.

    A release sorts above any .devN build of the same X.Y.Z (devN builds are
    "next patch" guesses made *before* that release). The +g<sha> and .dirty
    parts carry no ordering, so they're dropped.
    """
    nums = []
    dev = None
    for part in text.split("+", 1)[0].split("."):
        if part.isdigit() and dev is None:
            nums.append(int(part))
        elif part.startswith("dev") and part[3:].isdigit():
            dev = int(part[3:])
        elif part == "dirty":
            pass
        else:
            return None
    if not nums:
        return None
    while len(nums) < 3:
        nums.append(0)
    if dev is None:
        return (tuple(nums), 1, 0)
    return (tuple(nums), 0, dev)


def product_version(path):
    """ProductVersion string from `path`'s version resource, or None."""
    import ffi

    version = ffi.open("version.dll")
    get_size = version.func("I", "GetFileVersionInfoSizeW", "pp")
    get_info = version.func("i", "GetFileVersionInfoW", "pIIp")

    wpath = wstr(path)
    size = get_size(wpath, array.array("I", [0]))
    if not size:
        return None
    buf = bytearray(size)
    if not get_info(wpath, 0, size, buf):
        return None

    # Walk the raw VS_VERSIONINFO blob rather than calling VerQueryValueW:
    # that returns a pointer into our buffer, and there's no way to read
    # through a raw pointer here. A String entry is
    #   WORD wLength, wValueLength, wType; WCHAR szKey[]; pad to DWORD; value
    key = wstr("ProductVersion")
    at = bytes(buf).find(key)
    if at < 0:
        return None
    start = (at + len(key) + 3) & ~3
    end = start
    while end + 1 < size and (buf[end] or buf[end + 1]):
        end += 2
    return from_wstr_bytes(buf[start:end], end - start)
