"""The duplicate-word conflict popup (FR-4.2, FR-4.6, FR-4.7).

Mirrors ``mockup/widget-collect-duplicate.html``: a warning-bordered card naming the
word, a panel showing where and when the existing entry was collected, three actions
side by side, and a hint stating what dismissal does.

Two decisions from the requirements are visible directly in this file:

* The destructive action is labelled **"Delete both"** rather than "Delete", because
  FR-4.6 requires the label to make clear that neither the old row nor the new
  submission survives.
* **Any dismissal resolves as Keep old** (FR-4.7). Closing the card, pressing Escape,
  and clicking away all route through the same handler, so there is no path that leaves
  the conflict silently unresolved.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vocabulary_trainer.domain.models import DuplicateAction, WordEntry
from vocabulary_trainer.services.collect_service import CollectService
from vocabulary_trainer.ui.widget.anchoring import Rect, place_beside

__all__ = ["CONFLICT_WIDTH", "DuplicateConflictPopup", "format_existing_entry"]

CONFLICT_WIDTH = 280
"""Close to ``.conflict-card``'s 260px plus padding."""


def format_existing_entry(entry: WordEntry) -> str:
    """The "currently in X, collected on Y" panel text (FR-4.2).

    Kept as a module-level function so the wording is testable without constructing a
    Qt widget.
    """
    collected = entry.collected_on.strftime("%b %d, %Y")
    return (
        f"Currently in <b>{entry.collection_name}</b><br />"
        f"Collected on <b>{collected}</b>"
    )


class DuplicateConflictPopup(QWidget):
    """Keep / Replace / Delete both, for a word that already exists."""

    def __init__(
        self,
        collect_service: CollectService,
        existing: WordEntry,
        incoming: WordEntry,
        on_resolved: Callable[[DuplicateAction, bool], None] | None = None,
        on_closed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._service = collect_service
        self._existing = existing
        self._incoming = incoming
        self._on_resolved = on_resolved
        self._on_closed = on_closed
        self._resolved = False

        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._build_ui()
        self.setFixedWidth(CONFLICT_WIDTH + 24)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        card = QFrame()
        # Warning border rather than the neutral card border, per the mockup.
        card.setObjectName("CardWarning")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(30, 41, 82, 40))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        body = QVBoxLayout(card)
        body.setContentsMargins(14, 12, 14, 14)
        body.setSpacing(8)

        body.addLayout(self._warning_title())

        existing = QLabel(format_existing_entry(self._existing))
        existing.setObjectName("ExistingEntry")
        existing.setTextFormat(Qt.TextFormat.RichText)
        existing.setWordWrap(True)
        body.addWidget(existing)

        body.addLayout(self._action_row())

        hint = QLabel(
            "No choice? Closing this keeps the old entry and discards the new one."
        )
        hint.setObjectName("HintText")
        hint.setWordWrap(True)
        body.addWidget(hint)

    def _warning_title(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        badge = QLabel("!")
        badge.setObjectName("IconDotSettings")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(22, 22)
        row.addWidget(badge)

        title = QLabel(f'"{self._existing.word}" already exists')
        title.setObjectName("CardTitle")
        title.setWordWrap(True)
        row.addWidget(title, 1)
        return row

    def _action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        keep = QPushButton("Keep old")
        keep.setObjectName("Outline")
        keep.setCursor(Qt.CursorShape.PointingHandCursor)
        keep.clicked.connect(lambda: self._resolve(DuplicateAction.KEEP_OLD))
        row.addWidget(keep)

        replace = QPushButton("Replace")
        replace.setObjectName("Primary")
        replace.setCursor(Qt.CursorShape.PointingHandCursor)
        replace.clicked.connect(lambda: self._resolve(DuplicateAction.REPLACE))
        row.addWidget(replace)

        # Named for the full effect: FR-4.6 requires the label be unambiguous that
        # neither entry survives.
        delete = QPushButton("Delete both")
        delete.setObjectName("Danger")
        delete.setCursor(Qt.CursorShape.PointingHandCursor)
        delete.clicked.connect(lambda: self._resolve(DuplicateAction.DELETE_BOTH))
        row.addWidget(delete)

        return row

    # ------------------------------------------------------------------

    def _resolve(self, action: DuplicateAction) -> None:
        """Apply the chosen action exactly once."""
        if self._resolved:
            return
        self._resolved = True

        succeeded = self._service.resolve_duplicate(
            action, self._existing, self._incoming
        )
        if self._on_resolved is not None:
            self._on_resolved(action, succeeded)
        self.close()

    def show_beside(self, anchor: tuple[int, int, int, int]) -> None:
        from PySide6.QtGui import QGuiApplication

        x, y, width, height = anchor
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            bounds = Rect(area.x(), area.y(), area.width(), area.height())
        else:  # pragma: no cover
            bounds = Rect(0, 0, 1920, 1080)

        self.adjustSize()
        placement = place_beside(
            Rect(x, y, width, height), self.width(), self.height(), bounds
        )
        self.move(placement.x, placement.y)
        self.show()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: object) -> None:
        """Dismissal without a choice resolves as Keep old (FR-4.7).

        Nothing is written for that action, so this is safe to reach from any close
        path -- clicking the X, pressing Escape, or clicking away. What it guarantees is
        that the conflict is never left in an ambiguous state.
        """
        if not self._resolved:
            self._resolved = True
            self._service.resolve_duplicate(
                DuplicateAction.KEEP_OLD, self._existing, self._incoming
            )
            if self._on_resolved is not None:
                self._on_resolved(DuplicateAction.KEEP_OLD, True)

        if self._on_closed is not None:
            self._on_closed()
        super().closeEvent(event)  # type: ignore[arg-type]
