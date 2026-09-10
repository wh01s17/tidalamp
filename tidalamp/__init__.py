"""tidalamp: a TIDAL client for the terminal, with a retro player interface.

Copyright (C) 2026 wh01s17.

Free software under the GNU General Public License, version 3 or later; see
the LICENSE file. No warranty of any kind. Not affiliated with TIDAL, Aspiro,
or the Winamp trademark holders.
"""

import logging

__version__ = "0.5.0"

# Without a handler of our own, logging's last-resort handler would print
# warnings straight to stderr — on top of the TUI. config.setup_logging()
# adds a real file handler when TIDALAMP_DEBUG is set.
logging.getLogger("tidalamp").addHandler(logging.NullHandler())
