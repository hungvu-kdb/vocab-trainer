"""The popup menu opened by clicking the widget (FR-1.5, FR-1.6).

Mirrors ``mockup/widget-menu.html``: Collect, Practice, a divider, Settings, and a
widget on/off toggle, each action entry carrying a coloured icon square.

The window is a frameless ``Popup``, which gives two behaviours for free that the
mockups imply but do not state: it closes when the user clicks anywhere else
(E1-S2 branch 5d), and it does not take focus from the application underneath.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtGui import QColor, QFontMetrics

from vocabulary_trainer.services.widget_state_service import WidgetStateService
from vocabulary_trainer.ui.widget.anchoring import Rect, place_beside
from vocabulary_trainer.ui.widget.toggle_switch import ToggleSwitch

__all__ = ["WidgetMenuPopup"]

MENU_WIDTH = 176
"""Close to ``.widget-menu``'s 168px plus its padding -- used as a floor so the
menu never renders narrower than the mockups, but the actual width also grows to
fit whichever label is widest (see :meth:`WidgetMenuPopup._resolve_width`),
because ``MENU_WIDTH`` alone was too narrow for "Collect new word" and silently
clipped it (E1-S2)."""

_ICON_LEFT = 10
_ICON_SIZE = 26
_ICON_TEXT_GAP = 8
"""Geometry of the icon square each entry positions at (icon_left, 6) -- kept in
one place so the stylesheet's ``QPushButton#MenuItem`` left padding and the
width calculation below cannot drift apart."""

_MENU_TEXT_LABELS = ("Collect new word", "Practice", "Settings", "Quit")
"""Every label the menu renders, used to size the card to its content."""

_OUTER_MARGIN = 10
"""Matches ``outer.setContentsMargins(10, 10, 10, 10)`` in ``__init__``."""

_BODY_MARGIN_LEFT = 8
_BODY_MARGIN_RIGHT = 8
"""Matches ``body.setContentsMargins(8, 8, 8, 6)`` in ``__init__``."""

_BUTTON_RIGHT_PADDING = 14
"""Matches the ``QPushButton#MenuItem`` right padding in the stylesheet."""


