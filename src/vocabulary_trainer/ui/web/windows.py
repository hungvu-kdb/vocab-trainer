"""The Practice and Settings windows.

Thin wrappers over :class:`WebWindow`: each pairs a page with its bridge and adds the
one behaviour that page cannot express in JavaScript.

For Practice that behaviour matters -- closing the window mid-session must route
through the summary rather than discarding the session (FR-6.12). A page cannot
reliably act on a window close, so the window itself asks the service to finish.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QCloseEvent

from vocabulary_trainer.services.practice_service import PracticeService
from vocabulary_trainer.services.settings_service import SettingsService
from vocabulary_trainer.ui.web.practice_bridge import PracticeBridge
from vocabulary_trainer.ui.web.settings_bridge import SettingsBridge
from vocabulary_trainer.ui.web.web_window import WebWindow

__all__ = ["PracticeWindow", "SettingsWindow"]


class PracticeWindow(WebWindow):
    """Setup, drill and summary, in one window."""

    def __init__(
        self,
        practice: PracticeService,
        on_closed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            page="practice.html",
            bridge=PracticeBridge(practice),
            title_suffix="Practice",
            width=920,
            height=680,
        )
        self._practice = practice
        self._on_closed = on_closed

    def closeEvent(self, event: QCloseEvent) -> None:
        """End any in-flight session on close, so its results are still recorded.

        FR-6.12 requires window close and the End session button to reach the same
        outcome. The summary itself cannot be shown -- the window is going away -- but
        the session is finished properly and written to history rather than vanishing.
        """
        session = self._practice.session
        if session is not None:
            try:
                self._practice.end_session()
            except Exception:
                # Closing a window must never fail. A session that cannot be recorded
                # is discarded rather than blocking the close.
                self._practice.abandon_session()

        if self._on_closed is not None:
            self._on_closed()
        super().closeEvent(event)


class SettingsWindow(WebWindow):
    """General, Collections, Widget, Audio and About."""

    def __init__(
        self,
        settings: SettingsService,
        on_closed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            page="settings.html",
            bridge=SettingsBridge(settings),
            title_suffix="Settings",
            width=820,
            height=600,
        )
        self._on_closed = on_closed

    def closeEvent(self, event: QCloseEvent) -> None:
        """Settings persists each change as it is made, so closing needs no save."""
        if self._on_closed is not None:
            self._on_closed()
        super().closeEvent(event)
