# Contributing

## First, two lines that are not crossed

1. **No DRM.** `stream.py` rejects encrypted manifests rather than decrypting them, and
   no audio is downloaded to disk. Patches that add decryption or download to a file are
   not accepted. This is not an aesthetic preference: it is what keeps the project clear
   of anti-circumvention law.
2. **No embedded credentials.** No API keys, no tokens, no client secrets of our own in
   the repository.

## Setting up

```sh
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

You need `mpv` on the system. `cava` is optional (a real spectrum) and so is
`dbus-daemon` — without it the MPRIS integration skips itself rather than failing.

On Windows the same, with `.venv\Scripts\pip` and `.venv\Scripts\python`. The suite
does not need mpv there either: it runs a fake one over a named pipe. If a test fails
with a `FileNotFoundError` that makes no sense, suspect the 260-character path limit
and enable long paths, or run from a shorter directory.

## What has to pass before a commit

```sh
.venv/bin/ruff format .
.venv/bin/ruff check .
.venv/bin/mypy --platform linux
.venv/bin/mypy --platform win32
.venv/bin/python -m pytest -q --cov
```

All of it runs in CI, the suite on Linux and on Windows. mypy runs once per system
because each pass drops the other's branches: without the second, the Windows code
is never checked from Linux. That is also why platform code tests `sys.platform`
literally and never through a constant of our own, which mypy cannot see through. Coverage has a floor of 70%, which is a floor and not a target: it
exists so that a change which empties the tests fails instead of passing quietly.

`tidalamp/backends/linux/mpris.py` is excluded from mypy on purpose: its annotations are D-Bus
signatures (`"b"`, `"a{sv}"`), not Python types, and no checker can read them. In
exchange, that module has contract tests against a real bus in `tests/test_mpris.py`.

## Linux and Windows

What differs between the two lives in `tidalamp/backends/<system>/`, behind a facade
(`audio`, `mpris`, `desktop`, `distro`) that picks the backend and re-exports its
public names. `tests/test_backend_parity.py` checks that both backends offer the
same names with the same signatures. Patch a backend's internals on the backend
module: the facade only holds references. The plan, with its phases and traps, is
`windows.md`.

A test that only makes sense on one system is marked `@linux_only` or
`@windows_only` (from `conftest.py`) rather than deleted, so that it comes back the
day the other system has it. Do not simulate a write failure with `chmod`: it
protects nothing on Windows or from root. Make the write raise instead.

## How the tests are written here

They do not touch the network, TIDAL, or the user's session bus. There are doubles for
everything needed: `tests/fake_mpv.py` speaks the real IPC, `tests/fake_cava.py` emits
binary frames, and the MPRIS integration starts its own temporary `dbus-daemon`.

When you fix a bug, the test should say **what was breaking**, not only what the
function does. Plenty of the ones in this repository carry the symptom in the name or in
the docstring, and that is deliberate.

## Documentation

The split is by audience, not by preference: what a stranger reads is in English, and
what the maintainer reads is in Spanish.

- `README.md` and `CHANGELOG.md` are the public documentation, in English. So are the
  GitHub release notes.
- `plan.md` is the handover document, in Spanish: what exists, what has been verified
  and **the reasoning behind each decision**. If you make an architectural decision, it
  goes there, with the why. If you lose an afternoon to a trap, it goes in §7, so nobody
  repeats it.
- `next.md` is the queue of committed work for the next version, in Spanish: what goes
  in, why, the traps already known and how it gets checked. **When something there is
  done it is deleted from there**, and its trace goes to `CHANGELOG.md` as the user-
  facing line and to `plan.md` as the detail. A list that collects struck-out entries
  stops saying what is missing.
- `publish.md` is the release procedure, in Spanish: from the version to the tag and the
  AUR. `packaging/README.md` is its summary plus the packaging-specific decisions, also
  in Spanish: it is a companion to `publish.md`, not a door a stranger comes in through.
- This file is in English. Whoever reads it is deciding whether to contribute, and that
  is a stranger by definition.
- `CHANGELOG.md` is updated in the same commit as the change.

## Commit messages

Imperative, and explaining **why**, not only what. If the change comes out of a
measurement, the number goes in the message: that is what lets it be argued with later.
