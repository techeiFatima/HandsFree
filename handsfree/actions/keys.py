"""mute_toggle and media_playpause — system media keys, sent from code.

Both go through system-level keys so they work with Zoom (or any player)
minimised, which is the case that matters on stage.

Why this file knows about platforms
-----------------------------------
Media keys are the least portable thing in the project.

  Windows / Linux   pyautogui's "volumemute" and "playpause" names work.

  macOS             "volumemute" exists in pyautogui's key table but is sent as
                    an ordinary keystroke of kVK_Mute, which modern macOS
                    largely ignores; "playpause" is not in the macOS table at
                    all. And pyautogui's _keyDown returns silently for a key it
                    does not know -- no exception, nothing pressed. So on a Mac
                    the naive version reports success and does nothing, which is
                    the worst failure there is.

                    The route that does work is an NSSystemDefined event, and
                    pyautogui already implements exactly that for its own use
                    (_specialKeyEvent, KEYTYPE_MUTE=7, KEYTYPE_PLAY=16) -- it
                    simply never wires those to key names. So we call it
                    directly rather than reimplementing NSEvent handling.

Zoom's mute shortcut differs too: Alt+A on Windows and Linux, Cmd+Shift+A on
macOS. Sending the wrong one is silent, so it is a table, not an assumption.

Prerequisite, done once by hand: Zoom -> Settings -> Keyboard Shortcuts ->
Mute/Unmute My Audio -> tick "Enable Global Shortcut". Without it the shortcut
only works while Zoom is focused and the feature looks broken.

macOS also gates all of this behind Privacy & Security -> Accessibility. Until
this app is ticked there, every key below silently does nothing.
"""
from __future__ import annotations

import sys

# Zoom's global mute chord, per platform.
ZOOM_MUTE_CHORD = {
    "darwin": ("command", "shift", "a"),
}
ZOOM_MUTE_DEFAULT = ("alt", "a")

# macOS NSSystemDefined key names, from pyautogui's own table.
MAC_MUTE = "KEYTYPE_MUTE"
MAC_PLAYPAUSE = "KEYTYPE_PLAY"


def is_mac(platform: str | None = None) -> bool:
    return (platform or sys.platform) == "darwin"


def zoom_chord(platform: str | None = None) -> tuple[str, ...]:
    return ZOOM_MUTE_CHORD.get(platform or sys.platform, ZOOM_MUTE_DEFAULT)


def _press(*keys: str) -> None:
    """Send a key or chord through pyautogui."""
    import pyautogui
    if len(keys) == 1:
        pyautogui.press(keys[0])
    else:
        pyautogui.hotkey(*keys)


def _mac_media(name: str) -> None:
    """Send a macOS media key as an NSSystemDefined event.

    Reuses pyautogui's implementation rather than rebuilding it: same code path
    their own special keys take, so it stays correct if they fix a bug in it.
    """
    from pyautogui import _pyautogui_osx as osx
    osx._specialKeyEvent(name, "down")
    osx._specialKeyEvent(name, "up")


def mute_toggle() -> None:
    """Toggle the system mute, then Zoom's own shortcut so the mic mutes too."""
    if is_mac():
        _mac_media(MAC_MUTE)
    else:
        _press("volumemute")

    chord = zoom_chord()
    try:
        _press(*chord)
    except Exception as exc:
        # Zoom's half failing must not lose the system mute we already sent.
        print(f"[keys] Zoom chord {'+'.join(chord)} failed ({exc!r}) — "
              f"system mute still sent", file=sys.stderr)


def media_playpause() -> None:
    """Toggle whatever media player last played, focused or not."""
    if is_mac():
        _mac_media(MAC_PLAYPAUSE)
    else:
        _press("playpause")
