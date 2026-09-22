from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path


class ElevationError(RuntimeError):
    pass


def is_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def elevation_target() -> tuple[str, str]:
    """Return executable and arguments for a source or frozen restart."""
    if getattr(sys, "frozen", False):
        return sys.executable, subprocess.list2cmdline(sys.argv[1:])
    script = str(Path(sys.argv[0]).resolve())
    return sys.executable, subprocess.list2cmdline([script, *sys.argv[1:]])


def relaunch_as_admin_if_needed() -> bool:
    """Request UAC once. Return True in the old process after relaunch."""
    if os.name != "nt" or is_admin():
        return False
    executable, parameters = elevation_target()
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        parameters,
        os.getcwd(),
        1,
    )
    if result <= 32:
        raise ElevationError(
            "دسترسی Administrator تأیید نشد. بدون این دسترسی امکان تغییر شبکه وجود ندارد."
        )
    return True
