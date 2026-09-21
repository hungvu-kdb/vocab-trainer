"""System tray presence (FR-1.7).

The tray icon is what makes hiding the widget a reversible decision. The widget is the
only entry point the mockups draw, so without a permanent fallback a user who switched
it off would have no way back into the application short of relaunching it -- and the
app would still be running, so relaunching might do nothing at all.

Because of that, :meth:`TrayIcon.is_available` gates the widget's hide action: if the
tray icon could not be created, hiding is refused and the user is told why
(E1-S4 branch 4a). The app must never be running yet unreachable.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from vocabulary_trainer import APP_NAME
from vocabulary_trainer.domain.models import WidgetState
from vocabulary_trainer.services.widget_state_service import WidgetStateService
from vocabulary_trainer.ui.widget import assets

__all__ = ["TrayIcon"]


class TrayIcon:
    """Tray icon carrying the same menu as the widget."""

    def __init__(
        self,
        widget_state: WidgetStateService,
        on_collect: Callable[[], None],
        on_practice: Callable[[], None],
        on_settings: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._state_service = widget_state
        self._icon: QSystemTrayIcon | None = None

        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self._icon = QSystemTrayIcon(self._load_icon())
        self._icon.setToolTip(APP_NAME)

        menu = QMenu()
        menu.addAction("Collect new word", on_collect)
        menu.addAction("Practice", on_practice)
        menu.addSeparator()
        menu.addAction("Settings", on_settings)

        self._show_widget_action = menu.addAction("Show widget")
        self._show_widget_action.setCheckable(True)
        self._show_widget_action.setChecked(widget_state.is_visible)
        self._show_widget_action.toggled.connect(widget_state.set_visible)

        menu.addSeparator()
        menu.addAction("Quit", on_quit)

        self._icon.setContextMenu(menu)
        # Left-click opens the same menu as right-click, matching the widget's own
        # click behaviour (E1-S4 branch 6a).
        self._icon.activated.connect(self._on_activated)

        self._unsubscribe = widget_state.subscribe(self._sync_toggle)
        self._icon.show()

    @property
    def is_available(self) -> bool:
        """Whether a tray icon exists.

        The widget consults this before allowing itself to be hidden.
        """
        return self._icon is not None

    def _load_icon(self) -> QIcon:
        """Use the character artwork, falling back to an empty icon.

        An empty icon still produces a clickable tray entry, which is the property
        that matters -- reachability, not appearance.
        """
        path = assets.resolve(self._state_service.character, WidgetState.IDLE)
        if path is not None:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                return QIcon(pixmap)
        return QIcon()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason is QSystemTrayIcon.ActivationReason.Trigger and self._icon is not None:
            menu = self._icon.contextMenu()
            if menu is not None:
                menu.popup(self._icon.geometry().center())

    def _sync_toggle(self) -> None:
        """Keep this menu's toggle in step with the widget's own (E1-S4)."""
        if self._icon is None:
            return
        wanted = self._state_service.is_visible
        if self._show_widget_action.isChecked() != wanted:
            # Block signals so reflecting the change does not echo back into the
            # service and cause a notification loop.
            self._show_widget_action.blockSignals(True)
            self._show_widget_action.setChecked(wanted)
            self._show_widget_action.blockSignals(False)

    def refresh_icon(self) -> None:
        """Re-read the artwork after the character changed."""
        if self._icon is not None:
            self._icon.setIcon(self._load_icon())

    def shutdown(self) -> None:
        """Detach and remove the icon."""
        if self._icon is None:
            return
        self._unsubscribe()
        self._icon.hide()
        self._icon = None
