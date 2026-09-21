"""Tests for staging the web-rendered windows' assets.

These exist because of a real shipped bug. ``qwebchannel.js`` does not exist as a file
anywhere in the PySide6 installation -- it is compiled into Qt's ``qrc`` resource system.
An earlier implementation searched the filesystem for it, always failed, and silently
wrote a stub instead. The windows then rendered perfectly but every control reported
"The application backend is not available", because the page had no way to reach Python.

The lesson these tests encode: a staged asset directory that *looks* complete is not the
same as one that works. So they assert the real Qt script is present, not merely that a
file with the right name exists.

They need a ``QApplication`` because reading a ``qrc`` resource requires Qt to be
initialised, so they are skipped where one cannot be created.
"""

from __future__ import annotations

from pathlib import Path

import pytest

qt_widgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qt_app():
    """A process-wide QApplication, reused across tests.

    Qt permits only one instance per process, so an existing one is adopted rather than
    replaced.
    """
    app = qt_widgets.QApplication.instance() or qt_widgets.QApplication([])
    yield app


@pytest.fixture(scope="module")
def staged(qt_app) -> Path:
    from vocabulary_trainer.ui.web.web_window import stage_assets

    return stage_assets()


class TestQWebChannelScript:
    def test_is_staged(self, staged: Path) -> None:
        assert (staged / "qwebchannel.js").is_file()

    def test_is_the_real_qt_script_not_a_stub(self, staged: Path) -> None:
        """The bug that shipped: a placeholder file passed a name check while leaving
        every window disconnected from Python.

        Identified by Qt's copyright header plus the exported symbol. Deliberately not by
        scanning for phrases like "not found" -- the real script contains that string in
        one of its own error messages, so such a check would fail on a working file.
        """
        content = (staged / "qwebchannel.js").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert "The Qt Company" in content, "staged file is not Qt's qwebchannel.js"
        assert "QWebChannel" in content
        assert "module.exports" in content, "the script does not export QWebChannel"

    def test_defines_the_constructor_the_page_calls(self, staged: Path) -> None:
        """``bridge-client.js`` does ``new QWebChannel(qt.webChannelTransport, ...)``.

        The transport object is injected into the page by Qt at runtime, so it is not a
        string in the library. What the library must supply is the constructor and the
        ``send`` plumbing it uses.
        """
        content = (staged / "qwebchannel.js").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert "QWebChannel" in content
        assert "transport" in content
        assert "send(" in content

    def test_is_substantial(self, staged: Path) -> None:
        """Qt's script is ~16 KB; anything tiny is a placeholder."""
        assert (staged / "qwebchannel.js").stat().st_size > 5000

    def test_resource_is_readable_directly(self, qt_app) -> None:
        """Pins the resource path itself.

        If a future Qt release moves it, this fails with a clear cause rather than
        surfacing as an inert UI.
        """
        import PySide6.QtWebChannel  # noqa: F401
        from PySide6.QtCore import QFile, QIODevice

        resource = QFile(":/qtwebchannel/qwebchannel.js")
        assert resource.open(QIODevice.OpenModeFlag.ReadOnly), (
            "Qt no longer exposes qwebchannel.js at :/qtwebchannel/"
        )
        try:
            assert resource.size() > 5000
        finally:
            resource.close()


class TestPageAssets:
    @pytest.mark.parametrize(
        "filename",
        [
            "practice.html",
            "practice.js",
            "settings.html",
            "settings.js",
            "app.css",
            "bridge-client.js",
        ],
    )
    def test_every_page_asset_is_staged(self, staged: Path, filename: str) -> None:
        assert (staged / filename).is_file(), f"{filename} missing from the staged dir"

    def test_fonts_are_staged(self, staged: Path) -> None:
        """@font-face must resolve locally so the UI needs no network (NFR-UI-02)."""
        fonts = staged / "fonts"
        assert fonts.is_dir()
        assert list(fonts.glob("*.ttf")), "no Google Sans faces staged"

    def test_every_script_the_pages_reference_is_present(self, staged: Path) -> None:
        """Guards against a page referencing a file staging does not copy -- which is how
        the original bug produced a silently inert window."""
        import re

        for page in ("practice.html", "settings.html"):
            html = (staged / page).read_text(encoding="utf-8")
            for src in re.findall(r'<script src="([^"]+)"', html):
                assert (staged / src).is_file(), f"{page} references missing {src}"

            for href in re.findall(r'<link rel="stylesheet" href="([^"]+)"', html):
                assert (staged / href).is_file(), f"{page} references missing {href}"

    def test_staging_is_reused_within_a_process(self, staged: Path, qt_app) -> None:
        from vocabulary_trainer.ui.web.web_window import stage_assets

        assert stage_assets() == staged


class TestThemeInjection:
    def test_pages_carry_the_token_placeholder(self, staged: Path) -> None:
        """Tokens are injected at load time; without this element the page renders
        unstyled."""
        for page in ("practice.html", "settings.html"):
            html = (staged / page).read_text(encoding="utf-8")
            assert 'id="theme-tokens"' in html, f"{page} has no token placeholder"

    def test_css_uses_variables_the_tokens_define(self, staged: Path) -> None:
        from vocabulary_trainer.ui.theme import COLORS

        css = (staged / "app.css").read_text(encoding="utf-8")
        for token in ("ink", "brand", "surface", "border", "danger", "success"):
            assert f"var(--{token})" in css, f"--{token} unused by app.css"
            assert token in COLORS, f"--{token} not defined in the token source"
