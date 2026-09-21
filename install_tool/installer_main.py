"""Vocabulary Trainer installer -- the program that runs inside the .exe.

Not run directly from the source tree. ``build_exe.py`` freezes this module with
PyInstaller into ``Install-VocabularyTrainer.exe``, bundling the application
wheel and the shortcut icon alongside it.

Why Python rather than the previous PowerShell script: the .exe needs a real
program inside it, and PowerShell 5.1's handling of native command lines caused
three separate bugs in the earlier version (see install_tool/README.md). Python
has no equivalent quoting or stderr traps -- ``subprocess`` takes an argument
list, and a non-zero exit code is the only failure signal.

What it does, in order:
  1. Sanity-check Windows, architecture, and that no copy is running.
  2. Find Python 3.12+, or offer to install it from python.org (per-user).
  3. Create a private virtual environment under %LocalAppData%.
  4. pip install the bundled wheel and its dependencies into that venv.
  5. Verify every component imports, including QtWebEngine.
  6. Write Start Menu and desktop shortcuts, an uninstaller, and an Apps entry.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
import winreg
from pathlib import Path

APP_NAME = "Vocabulary Trainer"
APP_VERSION = "__APP_VERSION__"
WHEEL_NAME = "__WHEEL_NAME__"
PY_FALLBACK = "3.12.10"
MIN_PYTHON = (3, 12)

INSTALL_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "VocabularyTrainer"
RUNTIME_DIR = INSTALL_ROOT / "runtime"
VENV_PY = RUNTIME_DIR / "Scripts" / "python.exe"
VENV_PYW = RUNTIME_DIR / "Scripts" / "pythonw.exe"
ICON_PATH = INSTALL_ROOT / "app.ico"
UNINSTALL_CMD = INSTALL_ROOT / "uninstall.cmd"
USER_DATA = Path(os.environ.get("APPDATA", Path.home())) / "VocabularyTrainer"
REG_UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\VocabularyTrainerV3"

# Hide subprocess console windows. The installer has its own console; a pip or
# venv call flashing up a second black window looks like a crash.
_NO_WINDOW = 0x08000000


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------

class Colour:
    """ANSI colours, disabled if the terminal cannot render them."""

    enabled = True
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    GREY = "\033[90m"
    RESET = "\033[0m"

    @classmethod
    def wrap(cls, text: str, colour: str) -> str:
        return f"{colour}{text}{cls.RESET}" if cls.enabled else text


def enable_ansi() -> None:
    """Turn on virtual-terminal processing, or disable colour if unavailable."""
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            Colour.enabled = False
            return
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        Colour.enabled = False


def step(text: str) -> None:
    print()
    print(Colour.wrap(f"==> {text}", Colour.CYAN))


def info(text: str) -> None:
    print(Colour.wrap(f"    {text}", Colour.GREY))


def good(text: str) -> None:
    print(Colour.wrap(f"    {text}", Colour.GREEN))


def warn(text: str) -> None:
    print(Colour.wrap(f"    {text}", Colour.YELLOW))


class InstallError(Exception):
    """A failure worth explaining to the user, with hints on what to try."""

    def __init__(self, message: str, hints: list[str] | None = None) -> None:
        super().__init__(message)
        self.hints = hints or []


def ask(prompt: str, default_yes: bool = True) -> bool:
    """Yes/no prompt. Treats a closed stdin as accepting the default."""
    suffix = "[Y/n]" if default_yes else "[y/N]"
    try:
        answer = input(f"    {prompt} {suffix}: ").strip().lower()
    except EOFError:
        return default_yes
    if not answer:
        return default_yes
    return answer.startswith("y")


# ---------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------

def bundled(name: str) -> Path:
    """A file bundled into the .exe by PyInstaller (or beside this script)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


# ---------------------------------------------------------------------------
# 1. Environment checks
# ---------------------------------------------------------------------------

def check_machine() -> None:
    step("Checking this machine")

    if os.name != "nt":
        raise InstallError("this application is Windows only.")
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise InstallError(
            "a 64-bit version of Windows is required.",
            ["The Qt packages this app needs are only published for x64."],
        )
    good(f"Windows {platform.version()}, 64-bit.")


