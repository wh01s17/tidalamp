# PyInstaller recipe for the Windows build: `tidalamp.exe` in a folder, zipped
# by release.yml. Versioned rather than generated, so a change to what goes in
# is a reviewed change. See windows.md §10.
#
#   pyinstaller packaging/windows/tidalamp.spec --noconfirm
#
# onedir and not onefile: onefile unpacks everything into %TEMP% on every
# start, a second or more before the player appears, and it is what trips
# antivirus heuristics most. console=True: it is a TUI.
#
# mpv does not go in. It is GPL, weighs ~30 MB and updates on its own; the
# player looks for it as it would anywhere (backends/windows/mpv.py).

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent.parent  # noqa: F821 - defined by PyInstaller

# What the other system's backends import and this one does not have. On
# Windows, D-Bus: not installed there, and the facade never imports it. Built
# on Linux (to try the recipe), `_winapi` and `ctypes.WinDLL`.
if sys.platform == "win32":
    OTHER_SYSTEM = {"tidalamp.backends.linux.mpris"}
    EXCLUDES = ["dbus_fast"]
else:
    OTHER_SYSTEM = {"tidalamp.backends.windows.pipe", "tidalamp.backends.windows.job"}
    EXCLUDES = []

hidden = (
    collect_submodules("tidalamp", filter=lambda name: name not in OTHER_SYSTEM)
    # Textual imports its widgets on first use, and Rich its Unicode width
    # tables per version: invisible to the import scanner, and missed they
    # fail at the first screen, not at build time.
    + collect_submodules("textual")
    + collect_submodules("rich._unicode_data")
    # SMTC's WinRT projections, imported the first time the controls start.
    + (collect_submodules("winrt") if sys.platform == "win32" else [])
)

datas = (
    # The stylesheets, the emblems, the icons: CSS_PATH is read next to the
    # module, so they keep their place inside the package.
    collect_data_files("tidalamp")
    + collect_data_files("textual")
    + copy_metadata("tidalamp")
)

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging/windows/entry.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hidden,
    excludes=EXCLUDES,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="tidalamp",
    console=True,
    icon=str(ROOT / "tidalamp/tidalamp.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="tidalamp")  # noqa: F821
