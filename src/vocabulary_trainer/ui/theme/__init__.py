"""Shared visual theme.

``tokens.py`` holds the values transcribed from ``mockup/styles.css``.
``qt_stylesheet.py`` generates the Qt stylesheet from them, and
``as_css_variables()`` generates the equivalent CSS ``:root`` block for the
web-rendered windows. Both surfaces therefore read from one source and cannot drift
apart (NFR-UI-01).
"""

from vocabulary_trainer.ui.theme.qt_stylesheet import build_stylesheet
from vocabulary_trainer.ui.theme.tokens import (
    COLORS,
    FONT_FAMILY,
    FONT_STACK,
    RADII,
    SHADOWS,
    as_css_variables,
)

__all__ = [
    "COLORS",
    "FONT_FAMILY",
    "FONT_STACK",
    "RADII",
    "SHADOWS",
    "as_css_variables",
    "build_stylesheet",
]
