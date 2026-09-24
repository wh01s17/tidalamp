"""Tie a child process's life to ours, so it cannot outlive tidalamp.

On Linux, closing the terminal sends SIGHUP to the whole process group and
mpv goes with the app. Windows has no such thing: closing the console sends
CTRL_CLOSE_EVENT to the processes attached to *that* console, and mpv, started
with ``CREATE_NO_WINDOW``, has a hidden console of its own. Python is ended
without running any cleanup and mpv keeps playing, with nothing left to stop
it but the Task Manager. The same goes for a crash or a ``taskkill``.

A job object with ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` is Windows's answer:
the kernel ends every process in the job when the last handle to it closes,
and the one handle is ours, closed by the kernel however we exit. It is never
closed by hand, then: that would kill mpv on the spot.

Only the children we choose go in, not tidalamp itself: a process in a job
passes it on to its own children, and the browser `login` opens must not
close with the app.
"""

from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
from ctypes import wintypes

# `ctypes.windll` exists only on Windows; see pipe.py for why the assert.
assert sys.platform == "win32"

log = logging.getLogger("tidalamp.job")

_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
_kernel32.CreateJobObjectW.restype = wintypes.HANDLE
_kernel32.SetInformationJobObject.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.LPVOID,
    wintypes.DWORD,
]
_kernel32.SetInformationJobObject.restype = wintypes.BOOL
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL

# The one job, made on first use and held until the process ends.
_job: int | None = None


def _make_job() -> int:
    job = _kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not _kernel32.SetInformationJobObject(
        job,
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(limits),
        ctypes.sizeof(limits),
    ):
        error = ctypes.get_last_error()
        _kernel32.CloseHandle(job)
        raise ctypes.WinError(error)
    return job


def tie(proc: subprocess.Popen) -> None:
    """End ``proc`` when tidalamp ends, however it ends.

    A failure is logged and nothing more: the child still works, it just
    may outlive us, which is how it was before this existed. The moment
    between the spawn and this call is unguarded, and it is microseconds.
    """
    global _job
    try:
        if _job is None:
            _job = _make_job()
        handle = _kernel32.OpenProcess(
            _PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, proc.pid
        )
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not _kernel32.AssignProcessToJobObject(_job, handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            _kernel32.CloseHandle(handle)
    except OSError as exc:
        log.warning("no se pudo atar el pid %s a tidalamp: %s", proc.pid, exc)
