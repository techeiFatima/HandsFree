"""The --fire command line — Fatima's camera until the real one works.

    python -m handsfree --fire test_ping
    python -m handsfree --fire mute_toggle
    python -m handsfree --list
"""
from __future__ import annotations

import argparse
import sys

from handsfree.actions import ACTIONS, fire


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m handsfree", description=__doc__)
    ap.add_argument("--fire", metavar="WORD", help="fire one action word")
    ap.add_argument("--list", action="store_true", help="list the action words")
    args = ap.parse_args(argv)

    if args.list or not args.fire:
        for word in ACTIONS:
            print(word)
        return 0
    return 0 if fire(args.fire) else 1


if __name__ == "__main__":
    sys.exit(main())
