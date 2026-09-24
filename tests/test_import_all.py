"""`tools/import_all.py` skips exactly the modules that refuse the other system."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
REFUSES = re.compile(r'^assert sys\.platform == "(\w+)"', re.MULTILINE)


def _import_all():
    spec = importlib.util.spec_from_file_location(
        "import_all", ROOT / "tools/import_all.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_module_that_refuses_the_other_system_is_skipped():
    """backends/windows/job.py asserts win32 on import and was left off the
    list: the CI job that imports every module failed on Linux, on the commit
    that prepared 0.17.0, and only there."""
    refusing = {}
    for path in (ROOT / "tidalamp").rglob("*.py"):
        found = REFUSES.search(path.read_text(encoding="utf-8"))
        if found:
            name = ".".join(path.relative_to(ROOT).with_suffix("").parts)
            refusing[name] = found.group(1)
    assert refusing, "the pattern no longer finds the Windows-only modules"
    only_on = _import_all().ONLY_ON
    for name, platform in refusing.items():
        assert only_on.get(name) == platform, name
