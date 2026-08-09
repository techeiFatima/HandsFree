"""Guided self-test — walk every action, one keypress each.

This is where you actually test the product. It is not a website and cannot be
one: the whole point is moving the real cursor, muting Zoom while Zoom is
minimised, and covering the real screen. A browser tab is sandboxed out of all
three.

    python -m handsfree.selftest              # guided, asks after each step
    python -m handsfree.selftest --auto       # fire everything, ask nothing
    python -m handsfree.selftest --only mute  # just the mute checks

Before you start: CTRL+ALT+Q kills the process from anywhere. If anything gets
away from you — a black screen that won't lift, music you can't stop — that is
the way out. Learn it before the first step, not during it.

Pass criteria come from bench-plan.html. The summary at the end tells you which
ones you just confirmed by eye and which still need a phone or the board.
"""
from __future__ import annotations

import argparse
import sys
import time

from handsfree.actions import fire

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
OK = "\033[32m"
NO = "\033[31m"
WARN = "\033[33m"


class Step:
    def __init__(self, key: str, title: str, expect: str, criterion: str,
                 run, setup: str = "", teardown=None):
        self.key = key
        self.title = title
        self.expect = expect
        self.criterion = criterion
        self.run = run
        self.setup = setup
        self.teardown = teardown


def _mute_check() -> None:
    print(f"{DIM}    firing mute_toggle 5 times, 1.5 s apart{RESET}")
    for i in range(5):
        fire("mute_toggle")
        time.sleep(1.5)


def _beats_check() -> None:
    from handsfree.beats import led_beat_start, led_beat_stop
    led_beat_start()
    print(f"{DIM}    running 20 s — watch for drift between dot and music{RESET}")
    time.sleep(20)
    led_beat_stop()


def _privacy_check() -> None:
    fire("privacy_blank")
    print(f"{DIM}    screen should be black. Press Esc to bring it back.{RESET}")
    time.sleep(6)
    fire("privacy_restore")


STEPS = [
    Step("ping", "The seam is alive",
         "a 'pong' line prints below",
         "--fire test_ping prints something",
         lambda: fire("test_ping")),

    Step("mute", "Mute, with Zoom minimised",
         "the mute indicator on your PHONE flips 5 times",
         "under 500 ms, 5/5, with Zoom not focused",
         _mute_check,
         setup="Join a test meeting from your phone, then MINIMISE Zoom. "
               "That is the case that matters."),

    Step("play", "Media play/pause",
         "music stops (or starts)",
         "toggles without the player focused",
         lambda: fire("media_playpause"),
         setup="Have something playing."),

    Step("privacy", "Privacy blank",
         "every screen goes black within a second, and Esc lifts it",
         "covers <1 s, Esc dismisses, Ctrl+Alt+Q still works underneath",
         _privacy_check,
         setup="If you have a second monitor, watch THAT one too."),

    Step("playlist", "Playlist",
         "the demo track starts in your default player",
         "firing the word starts music",
         lambda: fire("playlist_open")),

    Step("beats", "LED and dot on the beat",
         "the dot pulses in time; the LED too if the board is plugged in",
         "still on the beat after 20 s, no drift",
         _beats_check,
         setup="The board is found automatically; set HANDSFREE_LED_PORT to override. "
               "Film this one on your phone and watch it back."),

    Step("break", "Break reminder",
         "a 'stand up' window appears",
         "fires at 30 s of stillness, resets within 3 s of moving",
         lambda: fire("break_prompt")),
]


def ask(prompt: str) -> bool | None:
    try:
        while True:
            a = input(f"    {BOLD}{prompt}{RESET} [y/n/s=skip] ").strip().lower()
            if a in ("y", "yes"):
                return True
            if a in ("n", "no"):
                return False
            if a in ("s", "skip", ""):
                return None
    except (EOFError, KeyboardInterrupt):
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Guided self-test for the hands-free actions.")
    ap.add_argument("--auto", action="store_true",
                    help="fire everything without asking (no verdicts)")
    ap.add_argument("--only", metavar="KEY", nargs="+",
                    help=f"run only these steps: {' '.join(s.key for s in STEPS)}")
    args = ap.parse_args(argv)

    steps = [s for s in STEPS if not args.only or s.key in args.only]
    if not steps:
        print(f"no such step. choose from: {' '.join(s.key for s in STEPS)}", file=sys.stderr)
        return 2

    try:
        from handsfree.safety import arm
        arm()
    except Exception as exc:
        print(f"{WARN}[selftest] kill switch NOT armed ({exc!r}).{RESET}", file=sys.stderr)
        print(f"{WARN}          pyautogui/pynput missing — install them before the demo.{RESET}",
              file=sys.stderr)

    print(f"\n{BOLD}Hands-free self-test{RESET}")
    print(f"{DIM}CTRL+ALT+Q kills this from anywhere. Learn it now.{RESET}\n")

    results: list[tuple[Step, bool | None]] = []
    for i, step in enumerate(steps, 1):
        print(f"{BOLD}{i}/{len(steps)}  {step.title}{RESET}")
        if step.setup:
            print(f"{DIM}    setup: {step.setup}{RESET}")
        print(f"{DIM}    expect: {step.expect}{RESET}")
        if not args.auto:
            try:
                input(f"    {DIM}enter to fire, Ctrl+C to stop{RESET} ")
            except (EOFError, KeyboardInterrupt):
                print("\nstopped.")
                break
        try:
            step.run()
        except Exception as exc:
            print(f"    {NO}raised: {exc!r}{RESET}")
            results.append((step, False))
            continue

        verdict = None if args.auto else ask("Did that happen?")
        results.append((step, verdict))
        print()

    print(f"\n{BOLD}Summary{RESET}  {DIM}(pass criteria from bench-plan.html){RESET}")
    width = max((len(s.title) for s, _ in results), default=10)
    for step, verdict in results:
        mark = (f"{OK}PASS{RESET}" if verdict is True else
                f"{NO}FAIL{RESET}" if verdict is False else f"{WARN}  ? {RESET}")
        print(f"  {mark}  {step.title.ljust(width)}  {DIM}{step.criterion}{RESET}")

    failed = [s.title for s, v in results if v is False]
    unknown = [s.title for s, v in results if v is None]
    print()
    if failed:
        print(f"{NO}{len(failed)} failed:{RESET} {', '.join(failed)}")
    if unknown:
        print(f"{WARN}{len(unknown)} unconfirmed:{RESET} {', '.join(unknown)}")
    if not failed and not unknown:
        print(f"{OK}Everything confirmed by eye.{RESET}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
