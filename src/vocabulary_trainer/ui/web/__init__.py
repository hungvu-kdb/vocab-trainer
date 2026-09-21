"""Web-rendered windows: Practice and Settings.

These screens are document-like and layout-heavy, and they already exist as HTML in
``mockup/``. Rendering that markup directly inside a ``QWebEngineView`` is what makes
strict visual fidelity achievable without hand-building every card in Qt, and it
removes any translation step between the design and the implementation.

No HTTP server, no browser process, no ``localhost``: content loads from local files
inside the application's own window. The boundary to Python is a ``QWebChannel``
bridge that carries data and calls only -- never decisions.
"""
