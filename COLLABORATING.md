# Working on this with two people

Two tracks, one repo, one trunk. Nicholas turns camera pixels into a **word**;
Fatima turns that word into **something happening**. You meet at the string and
nowhere else.

## The one-time setup

The plan docs point at `Nicohlutta/handsfree-hci`, but this checkout's origin is
`techeiFatima/HandsFree`. **Pick one repo and both work in it.** Two repos that
each hold half the project is the failure this file exists to prevent.

Whoever owns the chosen repo adds the other as a collaborator:

> Repo → **Settings** → **Collaborators and teams** → **Add people** →
> invite them → they accept from their GitHub notifications or email.

Until that invite is accepted, the other person can read but **cannot push**, and
your work does not reach them no matter how often you commit.

## The daily loop

The plan says no branches: commit to the trunk often and push. That only works
if you **pull before you push**, every time.

```bash
git pull --rebase origin main     # take their work first
# ... do your bit, run the tests ...
git add -A && git commit -m "what changed and why"
git push origin main
```

`--rebase` keeps the history a straight line instead of littering it with merge
commits every twenty minutes. If a push is rejected, someone pushed while you
were working: pull again, then push. Never `--force` a shared branch — that
deletes their commits.

Every ~20 minutes is the right rhythm. A commit that sits on your laptop is a
commit your teammate cannot build on, and at 18:15 it is worth nothing.

## File ownership — the rule that makes this work

| Owner | Files |
|---|---|
| Nicholas — perception | `sources.py`, `gestures.py`, `cursor.py` |
| Fatima — actuation | `actions/`, `beats.py`, `breakwatch.py`, `ui.py` |
| Either, carefully | `safety.py`, `README.md`, the HTML plan pages |

**Don't edit the other person's files — ask.** Two people editing one file
twenty minutes before a freeze is how you lose work. If you genuinely must,
say so in the commit message so it isn't a surprise.

`safety.py` is the exception worth naming: it is Nicholas's, but it is also the
kill switch that protects both of you, so a change there should be mentioned out
loud rather than merely pushed.

## The seam, so neither of you is ever blocked

Nicholas emits one of these strings; Fatima's registry runs it. Fixed, never
renamed:

```
mute_toggle  media_playpause  privacy_blank  privacy_restore
playlist_open  led_beat_start  led_beat_stop  break_prompt
```

Neither side needs the other to be finished:

```bash
# Fatima, with no camera:
python -m handsfree.actions --fire mute_toggle

# Nicholas, with no actions: print the word instead of firing it,
# then swap in the real call when you're ready.
from handsfree.actions import fire
fire(word)
```

If a word needs to change, change it **here first**, tell the other person, and
only then touch code. A renamed string is a gesture that silently fires nothing.

## Before you push

```bash
python -m pytest tests/ -q        # 43 tests, no camera/board/display needed
```

A red test on the trunk blocks both of you, so run them before pushing, not
after.