def running_app_pids() -> list[int]:
    """PIDs of any running copy of the app.

    Matches the command line, not just the executable path: a venv's pythonw.exe
    re-execs the base interpreter, so the process actually running the app lives
    outside the install folder while still holding its DLLs open. Path-only
    matching finds the redirector and misses the real one, and pip then fails
    halfway through replacing files that are still in use.
    """
    # Two conditions, both required:
    #
    #   Name like 'python*'  -- the PowerShell process running this very query has
    #                           "vocabulary_trainer" in its own command line, so a
    #                           string match alone always finds itself and reports a
    #                           phantom running app. That made the installer refuse
    #                           to proceed on a machine with nothing running at all.
    #   CommandLine match    -- a venv's pythonw.exe re-execs the base interpreter,
    #                           so the process actually running the app lives outside
    #                           the install folder while still holding its DLLs open.
    #                           Matching on path alone finds the redirector and
    #                           misses the real one.
    query = (
        "Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -like 'python*' -and $_.CommandLine "
        "-and $_.CommandLine -like '*vocabulary_trainer*' } | "
        "ForEach-Object { $_.ProcessId }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", query],
            capture_output=True, text=True, timeout=60, creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    pids = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit() and int(line) != os.getpid():
            pids.append(int(line))
    return pids


def close_running_app() -> None:
    pids = running_app_pids()
    if not pids:
        return

    warn(f"{APP_NAME} is currently running ({len(pids)} process(es)).")
    if not ask("Close it now and continue?"):
        raise InstallError(
            "the application must be closed before it can be replaced.",
            ["Quit it from the floating character's menu or the tray icon, then re-run."],
        )

    for pid in pids:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F", "/T"],
            capture_output=True, creationflags=_NO_WINDOW,
        )
    time.sleep(2)
    good("Closed.")


# ---------------------------------------------------------------------------
# 2. Python
# ---------------------------------------------------------------------------

PROBE = textwrap.dedent(
    """
    import sys
    print(sys.version_info[0])
    print(sys.version_info[1])
    print(sys.maxsize > 2**32)
    print(sys.executable)
    """
).strip()


def probe_python(exe: str, pre_args: list[str], probe_file: Path) -> dict | None:
    """Run the probe under a candidate interpreter, or None if unsuitable."""
    try:
        result = subprocess.run(
            [exe, *pre_args, str(probe_file)],
            capture_output=True, text=True, timeout=60, creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 4:
        return None

    try:
        version = (int(lines[0]), int(lines[1]))
    except ValueError:
        return None
    if version < MIN_PYTHON:
        return None
    # 32-bit Python cannot load the 64-bit-only PySide6 wheels.
    if lines[2] != "True":
        return None

    return {"exe": exe, "pre_args": pre_args, "version": version, "real": lines[3]}


def find_python(work: Path) -> dict | None:
    probe_file = work / "probe.py"
    probe_file.write_text(PROBE, encoding="ascii")

    candidates: list[tuple[str, list[str]]] = [
        ("py", ["-3.14"]), ("py", ["-3.13"]), ("py", ["-3.12"]), ("py", ["-3"]),
        ("python", []), ("python3", []),
    ]
    for root in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")):
        if not root:
            continue
        programs = Path(root) / "Programs" / "Python"
        if programs.is_dir():
            for folder in sorted(programs.iterdir(), reverse=True):
                candidates.append((str(folder / "python.exe"), []))
        for name in ("Python314", "Python313", "Python312"):
            candidates.append((str(Path(root) / name / "python.exe"), []))

    for exe, pre_args in candidates:
        if ("\\" in exe or "/" in exe) and not Path(exe).is_file():
            continue
        found = probe_python(exe, pre_args, probe_file)
        if found:
            return found
    return None


def install_python(work: Path) -> dict:
    warn("No suitable Python found.")
    info(f"This installer can download Python {PY_FALLBACK} from python.org and")
    info("install it for your user account only (it will not change your PATH).")
    if not ask("Download and install it now?"):
        raise InstallError(
            "Python 3.12 or newer is required.",
            ["Install it from https://www.python.org/downloads/windows/ and re-run."],
        )

    url = f"https://www.python.org/ftp/python/{PY_FALLBACK}/python-{PY_FALLBACK}-amd64.exe"
    target = work / f"python-{PY_FALLBACK}-amd64.exe"
    info(f"Downloading {url}")
    try:
        with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as out:
            shutil.copyfileobj(response, out)
    except Exception as exc:
        raise InstallError(
            f"the Python download failed ({exc}).",
            ["Check your internet connection or proxy, then re-run.",
             "Or install Python 3.12+ manually from python.org."],
        ) from exc

    info("Installing Python (this takes a minute, no window will appear)...")
    # InstallAllUsers=0 plus InstallLauncherAllUsers=0 keeps everything inside this
    # user's profile, which is what avoids an admin prompt. PrependPath=0 because
    # the app runs from its own venv and has no business editing PATH.
    result = subprocess.run([
        str(target), "/quiet", "InstallAllUsers=0", "InstallLauncherAllUsers=0",
        "PrependPath=0", "Include_launcher=1", "Include_pip=1", "Include_test=0",
        "AssociateFiles=0", "Shortcuts=0",
    ])
    if result.returncode not in (0, 3010):
        raise InstallError(
            f"the Python installer exited with code {result.returncode}.",
            ["Install Python 3.12+ manually from python.org, then re-run."],
        )

    found = find_python(work)
    if not found:
        raise InstallError(
            "Python was installed but could not be located afterwards.",
            ["Sign out and back in (or reboot), then re-run this installer."],
        )
    return found


# ---------------------------------------------------------------------------
# 3-5. Environment, install, verify
# ---------------------------------------------------------------------------

def create_venv(python: dict) -> None:
    step("Preparing a private Python environment")
    info("Kept separate from any Python you use for your own work, so this")
    info("app can never disturb your other projects.")

    if VENV_PY.is_file():
        with tempfile.TemporaryDirectory() as probe_dir:
            probe_file = Path(probe_dir) / "probe.py"
            probe_file.write_text(PROBE, encoding="ascii")
            if probe_python(str(VENV_PY), [], probe_file):
                good("Reusing the environment from a previous install.")
                return
        warn("The previous environment is unusable; rebuilding it.")
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)

    INSTALL_ROOT.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [python["exe"], *python["pre_args"], "-m", "venv", str(RUNTIME_DIR)],
        capture_output=True, text=True, creationflags=_NO_WINDOW,
    )
    if result.returncode != 0 or not VENV_PY.is_file():
        raise InstallError(
            "the Python environment could not be created.",
            ["If this Python came from the Microsoft Store, install it from",
             "python.org instead -- Store builds restrict venv creation.",
             (result.stderr or "").strip()[:300]],
        )
    good("Created.")


