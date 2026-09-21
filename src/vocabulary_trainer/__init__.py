"""Vocabulary Trainer v2.

A Windows desktop application for collecting and practising English vocabulary,
backed by a single human-editable Excel workbook.

Layering, with dependencies pointing downward only:

    ui          Qt widgets (floating overlay) + QWebEngineView (Practice, Settings)
    services    orchestration; the only layer the UI may call
    data        Excel workbook, preferences, practice history
    integrations dictionary/translation clients, TTS, audio, OS startup
    domain      pure logic: identity, lookup priority, shuffle, scoring

Nothing below ``ui`` imports anything from it, which is what makes the business
logic testable without a display.
"""

__version__ = "2.0.0"
APP_NAME = "Vocabulary Trainer"
