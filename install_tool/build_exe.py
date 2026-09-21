"""Build ``Install-VocabularyTrainer.exe`` -- one file to send to somebody.

Run from anywhere (paths derive from this file):

    python install_tool\\build_exe.py

Output: ``install_tool\\Install-VocabularyTrainer.exe``. The recipient
double-clicks it; nothing else is needed on their side.

How it works
------------
1. Build the application wheel fresh from ``src/``, so a stale installer can
   never ship stale code.
2. Generate a multi-resolution ``.ico`` from the character artwork.
3. Freeze ``installer_main.py`` with PyInstaller in one-file mode, bundling the
   wheel and the icon inside the executable via ``--add-data``.

The result is a genuine PE binary, not a renamed script: Windows treats it as an
executable, it carries the app icon, and there is no ``.cmd`` for a mail client
or chat app to mangle in transit.

Build requirements (not needed by the recipient):
  * ``pyinstaller`` -- produces the .exe
  * ``pillow`` -- optional, generates the icon; without it the exe uses the
    default PyInstaller icon and shortcuts fall back to pythonw's
"""

from __future__ import annotations

import io
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = HERE / "installer_main.py"
OUT = HERE / "Install-VocabularyTrainer.exe"
BUILD = HERE / "_build"

ICON_SOURCE = (
    ROOT / "src" / "vocabulary_trainer" / "assets" / "floating_widget" / "mini_ani_idle_web.png"
)
ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]


def run(args: list[str], cwd: Path | None = None) -> None:
    print("  $", " ".join(args))
    subprocess.run(args, check=True, cwd=str(cwd or ROOT))


def build_wheel() -> Path:
    """Build the app wheel fresh, so the installer always carries current code."""
    wheels = BUILD / "wheel"
    wheels.mkdir(parents=True, exist_ok=True)
    run([sys.executable, "-m", "pip", "wheel", str(ROOT), "--no-deps", "-w", str(wheels)])
    found = sorted(wheels.glob("vocab_v2-*.whl"))
    if not found:
        raise SystemExit("build failed: no vocab_v2 wheel was produced")
    return found[-1]


def build_icon() -> Path | None:
    """Multi-resolution .ico from the character artwork.

    Optional: Pillow is a build-time convenience. Without it the exe and its
    shortcuts fall back to default icons, which is cosmetic only.
    """
    if not ICON_SOURCE.is_file():
        print(f"  ! icon source missing ({ICON_SOURCE.name}); using default icons")
        return None
    try:
        from PIL import Image
    except ImportError:
        print("  ! Pillow not installed; using default icons")
        return None

    with Image.open(ICON_SOURCE) as img:
        art = img.convert("RGBA")
        # Square canvas first: .ico frames are square, and letting PIL squash a
        # portrait character into 256x256 would distort it.
        side = max(art.size)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(art, ((side - art.width) // 2, (side - art.height) // 2))
        target = BUILD / "app.ico"
        canvas.save(target, format="ICO", sizes=[(s, s) for s in ICON_SIZES])

    print(f"  icon: {target.stat().st_size:,} bytes from {ICON_SOURCE.name}")
    return target


def render_source(wheel: Path, version: str) -> Path:
    text = SOURCE.read_text(encoding="utf-8")
    text = text.replace("__APP_VERSION__", version).replace("__WHEEL_NAME__", wheel.name)

    leftover = sorted(set(re.findall(r"__[A-Z_]+__", text)) - {"__file__", "__name__", "__main__"})
    if leftover:
        raise SystemExit(f"build failed: unsubstituted placeholders {leftover}")

    target = BUILD / "installer_main.py"
    target.write_text(text, encoding="utf-8")
    return target


def read_version(wheel: Path) -> str:
    match = re.match(r"vocab_v2-([^-]+)-", wheel.name)
    return match.group(1) if match else "2.0.0"


def freeze(source: Path, wheel: Path, icon: Path | None) -> None:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", OUT.stem,
        "--distpath", str(HERE),
        "--workpath", str(BUILD / "pyinstaller"),
        "--specpath", str(BUILD),
        "--noconfirm",
        # ";." puts the file at the root of the bundle, where bundled() looks.
        "--add-data", f"{wheel}{';.'}",
    ]
    if icon:
        args += ["--icon", str(icon), "--add-data", f"{icon}{';.'}"]
    args.append(str(source))
    run(args)


def self_check(expect_version: str) -> None:
    """Confirm the output is a real 64-bit PE executable, not a renamed script."""
    data = OUT.read_bytes()

    if data[:2] != b"MZ":
        raise SystemExit("self-check failed: output is not a PE executable")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise SystemExit("self-check failed: missing PE header")
    machine = struct.unpack_from("<H", data, pe_offset + 4)[0]
    if machine != 0x8664:
        raise SystemExit(f"self-check failed: not x64 (machine=0x{machine:04x})")
    print("  valid 64-bit PE executable")

    # The wheel must actually be inside. PyInstaller compresses the archive, so
    # search for the distribution name rather than expecting a literal filename.
    if b"vocab_v2" not in data:
        raise SystemExit("self-check failed: the app wheel does not appear to be bundled")
    print("  application payload present")

    if expect_version.encode() not in data:
        print(f"  ! version string {expect_version} not found in the binary (compressed?)")


def main() -> int:
    print("Building the Vocabulary Trainer installer (.exe)")

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit(
            "build failed: PyInstaller is not installed.\n"
            '  Install it with:  python -m pip install "pyinstaller>=6.10,<7"'
        ) from None

    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True)

    print("\n[1/5] Building the application wheel")
    wheel = build_wheel()
    version = read_version(wheel)
    print(f"  {wheel.name} ({wheel.stat().st_size:,} bytes), version {version}")

    print("\n[2/5] Generating the icon")
    icon = build_icon()

    print("\n[3/5] Preparing the installer source")
    source = render_source(wheel, version)
    print(f"  {source.name}, version {version} and wheel name substituted")

    print("\n[4/5] Freezing with PyInstaller")
    freeze(source, wheel, icon)

    print("\n[5/5] Checking the finished executable")
    if not OUT.is_file():
        raise SystemExit("build failed: no executable was produced")
    self_check(version)
    size_mb = OUT.stat().st_size / (1024 * 1024)
    print(f"  {OUT}")
    print(f"  {OUT.stat().st_size:,} bytes ({size_mb:.1f} MB)")

    shutil.rmtree(BUILD, ignore_errors=True)
    print("\nDone. Send that one file; the recipient just runs it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