def pip_install(wheel: Path) -> None:
    step("Installing the application and its dependencies")
    info("Downloading Qt and friends from PyPI. First run is the slow one;")
    info("later re-installs reuse the download cache.")
    print()

    base = [str(VENV_PY), "-m", "pip", "install", "--disable-pip-version-check", "--no-input"]

    subprocess.run([*base, "--quiet", "--upgrade", "pip", "setuptools"],
                   capture_output=True, text=True, creationflags=_NO_WINDOW)

    # Drop any previous copy first. Without this, re-installing the same version
    # number makes pip skip the wheel ("already installed with the same version"),
    # which both leaves the old code in place and prints a line that reads like a
    # failure. On a fresh venv there is nothing to remove and pip says so -- that
    # is expected, hence the ignored result.
    subprocess.run(
        [str(VENV_PY), "-m", "pip", "uninstall", "--disable-pip-version-check",
         "--quiet", "-y", "vocab-v2"],
        capture_output=True, text=True, creationflags=_NO_WINDOW,
    )

    result = subprocess.run([*base, str(wheel)], text=True)
    if result.returncode != 0:
        raise InstallError(
            "the application or its dependencies failed to install.",
            ["This is nearly always a network, proxy or firewall problem.",
             "If you use a proxy, set HTTPS_PROXY in your environment and re-run."],
        )


VERIFY = textwrap.dedent(
    """
    import vocabulary_trainer
    import openpyxl, httpx
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from vocabulary_trainer.app import main
    print("ok")
    """
).strip()


def verify_install(work: Path) -> None:
    step("Verifying the install")
    check_file = work / "verify.py"
    check_file.write_text(VERIFY, encoding="ascii")

    result = subprocess.run(
        [str(VENV_PY), str(check_file)],
        capture_output=True, text=True, creationflags=_NO_WINDOW,
    )
    if result.returncode != 0 or "ok" not in result.stdout:
        detail = ((result.stderr or "") + (result.stdout or "")).strip()
        print(Colour.wrap(detail[-1200:], Colour.GREY))
        raise InstallError(
            "the installed application could not be loaded.",
            ["If the error above mentions a missing DLL, install the Microsoft",
             "Visual C++ 2015-2022 Redistributable (x64) from microsoft.com."],
        )
    good("All components load correctly.")


