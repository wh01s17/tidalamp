"""What each operating system does its own way, one package per system.

`tidalamp.audio`, `tidalamp.mpris`, `tidalamp.desktop` and `tidalamp.distro`
are facades: each picks its backend here with a literal `sys.platform` test,
the only form mypy understands, and re-exports its public names. The app and
the screens import the facade and never a backend.

A facade holds references, not the code: a test that patches a backend's
internals (`_run`, `RATES_FILE`, `MARKER`) patches the backend module, because
patching the facade would not reach the functions that read them.
"""
