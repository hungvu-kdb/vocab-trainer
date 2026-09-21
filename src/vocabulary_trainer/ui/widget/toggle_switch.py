"""A pill-shaped on/off switch with a sliding thumb, matching ``.switch`` in the
mockups (FR-1.6, FR-7.13's widget-visible toggle).

Qt Style Sheets cannot produce this control from a plain ``QCheckBox``: QSS has no
equivalent of CSS's ``::after`` pseudo-element, so ``QCheckBox::indicator`` can only
ever paint a single flat glyph -- there is nowhere in QSS to describe a circular
thumb that sits offset within the track and moves when checked. Painting it directly
is the only way to get the "roller" the mockups show, rather than the flat two-state
square a plain checkbox produces.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from vocabulary_trainer.ui.theme.tokens import COLORS

__all__ = ["ToggleSwitch"]

_WIDTH = 38
_HEIGHT = 22
_THUMB_MARGIN = 2
_THUMB_DIAMETER = _HEIGHT - 2 * _THUMB_MARGIN
"""Matches ``.switch`` / ``.switch .track::after`` in ``mockup/styles.css``:
38x22 track, an 18px thumb inset by 2px on every side."""


class ToggleSwitch(QAbstractButton):
    """A checkable pill switch with a thumb that slides between its two ends."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self):  # noqa: D102 - Qt override, signature fixed by base class
        from PySide6.QtCore import QSize

        return QSize(_WIDTH, _HEIGHT)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        track_color = QColor(COLORS["brand"] if self.isChecked() else COLORS["border"])
        painter.setBrush(track_color)
        track_rect = QRectF(0, 0, _WIDTH, _HEIGHT)
        radius = _HEIGHT / 2
        painter.drawRoundedRect(track_rect, radius, radius)

        thumb_x = (
            _WIDTH - _THUMB_MARGIN - _THUMB_DIAMETER
            if self.isChecked()
            else _THUMB_MARGIN
        )
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(
            QRectF(thumb_x, _THUMB_MARGIN, _THUMB_DIAMETER, _THUMB_DIAMETER)
        )

        painter.end()
