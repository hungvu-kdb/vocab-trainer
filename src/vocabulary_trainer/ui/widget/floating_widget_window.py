"""The always-on-top floating character (FR-1.1 through FR-1.4).

This is the most platform-sensitive part of the application. Three window flags and
one attribute have to combine correctly or the effect collapses:

* ``FramelessWindowHint`` -- no title bar or border.
* ``WA_TranslucentBackground`` -- true per-pixel alpha, so the character's
  anti-aliased edges blend with the desktop instead of sitting in a grey box.
* ``WindowStaysOnTopHint`` -- above other applications.
* ``Tool`` -- keeps it out of the taskbar and the Alt-Tab list, and stops it stealing
  focus from whatever the user is working in.

``Tool`` is the non-obvious one. Without it the widget appears as a taskbar entry and
activates on show, which for something meant to sit quietly on the desktop all day is
exactly wrong.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor, QGuiApplication, QMouseEvent, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from vocabulary_trainer.domain.models import WidgetState
from vocabulary_trainer.services.widget_state_service import WidgetStateService
from vocabulary_trainer.ui.widget import assets

__all__ = ["FloatingWidgetWindow"]

WIDGET_WIDTH = 92
"""Matches ``.mini-ani-widget`` in the mockups.

This is the width at 100%. The user's size setting scales it (FR-7.15) -- read
:func:`FloatingWidgetWindow._target_width` rather than this constant when sizing
or positioning, or the widget will be laid out as though it were always 92px.
"""

_DRAG_THRESHOLD = 4
"""Pixels of movement before a press becomes a drag rather than a click.

