"""Command-line entry point: ``python -m vocabulary_trainer``."""

from __future__ import annotations

import sys

from vocabulary_trainer.app import main

if __name__ == "__main__":
    sys.exit(main())
