"""Import every module of tidalamp, the way an install without extras would.

CI runs it in the job that installs no extras: a hard import of something
optional (Pillow, dbus-fast) would break the documented install without any
other job noticing. It walks the subpackages too, and skips only the modules
that need what one system alone has.

    python tools/import_all.py
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

import tidalamp

# Module to the platform it needs: `_winapi` exists only on Windows, and
# dbus-fast is only installed on Linux.
ONLY_ON = {
    "tidalamp.backends.windows.pipe": "win32",
    "tidalamp.backends.linux.mpris": "linux",
}


def main() -> int:
    imported = 0
    for module in pkgutil.walk_packages(tidalamp.__path__, "tidalamp."):
        needs = ONLY_ON.get(module.name)
        if needs is not None and not sys.platform.startswith(needs):
            continue
        importlib.import_module(module.name)
        imported += 1
    print(f"{imported} modules imported")
    return 0


if __name__ == "__main__":
    sys.exit(main())