class WidgetMenuPopup(QWidget):
    """Mode chooser anchored to the floating widget."""

    def __init__(
        self,
        widget_state: WidgetStateService,
        on_collect: Callable[[], None],
        on_practice: Callable[[], None],
        on_settings: Callable[[], None],
        on_quit: Callable[[], None],
        on_closed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._state_service = widget_state
        self._on_closed = on_closed

        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        outer = QVBoxLayout(self)
        # Margin leaves room for the drop shadow to render outside the card.
        outer.setContentsMargins(10, 10, 10, 10)

        card = QFrame()
        card.setObjectName("MenuCard")
        self._apply_shadow(card)
        outer.addWidget(card)

        body = QVBoxLayout(card)
        body.setContentsMargins(8, 8, 8, 6)
        body.setSpacing(2)

        body.addWidget(
            self._menu_entry("Collect new word", "+", "IconDotCollect", on_collect)
        )
        body.addWidget(
            self._menu_entry("Practice", "\u25b6", "IconDotPractice", on_practice)
        )

        divider = QFrame()
        divider.setObjectName("MenuDivider")
        divider.setFixedHeight(1)
        body.addSpacing(4)
        body.addWidget(divider)
        body.addSpacing(4)

        body.addWidget(
            self._menu_entry("Settings", "\u2699", "IconDotSettings", on_settings)
        )

        body.addLayout(self._toggle_row())

        quit_divider = QFrame()
        quit_divider.setObjectName("MenuDivider")
        quit_divider.setFixedHeight(1)
        body.addSpacing(4)
        body.addWidget(quit_divider)
        body.addSpacing(4)

        body.addWidget(
            self._menu_entry("Quit", "\u2715", "IconDotQuit", on_quit)
        )

        self.setFixedWidth(self._resolve_width())
        self.adjustSize()

    # ------------------------------------------------------------------

    @staticmethod
    def _apply_shadow(target: QWidget) -> None:
        """Approximate ``--shadow-card``.

        QSS has no ``box-shadow``, so the mockups' shadow is painted with a graphics
        effect instead of being silently dropped.
        """
        shadow = QGraphicsDropShadowEffect(target)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(30, 41, 82, 40))
        target.setGraphicsEffect(shadow)

    def _menu_entry(
        self, text: str, glyph: str, icon_object_name: str, handler: Callable[[], None]
    ) -> QWidget:
        """One action row: coloured icon square plus label, the whole row clickable.

        The label is the button's real text -- room for the icon comes from the
        ``QPushButton#MenuItem`` stylesheet's left padding, not literal leading
        spaces, so the button's own size hint reflects the text it actually shows.
        """
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        button = QPushButton(text)
        button.setObjectName("MenuItem")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda: self._activate(handler))

        icon = QLabel(glyph, button)
        icon.setObjectName(icon_object_name)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        icon.move(_ICON_LEFT, 6)

        layout.addWidget(button)
        return row

    def _resolve_width(self) -> int:
        """Widen the menu past ``MENU_WIDTH`` if a label would not otherwise fit.

        Measured against the same font the stylesheet gives ``QPushButton#MenuItem``
        (13px, the app's font family) rather than assumed, so this stays correct if
        the token or the label text changes.

        The previous version of this calculation only accounted for the button's
        own padding and left the popup's outer margin and the card body's margin
        out of the total, so the resolved width was too small by exactly that
        amount (36px) and "Collect new word" still clipped by ~20px. Every layer of
        chrome between the popup's outer edge and the label's left pixel has to be
        added up, not just the button's own padding.
        """
        font = self.font()
        font.setPixelSize(13)
        metrics = QFontMetrics(font)
        text_left_padding = _ICON_LEFT + _ICON_SIZE + _ICON_TEXT_GAP
        widest_label = max(metrics.horizontalAdvance(t) for t in _MENU_TEXT_LABELS)

        chrome = (
            2 * _OUTER_MARGIN
            + _BODY_MARGIN_LEFT
            + _BODY_MARGIN_RIGHT
            + text_left_padding
            + _BUTTON_RIGHT_PADDING
        )
        # A small buffer absorbs subpixel rounding between QFontMetrics' measurement
        # and Qt's actual text layout, so the label never sits flush against the
        # button's padding edge.
        required = widest_label + chrome + 6
        return max(MENU_WIDTH, required)

    def _toggle_row(self) -> QHBoxLayout:
        """The quick widget on/off switch, mirroring ``.toggle-row``."""
        row = QHBoxLayout()
        row.setContentsMargins(10, 6, 10, 2)

        label = QLabel("Widget on")
        label.setObjectName("ToggleLabel")
        row.addWidget(label)
        row.addStretch(1)

        self._toggle = ToggleSwitch()
        self._toggle.setChecked(self._state_service.is_visible)
        self._toggle.toggled.connect(self._on_toggle)
        row.addWidget(self._toggle)

        return row

    def _on_toggle(self, checked: bool) -> None:
        """Hiding the widget closes this menu with it (E1-S4 branch 3a)."""
        self._state_service.set_visible(checked)
        if not checked:
            self.close()

    def _activate(self, handler: Callable[[], None]) -> None:
        """Run an action and dismiss the menu."""
        self.close()
        handler()

    # ------------------------------------------------------------------

    def show_beside(self, anchor: tuple[int, int, int, int]) -> None:
        """Open the menu next to the widget, flipping sides if space demands."""
        x, y, width, height = anchor
        screen = QGuiApplication.screenAt(self.mapToGlobal(self.rect().center()))
        if screen is None:
            screen = QGuiApplication.primaryScreen()

        if screen is not None:
            area = screen.availableGeometry()
            bounds = Rect(area.x(), area.y(), area.width(), area.height())
        else:  # pragma: no cover - no screen in a headless session
            bounds = Rect(0, 0, 1920, 1080)

        placement = place_beside(
            Rect(x, y, width, height),
            self.width(),
            self.height(),
            bounds,
        )
        self.move(placement.x, placement.y)
        self.show()

    def hideEvent(self, event: QEvent) -> None:
        """Tell the owner when the menu closes, however it closed.

        Covers clicking an entry, clicking away, and pressing Escape -- all of which
        must return the character to its idle pose (E1-S2 branch 5d).
        """
        super().hideEvent(event)
        if self._on_closed is not None:
            self._on_closed()
