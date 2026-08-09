"""playlist_open — start the demo song in the default media player.

The song lives in the repo at media/beat_track.wav so the demo never depends
on a network, a streaming login, or someone's personal library. It's a
synthesized 120 BPM track with a hard four-on-the-floor kick — chosen so the
LED reads from across the room. To swap in a real song, drop the file in
media/ and point SONG at it (beats.py re-extracts beat times automatically).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SONG = Path(__file__).resolve().parents[2] / "media" / "beat_track.wav"


def playlist_open(song: Path | str = SONG) -> None:
    """Hand the song to the OS default player. Never blocks."""
    song = Path(song)
    if not song.exists():
        raise FileNotFoundError(
            f"song missing: {song} — run python -m handsfree.make_demo_track")
    if sys.platform == "win32":
        os.startfile(song)                                  # noqa: S606 — non-blocking
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(song)])
    else:
        try:
            subprocess.Popen(["xdg-open", str(song)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            # Headless box with no xdg-open: the beat scheduler still runs, so
            # timing stays testable. Say so rather than dying.
            print("[playlist] no desktop player available — pulses only",
                  file=sys.stderr)
            return
    print(f"[playlist] playing {song.name}")
