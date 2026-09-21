"""Start-with-Windows registration (FR-1.8).

Writes a per-user ``Run`` entry in ``HKEY_CURRENT_USER``. Per-user rather than
per-machine deliberately: no administrator rights are needed, and one user enabling
it does not impose it on everyone sharing the machine.

Every function reports success rather than raising, because the Settings toggle must
be able to revert itself. A toggle showing "on" while registration silently failed
is a lie the UI would keep displaying (E1-S5 branch 4a).
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["is_registered", "register", "startup_command", "unregister"]

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_ENTRY_NAME = "VocabularyTrainer"


def startup_command() -> str:
    """The command Windows should run at sign-in.

    Two deployment shapes need different handling:

    * **Frozen executable** (PyInstaller and friends): ``sys.frozen`` is set and
      ``sys.executable`` is the app itself, so the path alone is enough.
    * **Running from source**: ``sys.executable`` is the interpreter, so the module
      has to be named explicitly. ``pythonw.exe`` is preferred over ``python.exe``
      when present, since the latter would open a console window at every sign-in.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    interpreter = Path(sys.executable)
    windowless = interpreter.with_name("pythonw.exe")
    if windowless.is_file():
        interpreter = windowless

    return f'"{interpreter}" -m vocabulary_trainer'


def is_registered() -> bool:
    """Whether a startup entry currently exists."""
    key = _open_run_key(write=False)
    if key is None:
        return False

    winreg = _winreg()
    if winreg is None:
        return False

    try:
        with key:
            winreg.QueryValueEx(key, _ENTRY_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def register() -> bool:
    """Create or update the startup entry, reporting success."""
    winreg = _winreg()
    key = _open_run_key(write=True)
    if winreg is None or key is None:
        return False

    try:
        with key:
            winreg.SetValueEx(
                key, _ENTRY_NAME, 0, winreg.REG_SZ, startup_command()
            )
        return True
    except OSError:
        # Group policy can lock this key on managed machines.
        return False


def unregister() -> bool:
    """Remove the startup entry, reporting success.

    An entry that is already absent counts as success: the caller asked for a state,
    and that state has been reached.
    """
    winreg = _winreg()
    key = _open_run_key(write=True)
    if winreg is None or key is None:
        return False

    try:
        with key:
            winreg.DeleteValue(key, _ENTRY_NAME)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


# ----------------------------------------------------------------------


def _winreg():  # type: ignore[no-untyped-def]
    """The ``winreg`` module, or ``None`` off Windows.

    Isolated so the rest of the module reads cleanly and tests can substitute it.
    """
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None
    return winreg


def _open_run_key(*, write: bool):  # type: ignore[no-untyped-def]
    winreg = _winreg()
    if winreg is None:
        return None

    access = winreg.KEY_SET_VALUE if write else winreg.KEY_READ
    try:
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, access)
    except OSError:
        return None
