"""N1 test rig — a deliberately runaway cursor.

This simulates the exact failure the kill switch exists for: something owns the
mouse and will not give it back. Run it, then take the machine back.

    python -m handsfree.runaway

    Ctrl+Alt+Q            kills it
    cursor into a corner  kills it (pyautogui failsafe)

It walks a small circle around wherever your cursor already is, so it does not
fling the pointer across the screen while you are still reading this.

PASS: the cursor stops and the process exits within 200 ms, 3 times out of 3,
including once while a dialog box has focus.
"""
from __future__ import annotations

import math
import sys
import time

from handsfree.safety import arm


def main(radius: int = 90, hz: float = 60.0) -> None:
    import pyautogui

    arm()

    cx, cy = pyautogui.position()
    print(f"[runaway] hijacking the cursor around ({cx}, {cy}).")
    print("[runaway] TAKE IT BACK: Ctrl+Alt+Q, or slam into a screen corner.\n",
          file=sys.stderr)
    time.sleep(1.5)

    step = 1.0 / hz
    t = 0.0
    while True:
        x = cx + radius * math.cos(t)
        y = cy + radius * math.sin(t)
        try:
            pyautogui.moveTo(int(x), int(y), _pause=False)
        except pyautogui.FailSafeException:
            print("\n[KILL] failsafe corner reached — exiting", file=sys.stderr)
            raise SystemExit(1)
        t += 0.12
        time.sleep(step)


if __name__ == "__main__":
    main()
