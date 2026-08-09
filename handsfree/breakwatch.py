"""Break reminder — nag when the shoulders and hips stop moving.

Demo-tuned on purpose: the stillness window is 30 SECONDS, not 20 minutes,
because it has to fire in front of people. Standing up (a real burst of
movement) resets the timer within ~3 seconds.

Nicholas's pose loop feeds this once per frame with normalized landmark
coordinates; headless testing feeds it synthetic ones. The tracker itself
never touches the camera — that keeps it on Fatima's side of the seam.

    tracker = StillnessTracker(window_s=30.0)
    if tracker.update(shoulders_hips_xy, now):   # True once per still-period
        fire("break_prompt")
"""
from __future__ import annotations

import math
import sys

STILL_WINDOW_S = 30.0
# Mean landmark movement (normalized units/frame) below this counts as still.
STILL_EPS = 0.004
# One frame moving faster than this is a deliberate move (standing up) and
# resets immediately — this is what makes the reset land within 3 s.
BURST_EPS = 0.02


class StillnessTracker:
    def __init__(self, window_s: float = STILL_WINDOW_S,
                 still_eps: float = STILL_EPS, burst_eps: float = BURST_EPS):
        self.window_s = window_s
        self.still_eps = still_eps
        self.burst_eps = burst_eps
        self._prev: list[tuple[float, float]] | None = None
        self._still_since: float | None = None
        self._fired = False

    def update(self, points: list[tuple[float, float]], now: float) -> bool:
        """Feed shoulder+hip (x, y) points; returns True the moment the
        stillness window is exceeded (once per still-period)."""
        if self._prev is None or len(points) != len(self._prev):
            self._prev = points
            self._still_since = now
            return False

        move = sum(math.dist(p, q) for p, q in zip(points, self._prev)) / len(points)
        self._prev = points

        if move > self.burst_eps or move > self.still_eps:
            # any real movement resets; a burst is just very obviously real
            self._still_since = now
            self._fired = False
            return False

        if self._still_since is None:
            self._still_since = now
        if not self._fired and now - self._still_since >= self.window_s:
            self._fired = True
            return True
        return False

    @property
    def still_for(self) -> float | None:
        return None if self._still_since is None else self._still_since


def break_prompt() -> None:
    """The break_prompt word: put a reminder in front of the user."""
    msg = "You haven't moved in a while — stand up, roll the shoulders."
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title("Take a break")
        root.attributes("-topmost", True)
        root.geometry("+120+120")
        tk.Label(root, text=msg, font=("Segoe UI", 14), padx=24, pady=18).pack()
        tk.Button(root, text="OK, moving", command=root.destroy, padx=12).pack(pady=(0, 16))
        root.bind("<Escape>", lambda e: root.destroy())
        root.after(8000, root.destroy)  # never blocks the demo for long
        root.mainloop()
    except Exception:
        print(f"\a[break] {msg}", file=sys.stderr)
