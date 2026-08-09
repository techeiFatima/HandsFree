"""mute_toggle and media_playpause — the hardware media keys, sent from code.

Both use system-level keys so they work with Zoom (or anything) minimised —
that's the case that matters on stage. mute_toggle also sends Alt+A, Zoom's
own global mute shortcut, so the Zoom mic mutes and not just the speakers.

Prerequisite (done once, by hand): Zoom → Settings → Keyboard Shortcuts →
Mute/Unmute My Audio → tick "Enable Global Shortcut". Without it Alt+A only
works while Zoom has focus and the feature looks broken.
"""
from __future__ import annotations

import sys


def _press(*keys: str) -> None:
    import pyautogui
    if len(keys) == 1:
        pyautogui.press(keys[0])
    else:
        pyautogui.hotkey(*keys)


def mute_toggle() -> None:
    """Toggle the OS volume mute, then Alt+A so Zoom's mic mutes too."""
    _press("volumemute")
    try:
        _press("alt", "a")   # Zoom global mute — needs the shortcut enabled
    except Exception as exc:
        print(f"[keys] Alt+A failed ({exc!r}) — OS mute still sent", file=sys.stderr)


def media_playpause() -> None:
    """Toggle whatever media player last played, focused or not."""
    _press("playpause")
