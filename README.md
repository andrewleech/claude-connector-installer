# Claude MCPB Opener

Registers `.mcpb` files (Claude Desktop extension bundles) as double-clickable
on Windows, so dropping one onto Claude no longer requires "Open with" every
time.

## Usage

1. Download `claude-connector-installer.exe` and run it once, with no
   arguments. It installs a stable copy of itself under
   `%LOCALAPPDATA%\ClaudeMcpbOpener\` and registers `.mcpb` as a file type —
   a confirmation dialog appears when it's done.
2. With Claude Desktop running, double-click any `.mcpb` file. The first time
   Windows will show its normal "Open with" picker — choose **Claude MCPB
   Opener** and tick **Always**. After that, `.mcpb` files open directly.

No installer, no admin rights, no dependencies — it's a single ~500 KB exe.

## Developer

Built with [picolet](https://github.com/andrewleech/picolet) — a
MicroPython-based toolchain for producing single-exe native apps without a
Windows build toolchain. `picolet.toml` declares the app; `picolet build
--target windows-x64` downloads a pre-linked runtime and appends the app's
compiled `src/` tree.

- `src/main.py` — self-install (registry + icon association) and the
  `.mcpb`-launch path (resolves Claude's current install location and spawns
  it with the dropped file).
- `src/os`, `src/winreg`, `src/_wstr.py`, `src/_dll.py` — vendored from
  [micropython-lib's windows-ffi branch](https://github.com/andrewleech/micropython-lib/tree/windows-ffi)
  (not yet wired up via picolet's manifest system, so copied directly).
- `assets/claude.ico` — extracted from Claude Desktop's own `claude.exe` PE
  resources (all resolutions, not just the low-quality default).
- `picolet.toml`'s `console = false`, `company_name`/`file_description`/
  `product_name`, and `version = "git"` all depend on picolet features added
  alongside this app — see picolet's `docs/architecture.md` for the `[app]`
  schema.

Build:

```sh
picolet build --target windows-x64
```
