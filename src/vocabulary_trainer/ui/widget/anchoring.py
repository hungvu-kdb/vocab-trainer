"""Placing popups beside the floating widget.

The mockups anchor every popup to the left of the character
(``right: 118px`` relative to a widget at ``right: 28px``). That works until the
widget is dragged near the left edge of the screen, at which point a left-anchored
popup would render partly off screen -- so the placement flips to the right instead
(E1-S2 branch 3a).

Kept as a pure function of rectangles rather than a method on a window, so the flip
logic is unit-testable without constructing any Qt widgets.
"""

from __future__ import annotations

from typing import NamedTuple

__all__ = ["Placement", "Rect", "place_beside"]

GAP = 26
"""Horizontal space between the widget and the popup, from the mockups."""


class Rect(NamedTuple):
    """A rectangle in screen coordinates."""

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


class Placement(NamedTuple):
    """Where a popup should be drawn, and which side it ended up on."""

    x: int
    y: int
    flipped: bool
    """``True`` when the popup had to move to the widget's right-hand side."""


def place_beside(
    anchor: Rect,
    popup_width: int,
    popup_height: int,
    screen: Rect,
    *,
    align_bottom: bool = True,
) -> Placement:
    """Position a popup next to ``anchor``, keeping it fully on ``screen``.

    Preferred placement is to the left of the widget, matching the mockups. It flips
    to the right when there is not enough room on the left, and as a last resort --
    a screen narrower than the popup, or a widget wedged into a corner -- the result
    is clamped so the popup is still fully visible even if it overlaps the widget. A
    popup the user cannot read is worse than one that covers the character.
    """
    left_x = anchor.x - popup_width - GAP
    right_x = anchor.right + GAP

    flipped = False
    if left_x >= screen.x:
        x = left_x
    elif right_x + popup_width <= screen.right:
        x = right_x
        flipped = True
    else:
        # Neither side fits: clamp into the screen rather than hanging off it.
        x = max(screen.x, min(left_x, screen.right - popup_width))

    if align_bottom:
        # Bottom edges roughly level with the widget, as in the mockups.
        y = anchor.bottom - popup_height
    else:
        y = anchor.y

    y = max(screen.y, min(y, screen.bottom - popup_height))

    return Placement(x=int(x), y=int(y), flipped=flipped)
