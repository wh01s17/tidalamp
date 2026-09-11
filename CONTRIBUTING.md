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

## What has to pass before a commit

```sh
.venv/bin/ruff format .
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/python -m pytest -q --cov
```

All four run in CI. Coverage has a floor of 70%, which is a floor and not a target: it
exists so that a change which empties the tests fails instead of passing quietly.

`tidalamp/mpris.py` is excluded from mypy on purpose: its annotations are D-Bus
signatures (`"b"`, `"a{sv}"`), not Python types, and no checker can read them. In
exchange, that module has contract tests against a real bus in `tests/test_mpris.py`.

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
