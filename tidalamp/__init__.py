"""tidalamp: a Winamp-flavoured TIDAL client for the terminal."""

import logging

__version__ = "0.1.0"

# Without a handler of our own, logging's last-resort handler would print
# warnings straight to stderr — on top of the TUI. config.setup_logging()
# adds a real file handler when TIDALAMP_DEBUG is set.
logging.getLogger("tidalamp").addHandler(logging.NullHandler())
