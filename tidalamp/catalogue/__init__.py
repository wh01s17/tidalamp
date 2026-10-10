"""The English catalogue, Spanish source -> English.

Every string wrapped in _() must appear in one of these files;
tests/test_i18n.py walks the AST and fails when one does not. They are cut by
area, in the order the strings were added, so a new string goes in the file
of the screen that says it. A key in two of them is a mistake:
`tests/test_i18n.py` checks there is none.
"""

from __future__ import annotations

from . import messages, player, windows

ENGLISH: dict[str, str] = {**player.ENGLISH, **windows.ENGLISH, **messages.ENGLISH}
