"""Presentation layer.

Two surfaces, chosen per screen for a concrete reason:

* :mod:`vocabulary_trainer.ui.widget` -- Qt widgets, for the floating overlay and its
  popups. Requires per-pixel transparency and always-on-top behaviour.
* :mod:`vocabulary_trainer.ui.web` -- ``QWebEngineView``, for the Practice and Settings
  windows. Reuses the mockup HTML and CSS directly, which is what makes strict visual
  fidelity achievable. No HTTP server and no browser process: content is loaded from
  local files inside the application's own window.

Both consume the same service layer, so neither holds business logic. The
:mod:`vocabulary_trainer.ui.theme` package generates styling for both from one set of
design tokens.
"""
