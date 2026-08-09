"""Break reminder — nag when the shoulders and hips stop moving.

Demo-tuned on purpose: the stillness window is 30 SECONDS, not 20 minutes,
because it has to fire in front of people. Standing up resets it well inside
3 seconds.

How stillness is measured, and why this way:

  The tracked quantity is the SHOULDER-HIP MIDPOINT — one point summarising
  where the torso is — accumulated over a rolling one-second window.

  The metric is that midpoint's EXCURSION over the window: how far it strays
  from its own average position. Not the path length it travels. Landmark
  noise makes the midpoint jiggle, and a jiggling point accumulates path
  length forever without going anywhere — at 60 fps it racks up twice the
  path of 30 fps while describing the identical stillness. Excursion doesn't
  care how often you sample: noise of amplitude a reads as a at any frame
  rate, while a torso that actually moved reads as the distance it moved.
  That makes one threshold correct on any machine, which matters because the
  demo laptop and the dev laptop don't run the camera at the same rate.

The tracker never touches the camera — Nicholas's pose loop feeds it landmark
coordinates and the tests feed it synthetic ones, which keeps it on Fatima's
side of the seam and testable with no webcam.

    tracker = StillnessTracker()
    if tracker.update(shoulder_and_hip_points, now):   # True once per still period
        fire("break_prompt")
"""
from __future__ import annotations

import math
import sys
from collections import deque

STILL_WINDOW_S = 30.0
# Midpoint excursion (normalized frame units) over ENERGY_WINDOW_S, below which
# the torso counts as still. Measured on synthetic landmarks: sensor noise
# lands near 0.001, breathing near 0.005, typing/leaning near 0.02, standing up
# above 0.2. 0.01 sits in the gap and holds at 15, 30 and 60 fps.
STILL_EXCURSION = 0.01
ENERGY_WINDOW_S = 1.0


class StillnessTracker:
    """Rolling-excursion stillness detector over shoulder/hip landmarks."""

    def __init__(self, window_s: float = STILL_WINDOW_S,
                 still_excursion: float = STILL_EXCURSION,
                 energy_window_s: float = ENERGY_WINDOW_S):
        self.window_s = window_s
        self.still_excursion = still_excursion
        self.energy_window_s = energy_window_s
        self._track: deque[tuple[float, tuple[float, float]]] = deque()
        self._still_since: float | None = None
        self._fired = False
        self._n_points: int | None = None

    @staticmethod
    def _midpoint(points: list[tuple[float, float]]) -> tuple[float, float]:
        """The shoulder-hip midpoint: the mean of the tracked landmarks."""
        n = len(points)
        return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)

    def _excursion(self, t: float, mid: tuple[float, float]) -> float:
        """How far the midpoint strays from its own mean over the window."""
        self._track.append((t, mid))
        cutoff = t - self.energy_window_s
        while len(self._track) > 1 and self._track[0][0] < cutoff:
            self._track.popleft()

        n = len(self._track)
        cx = sum(p[0] for _, p in self._track) / n
        cy = sum(p[1] for _, p in self._track) / n
        return max(math.dist(p, (cx, cy)) for _, p in self._track)

    def update(self, points: list[tuple[float, float]], now: float) -> bool:
        """Feed this frame's shoulder+hip (x, y) landmarks.

        Returns True the moment the stillness window is exceeded — once per
        still period, so it nags you once rather than every frame after 30 s.
        """
        if not points:
            return False

        # A changed landmark count means the pose was lost and reacquired; the
        # old track is about a different set of points and would read as a jump.
        if self._n_points is not None and len(points) != self._n_points:
            self.reset(now)
        self._n_points = len(points)

        # A gap in the feed (pose lost, camera stalled, laptop slept) is time we
        # did not observe. It cannot be counted as stillness — the person may
        # have got up and sat back down — so treat it as movement and restart.
        if self._track and now - self._track[-1][0] > self.energy_window_s:
            self.reset(now)

        excursion = self._excursion(now, self._midpoint(points))

        # Not enough history yet to call it either way.
        if now - self._track[0][0] < self.energy_window_s * 0.5:
            return False

        if excursion > self.still_excursion:
            self._still_since = None
            self._fired = False
            return False

        if self._still_since is None:
            self._still_since = now
            return False

        if not self._fired and now - self._still_since >= self.window_s:
            self._fired = True
            return True
        return False

    def reset(self, now: float | None = None) -> None:
        self._track.clear()
        self._still_since = None
        self._fired = False

    def still_for(self, now: float) -> float:
        """Seconds of continuous stillness so far (0.0 while moving)."""
        return 0.0 if self._still_since is None else max(0.0, now - self._still_since)

    @property
    def is_still(self) -> bool:
        return self._still_since is not None


def break_prompt() -> None:
    """The break_prompt word: put a reminder in front of the user.

    Auto-dismisses after 8 s and never blocks the caller — a modal nag that
    swallowed the gesture loop mid-pitch would be worse than no reminder.
    """
    msg = "You haven't moved in a while — stand up, roll your shoulders."

    def build(root) -> None:
        import tkinter as tk
        win = tk.Toplevel(root)
        win.title("Take a break")
        win.attributes("-topmost", True)
        win.geometry("+120+120")
        tk.Label(win, text=msg, font=("Segoe UI", 14), padx=26, pady=18).pack()
        tk.Button(win, text="OK, moving", command=win.destroy, padx=12).pack(pady=(0, 16))
        win.bind("<Escape>", lambda e: win.destroy())
        win.after(8000, lambda: win.winfo_exists() and win.destroy())

    from handsfree import ui
    if not ui.submit(build):
        print(f"\a[break] {msg}", file=sys.stderr)
