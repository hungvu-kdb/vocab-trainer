"""Tests for popup placement beside the floating widget (E1-S2 branch 3a).

Placement is a pure function of rectangles precisely so this logic can be verified
without constructing any Qt widgets or requiring a display.
"""

from __future__ import annotations

from vocabulary_trainer.ui.widget.anchoring import GAP, Rect, place_beside

SCREEN = Rect(0, 0, 1920, 1080)
POPUP_W = 250
POPUP_H = 300


class TestRect:
    def test_derived_edges(self) -> None:
        rect = Rect(100, 200, 50, 80)
        assert rect.right == 150
        assert rect.bottom == 280


class TestPreferredLeftPlacement:
    def test_places_to_the_left_when_there_is_room(self) -> None:
        """Matches the mockups, where every popup sits left of the character."""
        anchor = Rect(1600, 800, 92, 120)
        placement = place_beside(anchor, POPUP_W, POPUP_H, SCREEN)

        assert placement.flipped is False
        assert placement.x == 1600 - POPUP_W - GAP

    def test_bottom_edges_align_with_the_widget(self) -> None:
        anchor = Rect(1600, 700, 92, 120)
        placement = place_beside(anchor, POPUP_W, POPUP_H, SCREEN)
        assert placement.y == anchor.bottom - POPUP_H

    def test_top_alignment_when_requested(self) -> None:
        anchor = Rect(1600, 400, 92, 120)
        placement = place_beside(anchor, POPUP_W, POPUP_H, SCREEN, align_bottom=False)
        assert placement.y == anchor.y


class TestFlipToRight:
    def test_flips_when_the_widget_hugs_the_left_edge(self) -> None:
        """A left-anchored popup would render off screen."""
        anchor = Rect(10, 800, 92, 120)
        placement = place_beside(anchor, POPUP_W, POPUP_H, SCREEN)

        assert placement.flipped is True
        assert placement.x == anchor.right + GAP

    def test_flipped_popup_is_fully_on_screen(self) -> None:
        anchor = Rect(0, 500, 92, 120)
        placement = place_beside(anchor, POPUP_W, POPUP_H, SCREEN)
        assert placement.x >= SCREEN.x
        assert placement.x + POPUP_W <= SCREEN.right

    def test_does_not_flip_when_the_left_fits_exactly(self) -> None:
        anchor = Rect(POPUP_W + GAP, 500, 92, 120)
        assert place_beside(anchor, POPUP_W, POPUP_H, SCREEN).flipped is False


class TestClampingFallback:
    def test_clamps_when_neither_side_fits(self) -> None:
        """A popup the user cannot read is worse than one covering the character."""
        narrow = Rect(0, 0, 300, 1080)
        anchor = Rect(120, 900, 92, 120)

        placement = place_beside(anchor, POPUP_W, POPUP_H, narrow)

        assert placement.x >= narrow.x
        assert placement.x + POPUP_W <= narrow.right

    def test_vertical_clamp_keeps_the_popup_on_screen(self) -> None:
        anchor = Rect(1600, 40, 92, 120)
        placement = place_beside(anchor, POPUP_W, POPUP_H, SCREEN)
        assert placement.y >= SCREEN.y

    def test_bottom_clamp(self) -> None:
        anchor = Rect(1600, 1070, 92, 120)
        placement = place_beside(anchor, POPUP_W, POPUP_H, SCREEN)
        assert placement.y + POPUP_H <= SCREEN.bottom


class TestMultiMonitor:
    def test_respects_a_secondary_screen_origin(self) -> None:
        """A screen to the left of the primary has negative coordinates on Windows."""
        secondary = Rect(-1920, 0, 1920, 1080)
        anchor = Rect(-300, 800, 92, 120)

        placement = place_beside(anchor, POPUP_W, POPUP_H, secondary)

        assert placement.x >= secondary.x
        assert placement.x + POPUP_W <= secondary.right

    def test_flips_on_a_secondary_screen_left_edge(self) -> None:
        secondary = Rect(-1920, 0, 1920, 1080)
        anchor = Rect(-1910, 800, 92, 120)
        assert place_beside(anchor, POPUP_W, POPUP_H, secondary).flipped is True


class TestReturnTypes:
    def test_coordinates_are_integers(self) -> None:
        """Qt's move() requires ints, not floats."""
        placement = place_beside(Rect(1600, 800, 92, 120), POPUP_W, POPUP_H, SCREEN)
        assert isinstance(placement.x, int)
        assert isinstance(placement.y, int)
