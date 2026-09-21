"""Persistence.

Three stores with deliberately different failure postures:

* :mod:`master_file_repository` -- the Excel workbook, the system of record. Every
  write is atomic and serialized; failures surface as typed errors the UI must
  handle, because losing a write here loses a user's vocabulary.
* :mod:`preferences_store` -- JSON settings. A failure degrades quietly.
* :mod:`history_store` -- JSON practice results. A failure degrades quietly and
  must never block the summary screen from displaying.
"""
