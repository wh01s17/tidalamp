"""Windows: a named pipe to mpv, winget/scoop/choco, AppData, and neutral
stand-ins for what is still to come (SMTC, WASAPI, the Start menu).

Every module here imports on any system except `pipe.py`, which needs the
Windows-only `_winapi`: the stand-ins and the lookups are tested on Linux too.
"""
