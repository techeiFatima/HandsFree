"""The action registry — Fatima's half of the seam.

Nicholas's code turns the camera into a word. This package turns that word into
something happening on the laptop. The two halves only touch here, which is why
neither of us ever waits for the other.

The words, fixed and never renamed:

    mute_toggle      media_playpause   privacy_blank    privacy_restore
    playlist_open    led_beat_start    led_beat_stop    break_prompt

Fire one from code:

    from handsfree.actions import fire
    fire("mute_toggle")

or straight from the terminal — this is the camera until the real one works:

    python -m handsfree.actions --fire mute_toggle
    python -m handsfree.actions --list
"""
from __future__ import annotations

import importlib
import sys
import time

# The contract with Nicholas. Order is the demo order, not alphabetical.
WORDS = (
    "mute_toggle",
    "media_playpause",
    "privacy_blank",
    "privacy_restore",
    "playlist_open",
    "led_beat_start",
    "led_beat_stop",
    "break_prompt",
)


def test_ping() -> None:
    """Prove the word→action seam is alive. The first thing that ever ran."""
    print(f"[actions] pong @ {time.strftime('%H:%M:%S')} — the seam works")


def _lazy(module: str, name: str):
    """Import an action's dependencies only when it is actually fired.

    Tk, pyautogui, librosa and pyserial are all optional in some environment we
    might end up demoing from. Importing them at registry-build time would mean
    one missing wheel takes down every word, including the ones that don't need
    it.
    """
    def run(*args, **kwargs):
        return getattr(importlib.import_module(module), name)(*args, **kwargs)
    run.__name__ = name
    run.__doc__ = f"{module}.{name} (imported on first use)"
    return run


ACTIONS = {
    "test_ping":       test_ping,
    "mute_toggle":     _lazy("handsfree.actions.keys", "mute_toggle"),
    "media_playpause": _lazy("handsfree.actions.keys", "media_playpause"),
    "privacy_blank":   _lazy("handsfree.actions.privacy", "privacy_blank"),
    "privacy_restore": _lazy("handsfree.actions.privacy", "privacy_restore"),
    "privacy_toggle":  _lazy("handsfree.actions.privacy", "privacy_toggle"),
    "playlist_open":   _lazy("handsfree.actions.playlist", "playlist_open"),
    "led_beat_start":  _lazy("handsfree.beats", "led_beat_start"),
    "led_beat_stop":   _lazy("handsfree.beats", "led_beat_stop"),
    "break_prompt":    _lazy("handsfree.breakwatch", "break_prompt"),
}

# Every contracted word must be registered. Catching a typo here at import time
# is much cheaper than catching it when a gesture fires into nothing at 20:00.
_missing = [w for w in WORDS if w not in ACTIONS]
if _missing:
    raise RuntimeError(f"registry is missing contracted words: {_missing}")


def fire(word: str) -> bool:
    """Fire one word. True if it ran, False if unknown or it raised.

    An action's exception is caught and reported, never propagated: a feature
    misfiring must not take down the gesture loop that called it.
    """
    fn = ACTIONS.get(word)
    if fn is None:
        print(f"[actions] unknown word {word!r}. Known: {' '.join(ACTIONS)}",
              file=sys.stderr)
        return False
    t0 = time.perf_counter()
    try:
        fn()
    except Exception as exc:
        print(f"[actions] {word} failed: {exc!r}", file=sys.stderr)
        return False
    print(f"[actions] {word} in {(time.perf_counter() - t0) * 1e3:.0f} ms",
          file=sys.stderr)
    return True
