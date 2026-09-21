"""Qt stylesheet generated from the shared design tokens.

Qt Style Sheets are CSS-like but not CSS: there are no custom properties, no
``box-shadow``, and no ``border-radius`` on arbitrary widgets. So rather than shipping
a hand-written ``.qss`` that would silently diverge from ``tokens.py``, the stylesheet
is composed here by interpolating the same token values the web layer uses
(NFR-UI-01).

Where Qt cannot express a mockup effect, the difference is noted inline rather than
quietly dropped.
"""

from __future__ import annotations

from vocabulary_trainer.ui.theme.tokens import COLORS, FONT_FAMILY, RADII

__all__ = ["build_stylesheet"]


def build_stylesheet() -> str:
    """The application-wide Qt stylesheet for the widget-layer windows."""
    c = COLORS
    r = RADII

    return f"""
/* Generated from vocabulary_trainer.ui.theme.tokens -- do not hand-edit. */

* {{
    font-family: "{FONT_FAMILY}", "Segoe UI", sans-serif;
    color: {c["ink"]};
}}

/* ---------------------------------------------------------------
   Cards: the popup surfaces anchored to the widget.
   Soft shadows from the mockups cannot be expressed in QSS, so each
   card window paints its own shadow via QGraphicsDropShadowEffect.
   --------------------------------------------------------------- */

QFrame#Card {{
    background: {c["surface"]};
    border: 1px solid {c["border"]};
    border-radius: {r["md"]}px;
}}

QFrame#CardWarning {{
    background: {c["surface"]};
    border: 1px solid {c["warning"]};
    border-radius: {r["md"]}px;
}}

QFrame#InfoPanel {{
    background: {c["surface-soft"]};
    border: none;
    border-radius: {r["sm"]}px;
}}

/* ---------------------------------------------------------------
   Typography
   --------------------------------------------------------------- */

QLabel#CardTitle {{
    font-size: 13px;
    font-weight: 600;
}}

QLabel#FieldLabel {{
    font-size: 11px;
    color: {c["ink-faint"]};
    letter-spacing: 1px;
}}

/* Echoes back what a comma-separated entry parsed into, so the lowercasing and
   duplicate collapsing are visible before saving rather than after. */
QLabel#FieldHint {{
    font-size: 11px;
    color: {c["brand"]};
}}

QLabel#StatusLine {{
    font-size: 11px;
    color: {c["ink-faint"]};
}}

QLabel#StatusLineSuccess {{
    font-size: 11px;
    color: {c["success"]};
}}

QLabel#StatusLineError {{
    font-size: 11px;
    color: {c["danger"]};
}}

QLabel#HintText {{
    font-size: 10px;
    color: {c["ink-faint"]};
}}

QLabel#ExistingEntry {{
    background: {c["surface-soft"]};
    border-radius: {r["sm"]}px;
    padding: 8px 10px;
    font-size: 12px;
    color: {c["ink-soft"]};
}}

/* ---------------------------------------------------------------
   Inputs
   --------------------------------------------------------------- */

QLineEdit, QComboBox {{
    background: {c["surface-soft"]};
    border: 1px solid {c["border"]};
    border-radius: {r["sm"]}px;
    padding: 7px 10px;
    font-size: 13px;
    selection-background-color: {c["brand"]};
}}

QLineEdit:focus, QComboBox:focus {{
    border-color: {c["brand"]};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background: {c["surface"]};
    border: 1px solid {c["border"]};
    selection-background-color: {c["brand-soft"]};
    selection-color: {c["brand"]};
    outline: none;
}}

/* ---------------------------------------------------------------
   Buttons
   --------------------------------------------------------------- */

QPushButton {{
    border: none;
    border-radius: {r["sm"]}px;
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton#Primary {{
    background: {c["brand"]};
    color: #ffffff;
}}
QPushButton#Primary:hover  {{ background: {c["brand-dark"]}; }}
QPushButton#Primary:disabled {{
    background: {c["border"]};
    color: {c["ink-faint"]};
}}

QPushButton#Ghost {{
    background: {c["surface-soft"]};
    color: {c["ink-soft"]};
}}
QPushButton#Ghost:hover {{ background: {c["border"]}; }}

QPushButton#Danger {{
    background: {c["danger"]};
    color: #ffffff;
}}
QPushButton#Danger:hover {{ background: #c9463f; }}

QPushButton#Outline {{
    background: transparent;
    border: 1px solid {c["border"]};
    color: {c["ink"]};
}}
QPushButton#Outline:hover {{ border-color: {c["brand"]}; color: {c["brand"]}; }}

/* Part-of-speech chips: pill-shaped, brand-filled when selected. */
QPushButton#Chip {{
    background: {c["surface-soft"]};
    border: 1px solid {c["border"]};
    border-radius: 11px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 500;
    color: {c["ink-soft"]};
}}
QPushButton#Chip:hover {{ border-color: {c["brand"]}; }}
QPushButton#Chip:checked {{
    background: {c["brand"]};
    border-color: {c["brand"]};
    color: #ffffff;
}}

/* Close affordance on card title rows. */
QPushButton#CloseX {{
    background: transparent;
    color: {c["ink-faint"]};
    font-size: 14px;
    font-weight: 400;
    padding: 0px;
    border-radius: {r["sm"]}px;
}}
QPushButton#CloseX:hover {{
    background: {c["surface-soft"]};
    color: {c["ink"]};
}}

/* ---------------------------------------------------------------
   Speech bubble -- the character reporting a lookup outcome
   --------------------------------------------------------------- */

/* Success and "not found" differ only in accent colour. The muted variant is not
   styled as an error: failing to find a rare word is an ordinary outcome, and a red
   alert would overstate it. */
QFrame#SpeechBubble, QFrame#SpeechBubbleMuted {{
    background: {c["surface"]};
    border: 1px solid {c["border"]};
    border-radius: {r["md"]}px;
}}
QFrame#SpeechBubble {{ border-left: 3px solid {c["success"]}; }}
QFrame#SpeechBubbleMuted {{ border-left: 3px solid {c["ink-faint"]}; }}

QLabel#SpeechBubbleIcon {{
    color: {c["success"]};
    font-size: 12px;
    font-weight: 700;
}}
QLabel#SpeechBubbleIconMuted {{
    color: {c["ink-faint"]};
    font-size: 12px;
    font-weight: 700;
}}
QLabel#SpeechBubbleText {{
    color: {c["ink"]};
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}}
QLabel#SpeechBubbleDetail {{
    color: {c["ink-soft"]};
    font-size: 11px;
    background: transparent;
}}

/* ---------------------------------------------------------------
   Widget popup menu
   --------------------------------------------------------------- */

QFrame#MenuCard {{
    background: {c["surface"]};
    border: 1px solid {c["border"]};
    border-radius: {r["md"]}px;
}}

QPushButton#MenuItem {{
    background: transparent;
    border-radius: {r["sm"]}px;
    /* Left padding reserves room for the 26px icon square positioned at x=10
       (see WidgetMenuPopup._ICON_LEFT/_ICON_SIZE/_ICON_TEXT_GAP), so the label
       starts clear of it instead of relying on literal leading spaces in the
       button text -- which is what silently clipped long labels before. */
    padding: 8px 14px 8px 44px;
    font-size: 13px;
    font-weight: 400;
    text-align: left;
}}
QPushButton#MenuItem:hover {{ background: {c["surface-soft"]}; }}

/* Coloured icon squares beside each menu entry, matching .icon-dot. */
QLabel#IconDotCollect {{
    background: {c["brand-soft"]};
    color: {c["brand"]};
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
}}
QLabel#IconDotPractice {{
    background: {c["success-soft"]};
    color: {c["success"]};
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
}}
QLabel#IconDotSettings {{
    background: {c["surface-soft"]};
    color: {c["ink-soft"]};
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
}}
QLabel#IconDotQuit {{
    background: {c["danger-soft"]};
    color: {c["danger"]};
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
}}

QFrame#MenuDivider {{
    background: {c["border"]};
    max-height: 1px;
    border: none;
}}

QLabel#ToggleLabel {{
    font-size: 12px;
    color: {c["ink-soft"]};
}}

""".strip()
