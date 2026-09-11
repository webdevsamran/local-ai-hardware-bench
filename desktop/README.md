# Desktop app (Tauri)

A native wrapper around the same CLI and the same dashboard. It is deliberately
thin.

## The one design rule

**The GUI shells out to `aihwbench`. It does not reimplement anything.**

A desktop app that measured things its own way would be a second
implementation of the benchmark, and the two would drift — quietly, in the
direction nobody checks, because the GUI is the one people use and the CLI is
the one that has tests. Every button here runs the same command you could type,
and shows you which command it ran.

The frontend is the existing `web/dist` build, unchanged. The dashboard is
already a static site; Tauri serves it locally instead of GitHub Pages.

## What it adds over the CLI

Nothing measurable. It adds discoverability: `aihwbench doctor` in a window,
a run button, and the result opened in the dashboard that already knows how to
render it. That is the whole point — the people who most need to know whether
their laptop can run a model are the least likely to install a Python CLI.

## Building

Needs the Rust toolchain **and** a C++ linker:

- Windows: Visual Studio Build Tools with the "C++ build tools" workload, plus
  WebView2 (present on Windows 11).
- macOS: Xcode command line tools.
- Linux: `webkit2gtk`, `libappindicator3`, `librsvg2`.

```bash
npm --prefix ../web run build    # produce web/dist
cargo tauri build                # from desktop/
```

## Status

**Not built or run on the reference machine.** Rust 1.98.1 is installed there
and `link.exe` fails: the C++ build tools workload is absent, so nothing here
has been compiled. The configuration is checked for validity by
`tests/test_desktop_scaffold.py` — that it parses, that its paths resolve, and
that it points at the real dashboard build — which is not the same as a
compiled binary, and the tests say so rather than implying more.
