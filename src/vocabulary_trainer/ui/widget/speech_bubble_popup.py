"""A small chat quote beside the character, for lookup outcomes (FR-3.11).

The Collect card closes the instant a word is saved, so a lookup that resolves
afterwards had nowhere to report itself: the meaning appeared in the workbook with
no acknowledgement on screen. This is that acknowledgement -- the character says
"I found it" or "I couldn't find it" once the answer lands.

Deliberately not a notification or a dialog:

* It **never takes focus** and cannot be interacted with, so it cannot interrupt
  whatever the user went back to doing. That is the whole reason the widget is a
  ``Tool`` window in the first place.
* It **dismisses itself** after a few seconds. A message about a word saved a moment
  ago stops being useful quickly, and one that needed closing would be worse than no
  message at all.
* Clicking it dismisses it early, for anyone who would rather not wait.

Reuses ``place_beside`` so it lands on the same side as every other popup, and flips
away from a screen edge for the same reason they do.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from vocabulary_trainer.ui.widget.anchoring import Rect, place_beside

__all__ = ["BUBBLE_WIDTH", "SpeechBubblePopup"]

BUBBLE_WIDTH = 168
"""Narrow on purpose: this holds one short sentence, not a definition.

Wide enough for "I couldn't find it" plus the word on a second line, and no wider --
a big panel beside the character would read as a dialog demanding attention.
"""

DEFAULT_DURATION_MS = 4000
"""How long the bubble stays up.

Long enough to notice and read while glancing away from another task, short enough
that it is gone before it becomes clutter. A found/not-found outcome carries no
action, so there is nothing to keep it around for.
"""


class SpeechBubblePopup(QWidget):
    """A transient, non-interactive message anchored beside the widget."""

    def __init__(
        self,
        message: str,
        detail: str | None = None,
        *,
        success: bool = True,
        duration_ms: int = DEFAULT_DURATION_MS,
    ) -> None:
        super().__init__()

        # ToolTip rather than Popup: a Popup grabs input, which would swallow the
        # next click the user makes somewhere else entirely. WindowTransparentForInput
        # is not used, because then clicking to dismiss early would not work.
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(BUBBLE_WIDTH + 20)

        self._build_ui(message, detail, success)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.close)
        self._duration_ms = duration_ms

    def _build_ui(self, message: str, detail: str | None, success: bool) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        bubble = QFrame()
        bubble.setObjectName("SpeechBubble" if success else "SpeechBubbleMuted")
        shadow = QGraphicsDropShadowEffect(bubble)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(30, 41, 82, 45))
        bubble.setGraphicsEffect(shadow)
        outer.addWidget(bubble)

        body = QVBoxLayout(bubble)
        body.setContentsMargins(12, 9, 12, 9)
        body.setSpacing(2)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.setContentsMargins(0, 0, 0, 0)

        icon = QLabel("\u2713" if success else "\u2715")
        icon.setObjectName("SpeechBubbleIcon" if success else "SpeechBubbleIconMuted")
        row.addWidget(icon)

        text = QLabel(message)
        text.setObjectName("SpeechBubbleText")
        text.setWordWrap(True)
        row.addWidget(text, 1)
        body.addLayout(row)

        if detail:
            # The word itself, so a bubble seen a few seconds later is still
            # attributable -- by then the user may have collected another word.
            word = QLabel(detail)
            word.setObjectName("SpeechBubbleDetail")
            word.setWordWrap(True)
            body.addWidget(word)

    # ------------------------------------------------------------------

    def show_beside(self, anchor: tuple[int, int, int, int]) -> None:
        """Place the bubble next to the widget and start its dismissal timer."""
        from PySide6.QtGui import QGuiApplication

        x, y, width, height = anchor
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            bounds = Rect(area.x(), area.y(), area.width(), area.height())
        else:  # pragma: no cover - always present in a GUI session
            bounds = Rect(0, 0, 1920, 1080)

        self.adjustSize()
        placement = place_beside(
            Rect(x, y, width, height),
            self.width(),
            self.height(),
            bounds,
            # Top-aligned rather than bottom-aligned: the character's head is where a
            # speech bubble belongs, and bottom-aligning would tuck it behind the
            # taskbar when the widget sits in its default corner.
            align_bottom=False,
        )
        self.move(placement.x, placement.y)
        self.show()
        self._timer.start(self._duration_ms)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Dismiss on click, for a user who does not want to wait it out."""
        self.close()
        event.accept()

    def closeEvent(self, event: object) -> None:
        # Stop the timer explicitly: without this, a bubble dismissed by click leaves
        # a pending timeout that fires against a closed window.
        self._timer.stop()
        super().closeEvent(event)  # type: ignore[arg-type]
