"""Hosting the mockup-derived HTML inside a native window.

One shared host for both the Practice and Settings windows, since they differ only in
which page they load and which bridge they expose. Splitting them would duplicate the
channel setup, the token injection, and the asset staging.

Three details are doing real work here:

* **``QWebChannel`` registers the bridge under the name ``backend``**, which is what
  ``bridge-client.js`` looks up. That name is the whole contract between the two
  layers.
* **Design tokens are injected at load time** rather than written into a CSS file, so
  the page provably renders with the same values as the Qt widget layer.
* **Assets are staged into a writable directory on first use.** ``qwebchannel.js``
  ships inside the Qt installation and the page needs it alongside its own files, so
  they are gathered into one directory that ``file:`` URLs can resolve.

Nothing is served over HTTP. Content is loaded from local files inside the
application's own window, so the product's "no web server, no browser" constraint
holds.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from vocabulary_trainer import APP_NAME
from vocabulary_trainer.ui.theme import as_css_variables

__all__ = ["WebWindow", "assets_dir", "stage_assets"]

_staged_dir: Path | None = None


def assets_dir() -> Path:
    """The packaged HTML, CSS and JS directory."""
    return Path(__file__).resolve().parent / "assets"


def stage_assets() -> Path:
    """Gather page assets and Qt's ``qwebchannel.js`` into one loadable directory.

    ``qwebchannel.js`` lives inside the Qt installation, which may be read-only, so the
    page's own files are copied next to it in a temporary directory instead. Done once
    per process and reused.
    """
    global _staged_dir
    if _staged_dir is not None and _staged_dir.is_dir():
        return _staged_dir

    target = Path(tempfile.mkdtemp(prefix="vocabulary-trainer-ui-"))
    source = assets_dir()

    for item in source.iterdir():
        if item.is_file():
            shutil.copy2(item, target / item.name)

    # Bundle the fonts so @font-face resolves without a network request (NFR-UI-02).
    fonts_source = source.parent.parent.parent / "assets" / "fonts"
    if fonts_source.is_dir():
        fonts_target = target / "fonts"
        fonts_target.mkdir(exist_ok=True)
        for font in fonts_source.glob("*.ttf"):
            shutil.copy2(font, fonts_target / font.name)

    _write_qwebchannel_js(target)

    _staged_dir = target
    return target


def _write_qwebchannel_js(target: Path) -> None:
    """Extract Qt's ``qwebchannel.js`` beside the page.

    The file does **not** exist on disk anywhere in the PySide6 installation -- it is
    compiled into Qt's ``qrc`` resource system and only becomes reachable once
    ``QtWebChannel`` has been imported. Searching the filesystem for it therefore always
    fails, which is exactly how an earlier version of this function silently fell back to
    writing a stub and left every bridge call reporting "backend is not available".

    Raises when the resource cannot be read: without this script the page loads but is
    permanently disconnected from Python, and a visible startup failure is far more
    diagnosable than a window whose every control quietly does nothing.
    """
    destination = target / "qwebchannel.js"

    # Importing QtWebChannel is what registers the :/qtwebchannel/ resource prefix.
    import PySide6.QtWebChannel  # noqa: F401
    from PySide6.QtCore import QFile, QIODevice

    resource = QFile(":/qtwebchannel/qwebchannel.js")
    if not resource.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError(
            "Qt's qwebchannel.js resource could not be read "
            "(:/qtwebchannel/qwebchannel.js). The Practice and Settings windows "
            "cannot communicate with the application without it."
        )

    try:
        payload = bytes(resource.readAll().data())
    finally:
        resource.close()

    if not payload:
        raise RuntimeError("Qt's qwebchannel.js resource was empty.")

    destination.write_bytes(payload)


class WebWindow(QMainWindow):
    """A native window rendering one of the mockup-derived pages."""

    def __init__(
        self,
        page: str,
        bridge: QObject,
        title_suffix: str,
        width: int = 900,
        height: int = 640,
    ) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} \u2014 {title_suffix}")
        self.resize(width, height)

        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)

        # Keep a reference: QWebChannel does not own the objects it publishes, and a
        # garbage-collected bridge would make every call from JavaScript fail.
        self._bridge = bridge
        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject("backend", bridge)
        self._view.page().setWebChannel(self._channel)

        self._view.loadFinished.connect(self._inject_theme)

        staged = stage_assets()
        self._view.setUrl(QUrl.fromLocalFile(str(staged / page)))

    def _inject_theme(self, ok: bool) -> None:
        """Push the shared design tokens into the page's empty ``<style>`` block."""
        if not ok:
            return
        css = as_css_variables().replace("\\", "\\\\").replace("`", "\\`")
        self._view.page().runJavaScript(
            f"""
            (function () {{
                var node = document.getElementById('theme-tokens');
                if (node) {{ node.textContent = `{css}`; }}
            }})();
            """
        )

    def reload_page(self) -> None:
        """Re-render, e.g. after the workbook changed on disk."""
        self._view.reload()

    def page(self):  # type: ignore[no-untyped-def]
        """The underlying ``QWebEnginePage``.

        Exposed so a caller can run JavaScript against the loaded document -- which is the
        only way to verify that the page really reached Python, rather than rendering
        correctly while silently disconnected.
        """
        return self._view.page()
