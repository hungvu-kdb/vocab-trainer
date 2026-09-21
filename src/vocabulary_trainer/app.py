"""Application shell: builds the Qt application and connects the UI to the services.

Separate from ``__main__`` so it can be constructed in a test without invoking
``sys.exit``.

The ordering in :meth:`Application.start` follows the startup sequence in the design.
Two steps in it are not obvious:

* **The tray icon is created before the widget.** The widget is only allowed to hide
  itself if a tray icon exists, so its availability has to be known first. Otherwise a
  user could hide the widget on a machine with no notification area and leave the app
  running but unreachable (E1-S4 branch 4a).
* **A header repair is reported after the windows exist**, so the message has somewhere
  to appear rather than being raised before there is any UI.
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QMessageBox

from vocabulary_trainer import APP_NAME
from vocabulary_trainer.domain.models import WidgetState, WordEntry
from vocabulary_trainer.services.app_context import AppContext
from vocabulary_trainer.ui.theme import build_stylesheet
from vocabulary_trainer.ui.web.windows import PracticeWindow, SettingsWindow
from vocabulary_trainer.ui.widget.collect_card_popup import CollectCardPopup
from vocabulary_trainer.ui.widget.duplicate_conflict_popup import (
    DuplicateConflictPopup,
)
from vocabulary_trainer.ui.widget.floating_widget_window import FloatingWidgetWindow
from vocabulary_trainer.ui.widget.lookup_announcer import LookupAnnouncer
from vocabulary_trainer.ui.widget.speech_bubble_popup import SpeechBubblePopup
from vocabulary_trainer.ui.widget.tray_icon import TrayIcon
from vocabulary_trainer.ui.widget.widget_menu_popup import WidgetMenuPopup

__all__ = ["Application", "main"]


class Application:
    """Owns the Qt application, the service context, and the windows."""

    def __init__(self, argv: list[str] | None = None) -> None:
        self._qt = QApplication(argv if argv is not None else sys.argv)
        self._qt.setApplicationName(APP_NAME)
        # The widget is the app's anchor and may be hidden, so Qt must not quit when
        # the last visible window closes -- the tray icon keeps the app alive.
        self._qt.setQuitOnLastWindowClosed(False)

        self._load_bundled_fonts()
        self._qt.setStyleSheet(build_stylesheet())

        self.context = AppContext()

        self._menu: WidgetMenuPopup | None = None
        self._collect_card: CollectCardPopup | None = None
        self._bubble: SpeechBubblePopup | None = None

        # Owned here, not by the Collect card: the card closes as soon as a word is
        # saved, while the lookup it started keeps running. A watcher owned by the
        # card would be destroyed before the result arrived (FR-3.11).
        self._announcer = LookupAnnouncer()
        self._announcer.reported.connect(self._announce_lookup)
        self._conflict: DuplicateConflictPopup | None = None
        self._practice_window: PracticeWindow | None = None
        self._settings_window: SettingsWindow | None = None

        self._tray = TrayIcon(
            self.context.widget_state,
            on_collect=self.open_collect,
            on_practice=self.open_practice,
            on_settings=self.open_settings,
            on_quit=self.quit,
        )

        self._widget = FloatingWidgetWindow(
            self.context.widget_state, on_clicked=self.open_menu
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _load_bundled_fonts() -> None:
        """Register the bundled Google Sans faces (NFR-UI-02).

        Loaded from local files so the UI renders correctly with no network access.
        """
        from pathlib import Path

        fonts = Path(__file__).resolve().parent / "assets" / "fonts"
        if not fonts.is_dir():
            return
        for face in fonts.glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(face))

    def start(self) -> int:
        """Show the UI and run the event loop."""
        self._report_startup_repairs()
        return self._qt.exec()

    def _report_startup_repairs(self) -> None:
        """Tell the user if the workbook's layout had to be corrected (FR-8.4).

        Only fires when something actually changed. Creating a workbook on first run is
        expected and stays silent.
        """
        report = self.context.startup_report
        if not report.needs_user_notice:
            return

        QMessageBox.information(
            None,
            f"{APP_NAME} \u2014 workbook repaired",
            "Your vocabulary workbook's layout was corrected so it could be read:\n\n"
            + "\n".join(f"\u2022 {change}" for change in report.changes),
        )

    # ------------------------------------------------------------------
    # Widget interactions
    # ------------------------------------------------------------------

    def open_menu(self) -> None:
        """Show the mode menu beside the widget (FR-1.5)."""
        self.context.widget_state.set_state(WidgetState.ACTIVE)
        self._menu = WidgetMenuPopup(
            self.context.widget_state,
            on_collect=self.open_collect,
            on_practice=self.open_practice,
            on_settings=self.open_settings,
            on_quit=self.quit,
            on_closed=self._return_to_idle,
        )
        self._menu.show_beside(self._widget.anchor_rect())

    def _return_to_idle(self) -> None:
        """Drop back to the idle pose once nothing the widget owns is open."""
        if self._collect_card is None and self._conflict is None:
            self.context.widget_state.set_state(WidgetState.IDLE)

    def open_collect(self) -> None:
        """Open the Collect card (FR-2.1)."""
        self.context.widget_state.set_state(WidgetState.ACTIVE)
        card = CollectCardPopup(
            self.context.collect,
            on_duplicate=self._show_conflict,
            on_closed=self._on_collect_closed,
            on_lookup_reported=self._announcer.watch,
        )
        self._collect_card = card
        card.show_beside(self._widget.anchor_rect())

    def _announce_lookup(self, word: str, found: bool) -> None:
        """Have the character report a lookup outcome in a speech bubble (FR-3.11).

        Owned by the Application rather than the Collect card because the card closes
        the moment a word is saved, while the lookup it started keeps running -- the
        report has to outlive the window that triggered it.

        Only one bubble is shown at a time: a batch of ten words resolving over a few
        seconds would otherwise stack ten overlapping popups beside the character.
        The newest replaces the previous one, which is the outcome the user is most
        likely still interested in.
        """
        if self._bubble is not None:
            self._bubble.close()
            self._bubble = None

        message = "I found it!" if found else "I couldn't find it"
        bubble = SpeechBubblePopup(message, detail=word, success=found)
        bubble.destroyed.connect(self._on_bubble_closed)
        self._bubble = bubble
        bubble.show_beside(self._widget.anchor_rect())

    def _on_bubble_closed(self) -> None:
        self._bubble = None

    def _on_collect_closed(self) -> None:
        self._collect_card = None
        self._return_to_idle()

    def _show_conflict(self, existing: WordEntry, incoming: WordEntry) -> None:
        """Swap the Collect card for the duplicate conflict popup (FR-4.1)."""
        self.context.widget_state.set_state(WidgetState.ACTIVE)
        popup = DuplicateConflictPopup(
            self.context.collect,
            existing=existing,
            incoming=incoming,
            on_closed=self._on_conflict_closed,
        )
        self._conflict = popup
        popup.show_beside(self._widget.anchor_rect())

    def _on_conflict_closed(self) -> None:
        self._conflict = None
        self._return_to_idle()

    # ------------------------------------------------------------------
    # Windows
    # ------------------------------------------------------------------

    def open_practice(self) -> None:
        """Open Practice, reusing the window if it is already up (FR-5.1)."""
        if self._practice_window is not None:
            self._practice_window.raise_()
            self._practice_window.activateWindow()
            return

        window = PracticeWindow(
            self.context.practice, on_closed=self._on_practice_closed
        )
        self._practice_window = window
        window.show()

    def _on_practice_closed(self) -> None:
        self._practice_window = None

    def open_settings(self) -> None:
        """Open Settings, reusing the window if it is already up (E7-S1 branch 2a)."""
        if self._settings_window is not None:
            self._settings_window.raise_()
            self._settings_window.activateWindow()
            return

        window = SettingsWindow(
            self.context.settings, on_closed=self._on_settings_closed
        )
        self._settings_window = window
        window.show()

    def _on_settings_closed(self) -> None:
        # A settings change may have moved the workbook, so re-point the watcher.
        self.context.retarget_master_file(
            self.context.preferences.master_file_path
        )
        self._settings_window = None

    # ------------------------------------------------------------------

    def quit(self) -> None:
        """Shut down cleanly: stop background work, then end the event loop."""
        self.context.shutdown()
        self._tray.shutdown()
        self._widget.close_permanently()
        self._qt.quit()


def main() -> int:
    """Entry point."""
    return Application().start()