# ---------------------------------------------------------------------------
# 6. Shortcuts, uninstaller, registry
# ---------------------------------------------------------------------------

UNINSTALLER = textwrap.dedent(
    r"""
    @echo off
    rem Uninstaller for {app_name} {version}.
    rem Removes the application. Your words and settings are deliberately kept.
    setlocal enableextensions
    cd /d "%TEMP%"

    rem Still inside the folder about to be deleted? Relocate and hand over: cmd
    rem reads a batch file as it executes, so deleting it mid-run aborts with
    rem "The system cannot find the path specified".
    echo "%~dp0" | findstr /i /c:"{install_root}" >nul
    if errorlevel 1 goto :run
    set "COPY=%TEMP%\vt3-uninstall-%RANDOM%%RANDOM%.cmd"
    copy /y "%~f0" "%COPY%" >nul
    if errorlevel 1 (
      echo Could not prepare the uninstaller in %TEMP%.
      pause
      exit /b 1
    )
    start "" cmd /c ""%COPY%""
    exit /b 0

    :run
    echo.
    echo Removing {app_name}...
    rem Requires Name like 'python*' as well as the command-line match. Without the
    rem name test this PowerShell process matches itself (its own command line
    rem contains the search string) and kills its own shell mid-uninstall. The
    rem command-line test is still needed because a venv's pythonw.exe re-execs the
    rem base interpreter, so the process really running the app sits outside this
    rem folder while still holding its DLLs open.
    powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach($p in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)){{ if($p.Name -like 'python*' -and $p.CommandLine -and $p.CommandLine -like '*vocabulary_trainer*'){{ Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }} }}"
    rem ping, not timeout: timeout fails outright when stdin is redirected.
    ping -n 3 127.0.0.1 >nul 2>nul
    del /f /q "{start_menu_lnk}" >nul 2>nul
    del /f /q "{desktop_lnk}" >nul 2>nul
    reg delete "HKCU\{reg_key}" /f >nul 2>nul
    rmdir /s /q "{install_root}" >nul 2>nul
    if exist "{install_root}" (
      echo.
      echo Some files could not be removed -- something there is still open.
      echo Close {app_name}, sign out and back in, then delete this folder:
      echo   {install_root}
    ) else (
      echo Removed.
    )
    echo.
    echo Your vocabulary workbook and settings were kept at:
    echo   {user_data}
    echo Delete that folder yourself if you want them gone too.
    echo.
    pause
    (goto) 2>nul & del /f /q "%~f0"
    """
).strip()


def start_menu_path() -> Path:
    return (
        Path(os.environ.get("APPDATA", Path.home()))
        / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        / f"{APP_NAME}.lnk"
    )


def desktop_path() -> Path:
    return Path(os.path.join(os.path.expanduser("~"), "Desktop")) / f"{APP_NAME}.lnk"


def write_shortcut(target: Path) -> bool:
    """Create a .lnk via PowerShell's WScript.Shell.

    pythonw.exe rather than the vocab-v2 console script: the app is a floating
    widget with no main window, and a console script would leave a black cmd
    window on the taskbar for as long as it runs.
    """
    script = textwrap.dedent(f"""
        $shell = New-Object -ComObject WScript.Shell
        $lnk = $shell.CreateShortcut({str(target)!r})
        $lnk.TargetPath = {str(VENV_PYW)!r}
        $lnk.Arguments = '-m vocabulary_trainer'
        $lnk.WorkingDirectory = {str(INSTALL_ROOT)!r}
        $lnk.Description = {f"{APP_NAME} {APP_VERSION}"!r}
        $lnk.IconLocation = {str(ICON_PATH)!r}
        $lnk.Save()
    """).strip()

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=90, creationflags=_NO_WINDOW,
        )
        return result.returncode == 0 and target.is_file()
    except (OSError, subprocess.SubprocessError):
        return False


def write_uninstaller() -> None:
    UNINSTALL_CMD.write_text(
        UNINSTALLER.format(
            app_name=APP_NAME,
            version=APP_VERSION,
            install_root=str(INSTALL_ROOT),
            start_menu_lnk=str(start_menu_path()),
            desktop_lnk=str(desktop_path()),
            reg_key=REG_UNINSTALL,
            user_data=str(USER_DATA),
        )
        + "\r\n",
        encoding="ascii",
    )


