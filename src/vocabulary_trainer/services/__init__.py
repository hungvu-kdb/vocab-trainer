"""Orchestration: the only layer the UI is permitted to call.

Each service owns one user-facing capability area, coordinates domain rules with the
data and integration layers, and imports nothing from ``ui``. That one-way
dependency is what lets both UI technologies -- Qt widgets and the web-rendered
windows -- consume identical behaviour instead of growing divergent copies of it.

Errors are translated here: raw file-system, HTTP, and library exceptions never
reach the UI.
"""
