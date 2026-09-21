"""Design tokens, transcribed from ``mockup/styles.css``.

This module is the single source for both UI surfaces. The Qt stylesheet and the
web-layer CSS are *generated* from these values rather than maintained separately,
so the transparent widget and the web-rendered windows cannot drift apart visually
(NFR-UI-01).

Values are copied verbatim from the mockups' ``:root`` block. When the mockups
change, this file changes, and both surfaces follow.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "COLORS",
    "FONT_FAMILY",
    "FONT_STACK",
    "RADII",
    "SHADOWS",
    "as_css_variables",
]


COLORS: Final[dict[str, str]] = {
    "bg-desktop": "#dfe7f0",
    "ink": "#1f2430",
    "ink-soft": "#5b6472",
    "ink-faint": "#8a93a3",
    "surface": "#ffffff",
    "surface-soft": "#f4f6fa",
    "border": "#e1e6ee",
    "brand": "#4d6bfe",
    "brand-dark": "#3450d6",
    "brand-soft": "#eef1ff",
    "success": "#2fb380",
    "success-soft": "#e6f7ef",
    "danger": "#e2554d",
    "danger-soft": "#fdecea",
    "warning": "#e0a635",
    "warning-soft": "#fff4e0",
}

RADII: Final[dict[str, int]] = {
    "lg": 20,
    "md": 14,
    "sm": 10,
}

SHADOWS: Final[dict[str, str]] = {
    "widget": "0 12px 30px rgba(30, 41, 82, 0.22)",
    "card": "0 6px 20px rgba(30, 41, 82, 0.08)",
}

FONT_FAMILY: Final = "Google Sans"

FONT_STACK: Final = (
    '"Google Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif'
)
"""Matches the mockups' ``--font``.

Google Sans is bundled as local TTF files rather than fetched from a CDN, so the UI
renders correctly with no network connection (NFR-UI-02). Segoe UI is the fallback on
a machine where the bundled font failed to load.
"""


def as_css_variables() -> str:
    """Render the tokens as a CSS ``:root`` block for the web-rendered windows.

    Generated rather than hand-written so the web layer provably uses the same values
    as the Qt layer.
    """
    lines = [":root {"]
    for name, value in COLORS.items():
        lines.append(f"  --{name}: {value};")
    for name, value in RADII.items():
        lines.append(f"  --radius-{name}: {value}px;")
    for name, value in SHADOWS.items():
        lines.append(f"  --shadow-{name}: {value};")
    lines.append(f"  --font: {FONT_STACK};")
    lines.append("}")
    return "\n".join(lines)
