# Working on this with two people

Two tracks, one repo, one trunk. Nicholas turns camera pixels into a **word**;
Fatima turns that word into **something happening**. You meet at the string and
nowhere else.

## The one-time setup

**The shared repo is `Nicohlutta/handsfree-hci`.** That is the decision — it is
also what every plan doc already says. `techeiFatima/HandsFree` is where Track B
was built and currently holds the newer code; it becomes a working copy once the
move below is done.

### Step 1 — Nicholas invites Fatima

> `Nicohlutta/handsfree-hci` → **Settings** → **Collaborators and teams** →
> **Add people** → invite `techeiFatima` → she accepts from her GitHub
> notifications or email.

Until that invite is accepted, Fatima can read but **cannot push**, and no amount
of committing gets her work to him. This is the actual blocker; nothing else in
this file works without it.

### Step 2 — Fatima pushes Track B over to his repo

From a clone of `techeiFatima/HandsFree`, with `main` up to date:

```bash
git remote add upstream https://github.com/Nicohlutta/handsfree-hci
git fetch upstream
git checkout -b track-b main
git push upstream track-b
```

Then open a pull request on his repo from `track-b`, so he can look over the
`safety.py` change before it lands on his trunk.

Push a **branch**, not straight to his `main`. If his repo grew from a separate
starting point, its history and this one may not share an ancestor, and pushing
`main` directly would either be rejected or clobber his work. A branch plus a PR
shows you which it is before anything is at risk. If GitHub says the branches
have unrelated histories, stop and sort that out together rather than forcing it.

### Step 3 — repoint your clone

Once the PR is merged, his repo is the trunk. Make `origin` point at it so the
daily loop below just works:

```bash
git remote set-url origin https://github.com/Nicohlutta/handsfree-hci
git fetch origin && git checkout main && git reset --hard origin/main
```

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
