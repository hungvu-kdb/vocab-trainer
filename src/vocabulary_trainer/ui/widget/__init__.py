"""Qt widget windows: the floating overlay and its popups.

These screens are Qt rather than web-rendered because the widget needs a frameless,
per-pixel-translucent, always-on-top window -- the one requirement an embedded web view
cannot satisfy cleanly. The popups are Qt too so they can anchor to the widget and
share its idle/active state.
"""
