# claude-mcpb-opener — registers itself as the Windows handler for .mcpb
# files and launches Claude Desktop with the dropped file.
#
# No args: self-install (copy to a stable path, write the HKCU association).
# One arg: resolve Claude's current exe path and spawn it with that arg.

import sys
import os
import json
import array
import uctypes
import ffi


def _open_dll(name):
    try:
        return ffi.open(name)
    except OSError as e:
        raise ImportError("failed to open {!r}: {}".format(name, e))


kernel32 = _open_dll("kernel32.dll")
ucrtbase = _open_dll("ucrtbase.dll")
advapi32 = _open_dll("advapi32.dll")

GetModuleFileNameW = kernel32.func("I", "GetModuleFileNameW", "ppI")

_wspawnv = ucrtbase.func("l", "_wspawnv", "ipp")
_wspawnvp = ucrtbase.func("l", "_wspawnvp", "ipp")

RegCreateKeyExW = advapi32.func("i", "RegCreateKeyExW", "ppIpIIppp")
RegSetValueExW = advapi32.func("i", "RegSetValueExW", "ppIIpI")
RegCloseKey = advapi32.func("i", "RegCloseKey", "p")

HKEY_CURRENT_USER = 0x80000001
KEY_WRITE = 0x20006
REG_SZ = 1
_P_WAIT = 0
_P_NOWAIT = 1

STABLE_DIR = os.getenv("LOCALAPPDATA") + "\\ClaudeMcpbOpener"
STABLE_EXE = STABLE_DIR + "\\claude-mcpb-opener.exe"


def _wstr(s):
    # NUL-terminated UTF-16LE buffer; kept alive by the caller for the
    # lifetime of any Win32 call that holds its address.
    #
    # bytes.encode("utf-16-le") is a CPython codec name this MicroPython
    # build doesn't actually implement (it silently mis-encodes rather than
    # raising) -- encode by hand instead. BMP-only; fine for Windows paths.
    out = bytearray(2 * len(s) + 2)
    for i, ch in enumerate(s):
        code = ord(ch)
        out[2 * i] = code & 0xFF
        out[2 * i + 1] = (code >> 8) & 0xFF
    return out


def _from_wstr(buf, nchars):
    # Inverse of _wstr, for reading fixed-width UTF-16LE Win32 out-buffers.
    # Same "utf-16-le" codec caveat applies to .decode().
    return "".join(
        chr(buf[2 * i] | (buf[2 * i + 1] << 8)) for i in range(nchars)
    )


def _argv(args):
    bufs = [_wstr(a) for a in args]
    ptrs = array.array("P", [uctypes.addressof(b) for b in bufs] + [0])
    return bufs, ptrs  # both must outlive the spawn call


def spawn(mode, cmd, args, use_path=False):
    bufs, ptrs = _argv(args)
    cmd_buf = _wstr(cmd)
    fn = _wspawnvp if use_path else _wspawnv
    return fn(mode, uctypes.addressof(cmd_buf), uctypes.addressof(ptrs))


def current_exe_path():
    buf = bytearray(520)  # MAX_PATH * 2 bytes + slack, UTF-16LE
    n = GetModuleFileNameW(0, uctypes.addressof(buf), 260)
    return _from_wstr(buf, n)


def reg_set_string(subkey, value_name, value):
    hkey = array.array("P", [0])
    disp = array.array("I", [0])
    full_subkey = "Software\\Classes\\" + subkey
    rc = RegCreateKeyExW(
        HKEY_CURRENT_USER, uctypes.addressof(_wstr(full_subkey)), 0, 0, 0,
        KEY_WRITE, 0, uctypes.addressof(hkey), uctypes.addressof(disp),
    )
    if rc != 0:
        raise OSError("RegCreateKeyExW failed for {!r}: {}".format(subkey, rc))
    try:
        data = _wstr(value)
        name_buf = uctypes.addressof(_wstr(value_name)) if value_name else 0
        rc = RegSetValueExW(
            hkey[0], name_buf, 0, REG_SZ, uctypes.addressof(data), len(data),
        )
        if rc != 0:
            raise OSError("RegSetValueExW failed for {!r}: {}".format(subkey, rc))
    finally:
        RegCloseKey(hkey[0])


PROG_ID = "ClaudeMCPBFile"


def self_install():
    src = current_exe_path()
    if src.lower() != STABLE_EXE.lower():
        try:
            os.mkdir(STABLE_DIR)
        except OSError:
            pass  # already exists
        with open(src, "rb") as f:
            data = f.read()
        with open(STABLE_EXE, "wb") as f:
            f.write(data)

    reg_set_string(".mcpb", None, PROG_ID)
    reg_set_string(
        PROG_ID + "\\shell\\open\\command",
        None,
        '"{}" "%1"'.format(STABLE_EXE),
    )
    reg_set_string(PROG_ID + "\\DefaultIcon", None, "{},0".format(STABLE_EXE))
    print("Registered .mcpb -> {}".format(STABLE_EXE))


_FIND_CLAUDE_PS = (
    "$p = Get-Process claude -ErrorAction SilentlyContinue |"
    " Select-Object -First 1 -ExpandProperty Path;"
    " if (-not $p) {"
    "   $pkg = Get-AppxPackage -Name '*Claude*' | Select-Object -First 1;"
    "   if ($pkg) { $p = Join-Path $pkg.InstallLocation 'app\\claude.exe' }"
    " };"
    " @{ path = $p } | ConvertTo-Json -Compress |"
    " Set-Content -Path '%s' -Encoding utf8"
)


def find_claude_exe():
    tmp = os.getenv("TEMP") + "\\claude_mcpb_lookup.json"
    try:
        os.unlink(tmp)
    except OSError:
        pass
    script = _FIND_CLAUDE_PS % tmp
    spawn(
        _P_WAIT, "powershell.exe",
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        use_path=True,
    )
    try:
        with open(tmp, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    try:
        os.unlink(tmp)
    except OSError:
        pass
    if raw[:3] == b"\xef\xbb\xbf":  # Set-Content -Encoding utf8 writes a BOM
        raw = raw[3:]
    data = raw.decode("utf-8")
    if not data.strip():
        return None
    return json.loads(data).get("path")


def launch(mcpb_path):
    exe = find_claude_exe()
    if not exe:
        print("claude.exe not found (not running, and no AppX package matched)")
        return 1
    spawn(_P_NOWAIT, exe, [exe, mcpb_path])
    return 0


def main():
    if len(sys.argv) < 2:
        self_install()
        return 0
    return launch(sys.argv[1])


sys.exit(main())