def write_registry() -> None:
    """Register in Settings > Apps so the app uninstalls the normal way."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_UNINSTALL) as key:
        for name, value in [
            ("DisplayName", APP_NAME),
            ("DisplayVersion", APP_VERSION),
            ("Publisher", APP_NAME),
            ("InstallLocation", str(INSTALL_ROOT)),
            ("DisplayIcon", str(ICON_PATH)),
            ("UninstallString", f'cmd.exe /c "{UNINSTALL_CMD}"'),
        ]:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name, value in [("NoModify", 1), ("NoRepair", 1)]:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)


def create_shortcuts() -> None:
    step("Creating shortcuts")

    icon = bundled("app.ico")
    if icon.is_file():
        shutil.copyfile(icon, ICON_PATH)

    write_uninstaller()

    for target in (start_menu_path(), desktop_path()):
        if write_shortcut(target):
            good(f"Shortcut: {target}")
        else:
            warn(f"Could not create {target}")

    write_registry()
    good("Listed in Settings > Apps > Installed apps.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def banner() -> None:
    print()
    print(f"  {APP_NAME} {APP_VERSION}")
    print(Colour.wrap("  " + "-" * 58, Colour.GREY))
    for line in [
        "Installs for the current user only. No administrator rights,",
        "no changes outside your own profile.",
        f"Location: {INSTALL_ROOT}",
        "An internet connection is needed to fetch Qt and the other",
        "Python dependencies (roughly 150 MB on a first install).",
    ]:
        print(Colour.wrap(f"  {line}", Colour.GREY))


def finish() -> None:
    print()
    print(Colour.wrap("  " + "-" * 58, Colour.GREY))
    print(Colour.wrap(f"  {APP_NAME} is installed.", Colour.GREEN))
    print()
    for line in [
        "There is no main window, by design. When it starts you get a",
        "floating character near the bottom-right of your screen and an",
        "icon in the notification area. Click either one for the menu.",
        "",
        f"Your words live in {USER_DATA / 'master.xlsx'}",
        "and can be opened in Excel at any time.",
        "",
        "To remove it later: Settings > Apps, or run",
        f"{UNINSTALL_CMD}",
    ]:
        print(Colour.wrap(f"  {line}", Colour.GREY) if line else "")

    print()
    if ask("Start it now?"):
        subprocess.Popen(
            [str(VENV_PYW), "-m", "vocabulary_trainer"],
            cwd=str(INSTALL_ROOT), creationflags=0x00000008,  # DETACHED_PROCESS
        )
        print()
        print(Colour.wrap("  Started. Look for the character near the bottom-right.", Colour.GREEN))
        print()


def main() -> int:
    enable_ansi()
    try:
        os.system(f"title {APP_NAME} {APP_VERSION} -- installer")
    except Exception:
        pass

    banner()

    with tempfile.TemporaryDirectory(prefix="vt3-install-") as work_name:
        work = Path(work_name)
        try:
            check_machine()
            close_running_app()

            step("Unpacking the application")
            wheel = bundled(WHEEL_NAME)
            if not wheel.is_file():
                raise InstallError(
                    "the application package is missing from this installer.",
                    ["The file was probably damaged in transit. Ask for a fresh copy."],
                )
            staged = work / WHEEL_NAME
            shutil.copyfile(wheel, staged)
            good(f"Extracted {WHEEL_NAME}.")

            step("Looking for Python 3.12 or newer")
            python = find_python(work) or install_python(work)
            good(f"Using Python {python['version'][0]}.{python['version'][1]} at {python['real']}")

            create_venv(python)
            pip_install(staged)
            verify_install(work)
            create_shortcuts()
            finish()
            return 0

        except InstallError as exc:
            print()
            print(Colour.wrap(f"  Install failed: {exc}", Colour.RED))
            for hint in exc.hints:
                if hint:
                    print(Colour.wrap(f"  - {hint}", Colour.YELLOW))
            print()
            print(Colour.wrap(
                "  Nothing was left half-installed that you need to clean up;",
                Colour.GREY))
            print(Colour.wrap(
                "  re-run this installer once the above is sorted.", Colour.GREY))
            return 1

        except KeyboardInterrupt:
            print()
            print(Colour.wrap("  Cancelled. Nothing was changed.", Colour.YELLOW))
            return 1


if __name__ == "__main__":
    code = main()
    # The .exe is double-clicked, so its console closes the instant this returns.
    # Hold it open long enough to read the outcome.
    try:
        input("Press Enter to close... ")
    except EOFError:
        pass
    sys.exit(code)
