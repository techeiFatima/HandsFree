"""The --fire command line — Fatima's camera until the real one works.

This is the entrypoint named in the plan and on the task board:

    python -m handsfree.actions --fire mute_toggle
    python -m handsfree.actions --fire test_ping
    python -m handsfree.actions --list
    python -m handsfree.actions --fire privacy_blank --hold 5

--hold keeps the process alive after firing, which the windowed actions need:
the privacy blank and the beat dot live on a daemon UI thread, so without it
the process would exit and take the window with it.
"""
from __future__ import annotations

import argparse
import sys
import time

from handsfree.actions import ACTIONS, WORDS, fire


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m handsfree.actions",
        description="Fire an action word without a camera.")
    ap.add_argument("--fire", metavar="WORD", help="fire one action word")
    ap.add_argument("--list", action="store_true", help="list every action word")
    ap.add_argument("--hold", type=float, default=0.0, metavar="SECONDS",
                    help="stay alive after firing, so windows stay up")
    ap.add_argument("--repeat", type=int, default=1, metavar="N",
                    help="fire N times (the bench tests ask for 5x and 10x)")
    ap.add_argument("--interval", type=float, default=1.0, metavar="SECONDS",
                    help="gap between repeats")
    args = ap.parse_args(argv)

    if args.list or not args.fire:
        contracted = set(WORDS)
        for word in ACTIONS:
            tag = "" if word in contracted else "   (extra)"
            print(f"{word}{tag}")
        return 0

    ok = True
    for i in range(max(1, args.repeat)):
        if i:
            time.sleep(args.interval)
        ok = fire(args.fire) and ok

    if args.hold:
        print(f"[actions] holding {args.hold:.0f}s — Ctrl+C to quit", file=sys.stderr)
        try:
            time.sleep(args.hold)
        except KeyboardInterrupt:
            pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
