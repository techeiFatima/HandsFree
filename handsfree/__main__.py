"""Alias for `python -m handsfree.actions` — the plan names both spellings.

    python -m handsfree --fire mute_toggle
"""
from __future__ import annotations

import sys

from handsfree.actions.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
