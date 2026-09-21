"""Tests for the widget's popup menu, in particular the Quit action (FR-1.5, FR-1.10).

Needs a ``QApplication`` because :class:`WidgetMenuPopup` is a real Qt widget, so this
follows the same module-scoped fixture pattern as ``test_web_asset_staging.py``.
"""

from __future__ import annotations

import pytest

qt_widgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qt_app():
    app = qt_widgets.QApplication.instance() or qt_widgets.QApplication([])
    yield app


@pytest.fixture
def widget_state(preferences_store, preferences):
    from vocabulary_trainer.services.widget_state_service import WidgetStateService

    return WidgetStateService(preferences_store, preferences)


class TestQuitAction:
    def test_clicking_quit_invokes_the_callback(self, qt_app, widget_state) -> None:
        from vocabulary_trainer.ui.widget.widget_menu_popup import WidgetMenuPopup

        called: list[bool] = []
        popup = WidgetMenuPopup(
            widget_state,
            on_collect=lambda: None,
            on_practice=lambda: None,
            on_settings=lambda: None,
            on_quit=lambda: called.append(True),
        )
        try:
            quit_button = next(
                b
                for b in popup.findChildren(qt_widgets.QPushButton)
                if b.text() == "Quit"
            )
            quit_button.click()
            assert called == [True]
        finally:
            popup.close()

    def test_every_label_fits_the_resolved_width(self, qt_app, widget_state) -> None:
        """Regression guard: an earlier version of this menu clipped "Collect new
        word" because the width calculation omitted the popup's own margins."""
        from vocabulary_trainer.ui.widget.widget_menu_popup import WidgetMenuPopup

        popup = WidgetMenuPopup(
            widget_state,
            on_collect=lambda: None,
            on_practice=lambda: None,
            on_settings=lambda: None,
            on_quit=lambda: None,
        )
        try:
            popup.show_beside((0, 0, 92, 92))
            qt_app.processEvents()
            buttons = [
                b
                for b in popup.findChildren(qt_widgets.QPushButton)
                if b.objectName() == "MenuItem"
            ]
            assert {b.text() for b in buttons} == {
                "Collect new word",
                "Practice",
                "Settings",
                "Quit",
            }
            for button in buttons:
                assert button.width() >= button.sizeHint().width(), (
                    f"{button.text()!r} does not fit its own row"
                )
        finally:
            popup.close()
