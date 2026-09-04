# Claude MCPB Opener

Claude Desktop extensions are distributed as [`.mcpb` files](https://github.com/modelcontextprotocol/mcpb).
Claude Desktop itself, however, doesn't register `.mcpb` files with
Explorer: you can't double-click one to install it, and Claude Desktop
doesn't even show up as an option in the "Open with" popup to pick
manually. This app is a simple workaround for that gap: it registers
itself as the `.mcpb` handler and launches Claude Desktop with the file.

## Usage

1. Download `claude-connector-installer.exe` from
   [Releases](https://github.com/andrewleech/claude-connector-installer/releases)
   and double-click it. It installs a stable copy of itself under
   `%LOCALAPPDATA%\ClaudeMcpbOpener\` and registers `.mcpb` as a file type,
   with a confirmation dialog when it's done.
2. With Claude Desktop running, double-click any `.mcpb` file. The first
   time, Windows will show its normal "Open with" picker: choose **Claude
   MCPB Opener** and tick **Always**. After that, `.mcpb` files open
   directly.

No installer, no admin rights, no dependencies: it's a single ~500 KB exe.

## Developer

Built with [picolet](https://github.com/andrewleech/picolet), a
MicroPython-based toolchain for producing single-exe native apps without a
Windows build toolchain. `picolet.toml` declares the app; `picolet build
--target windows-x64` downloads a pre-linked runtime and appends the app's
compiled `src/` tree.

- `src/main.py`: self-install (registry + icon association) and the
  `.mcpb`-launch path (resolves Claude's current install location and spawns
  it with the dropped file).
- `src/os`, `src/winreg`, `src/_wstr.py`, `src/_dll.py`: vendored from
  [micropython-lib's windows-ffi branch](https://github.com/andrewleech/micropython-lib/tree/windows-ffi)
  (not yet wired up via picolet's manifest system, so copied directly).
- `assets/claude.ico`: extracted from Claude Desktop's own `claude.exe` PE
  resources (all resolutions, not just the low-quality default).
- `picolet.toml`'s `console = false`, `company_name`/`file_description`/
  `product_name`, and `version = "git"` all depend on picolet features added
  alongside this app; see picolet's `docs/architecture.md` for the `[app]`
  schema.

Build:

```sh
picolet build --target windows-x64
```
