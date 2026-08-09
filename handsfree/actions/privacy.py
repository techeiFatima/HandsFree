"""privacy_blank / privacy_restore — a fullscreen, always-on-top black window.

The desk-visitor moment: finger to lips, or an open palm sweep, and the screen
is black before the visitor has finished walking over.

Second-monitor decision (made now, not discovered on stage): the blank covers
EVERY attached screen. A blank that only covers the laptop while the projector
still shows your inbox is not a privacy feature. One Toplevel is created per
monitor, positioned over it; with a single screen this collapses to exactly the
Tk Toplevel + -fullscreen + -topmost the plan asks for.

Safety, non-negotiable: Esc dismisses. A topmost black window with no keyboard
escape locks the laptop in front of the whole room. Ctrl+Alt+Q also still works
underneath, because safety.arm() reads raw keyboard events through pynput,
which sees keys whatever window holds focus.

Runs on the shared UI thread (handsfree.ui), so firing it never blocks the
gesture loop and privacy_restore can always get through.
"""
from __future__ import annotations

import sys
import threading

from handsfree import ui

_windows: list = []
_lock = threading.Lock()


def _monitor_boxes() -> list[tuple[int, int, int, int]]:
    """(x, y, w, h) per monitor. Falls back to one primary-screen box."""
    try:
        from screeninfo import get_monitors
        boxes = [(m.x, m.y, m.width, m.height) for m in get_monitors()]
        if boxes:
            return boxes
    except Exception:
        pass
    return []


def _build(root) -> None:
    import tkinter as tk

    with _lock:
        if _windows:
            return                      # already blanked

        boxes = _monitor_boxes()
        if not boxes:                   # single screen, or screeninfo missing
            boxes = [(0, 0, root.winfo_screenwidth(), root.winfo_screenheight())]

        for x, y, w, h in boxes:
            win = tk.Toplevel(root)
            win.configure(background="black")
            win.overrideredirect(True)  # no title bar on the secondary screens
            win.geometry(f"{w}x{h}+{x}+{y}")
            if len(boxes) == 1:
                win.attributes("-fullscreen", True)
            win.attributes("-topmost", True)
            win.config(cursor="none")
            # Esc dismisses — mandatory, bound on every window so whichever one
            # holds focus can take it down.
            win.bind("<Escape>", lambda e: privacy_restore())
            _windows.append(win)

        _windows[0].focus_force()


def _teardown(root) -> None:
    with _lock:
        for win in _windows:
            try:
                win.destroy()
            except Exception:
                pass
        _windows.clear()


def privacy_blank() -> None:
    """Cover every screen with black. Esc or privacy_restore brings it back."""
    if not ui.submit(_build):
        print("[privacy] headless — would blank every screen now", file=sys.stderr)


def privacy_restore() -> None:
    """Take the black cover down."""
    if not ui.submit(_teardown):
        print("[privacy] headless — would restore now", file=sys.stderr)


def privacy_toggle() -> None:
    """Open-palm sweep: black if visible, back if not."""
    privacy_restore() if _windows else privacy_blank()