Without this, the small hand-tremor during a click would register as a drag, so the
menu would never open and the widget would jitter (E1-S3 branch 4a).
"""

_EDGE_MARGIN = 24
"""Minimum on-screen pixels kept grabbable when clamping (E1-S1 branch 3a)."""


class FloatingWidgetWindow(QWidget):
    """The draggable character overlay."""

    def __init__(
        self,
        widget_state: WidgetStateService,
        on_clicked: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._state_service = widget_state
        self._on_clicked = on_clicked

        self._press_origin: QPoint | None = None
        self._window_origin: QPoint | None = None
        self._is_dragging = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._image = QLabel()
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        layout.addWidget(self._image)

        self._unsubscribe = widget_state.subscribe(self._on_state_changed)

        self._render_character()
        self._apply_saved_position()
        self._apply_visibility()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _target_width(self) -> int:
        """The widget's width at the user's chosen size (FR-7.15).

        Scaled from the source artwork every time rather than from the currently
        displayed pixmap: repeatedly rescaling an already-scaled image compounds
        interpolation blur, so going 100% -> 300% -> 100% would not return to a
        crisp original.
        """
        width = round(WIDGET_WIDTH * self._state_service.scale_factor)
        # One pixel floor so a pathological scale can never produce a zero-sized
        # window, which Qt would treat as unmapped and the user as "it vanished".
        return max(1, width)

    def _render_character(self) -> None:
        """Draw the current character in its current pose (FR-1.2), at the set size."""
        target_width = self._target_width()

        path = assets.resolve(
            self._state_service.character, self._state_service.state
        )
        if path is None:
            # No artwork: show nothing rather than a broken-image placeholder. The
            # window keeps working, so the user can still reach Settings via the tray.
            self._image.clear()
            self._resize_to(target_width, target_width)
            return

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._image.clear()
            return

        scaled = pixmap.scaledToWidth(
            target_width, Qt.TransformationMode.SmoothTransformation
        )
        self._image.setPixmap(scaled)
        self._resize_to(scaled.width(), scaled.height())

    def _resize_to(self, width: int, height: int) -> None:
        """Force the window to exactly this size, growing or shrinking.

        ``resize()`` alone only ever grew this window. Both the label and the
        window keep a minimum size derived from the largest pixmap they have held,
        and a plain ``resize()`` is clamped by that minimum -- so 300% -> 100% left
        a 92px cat centred in a 276px window with a dead border around it. Setting
        a fixed size on both moves the floor down as well as up.

        Fixed rather than merely resized is correct here regardless: the widget has
        no frame and is not user-resizable, so its size is always exactly the
        artwork's size.
        """
        self._image.setFixedSize(width, height)
        self.setFixedSize(width, height)

    def _on_state_changed(self) -> None:
        """React to any change published by the state service."""
        previous_size = self.size()
        self._render_character()
        if self.size() != previous_size:
            # Growing near a screen edge can push the widget partly off-screen, and
            # the saved position was clamped for the old size. Re-clamp so a size
            # change can never strand it somewhere ungrabbable.
            self.move(self._clamped(self.pos()))
        self._apply_visibility()

    def _apply_visibility(self) -> None:
        if self._state_service.is_visible:
            if not self.isVisible():
                self.show()
        elif self.isVisible():
            self.hide()

    # ------------------------------------------------------------------
    # Positioning
    # ------------------------------------------------------------------

    def _apply_saved_position(self) -> None:
        """Restore the last position, or fall back to the default corner (FR-1.4)."""
        saved = self._state_service.position
        target = (
            QPoint(*saved) if saved is not None else self._default_position()
        )
        self.move(self._clamped(target))

    def _default_position(self) -> QPoint:
        """Bottom-right of the primary screen, clear of the taskbar.

        Mirrors ``.pos-br`` in the mockups: 28px in from the right edge, 64px up from
        the bottom, which leaves room for a standard-height taskbar.
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None:  # pragma: no cover - always present in a GUI session
            return QPoint(100, 100)

        area = screen.availableGeometry()
        # self.width(), not WIDGET_WIDTH: at 300% the widget is three times wider,
        # and insetting by the unscaled width would hang it off the right edge.
        return QPoint(
            area.right() - max(self.width(), WIDGET_WIDTH) - 28,
            area.bottom() - self.height() - 64,
        )

    def _clamped(self, position: QPoint) -> QPoint:
        """Pull a position back onto a visible screen.

        Guards two cases: a saved position from a monitor that has since been
        disconnected or a resolution that shrank (E1-S1 branch 3a), and a drag that
        ran past a screen edge (E1-S3 branch 3a). Either way a grabbable margin stays
        on screen, so the widget can never become unreachable.
        """
        screen = QGuiApplication.screenAt(position) or QGuiApplication.primaryScreen()
        if screen is None:  # pragma: no cover
            return position

        area = screen.availableGeometry()
        # Falls back to the unscaled width only before the first render, when the
        # window has no size yet.
        width = max(self.width(), 1)
        height = max(self.height(), 1)

        x = min(max(position.x(), area.left() - width + _EDGE_MARGIN), area.right() - _EDGE_MARGIN)
        y = min(max(position.y(), area.top()), area.bottom() - _EDGE_MARGIN)
        return QPoint(x, y)

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() is not Qt.MouseButton.LeftButton:
            return
        self._press_origin = event.globalPosition().toPoint()
        self._window_origin = self.pos()
        self._is_dragging = False
        self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_origin is None or self._window_origin is None:
            return

        delta = event.globalPosition().toPoint() - self._press_origin
        if not self._is_dragging:
            if max(abs(delta.x()), abs(delta.y())) < _DRAG_THRESHOLD:
                return
            self._is_dragging = True

        # Follow the cursor continuously (FR-1.3), clamped so the widget cannot be
        # dragged entirely off screen.
        self.move(self._clamped(self._window_origin + delta))
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() is not Qt.MouseButton.LeftButton:
            return

        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        was_dragging = self._is_dragging
        self._press_origin = None
        self._window_origin = None
        self._is_dragging = False

        if was_dragging:
            # Persist the new position (FR-1.3). A save failure keeps the widget where
            # it was dropped for this session rather than snapping it back.
            self._state_service.move_to(self.x(), self.y())
        elif self._on_clicked is not None:
            # A press with no meaningful movement is a click, so open the menu
            # (E1-S3 branch 4a).
            self._on_clicked()

        event.accept()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def anchor_rect(self) -> tuple[int, int, int, int]:
        """Geometry popups use to position themselves beside the widget."""
        return (self.x(), self.y(), self.width(), self.height())

    def close_permanently(self) -> None:
        """Detach from the state service and close.

        Unsubscribing matters: without it the service would hold a reference to a
        destroyed window and notifying it would raise.
        """
        self._unsubscribe()
        self.close()
