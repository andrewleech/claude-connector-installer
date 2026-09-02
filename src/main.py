# claude-mcpb-opener — registers itself as the Windows handler for .mcpb
# files and launches Claude Desktop with the dropped file.
#
# No args: self-install (copy to a stable path, write the HKCU association).
# One arg: resolve Claude's current exe path and spawn it with that arg.

import sys
import os
import json
import ffi
import winreg

from _wstr import from_wstr_bytes

kernel32 = ffi.open("kernel32.dll")
GetModuleFileNameW = kernel32.func("I", "GetModuleFileNameW", "ppI")

STABLE_DIR = os.getenv("LOCALAPPDATA") + "\\ClaudeMcpbOpener"
STABLE_EXE = STABLE_DIR + "\\claude-mcpb-opener.exe"

PROG_ID = "ClaudeMCPBFile"


def current_exe_path():
    buf = bytearray(520)  # MAX_PATH * 2 bytes + slack, UTF-16LE
    n = GetModuleFileNameW(0, buf, 260)
    return from_wstr_bytes(buf, n * 2)


def reg_set_string(subkey, value_name, value):
    full_subkey = "Software\\Classes\\" + subkey
    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, full_subkey)
    try:
        winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, value)
    finally:
        winreg.CloseKey(key)


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
    # Full path rather than a bare "powershell.exe" name: windows-ffi/os only
    # exposes spawnv/spawnl (no PATH-searching spawnvp variant).
    powershell = os.getenv("SystemRoot") + "\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
    os.spawnv(
        os.P_WAIT, powershell,
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
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
    os.spawnv(os.P_NOWAIT, exe, [exe, mcpb_path])
    return 0


def main():
    if len(sys.argv) < 2:
        self_install()
        return 0
    return launch(sys.argv[1])


sys.exit(main())
