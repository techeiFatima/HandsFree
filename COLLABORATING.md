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

### Step 0 — check you are in the right repository

Git commands run against whatever repo contains your current directory, and it
will happily let you add a remote, branch, and push from the wrong one. If your
home folder is itself a git repo — which is easy to do by accident and easy not
to notice — then every `git` command you type in a fresh terminal runs against
*that*, not against this project.

```bash
git rev-parse --show-toplevel
git remote -v
```

The first should print the path of your HandsFree clone, **not** your home
directory. The second should mention `HandsFree`. If either looks wrong, `cd`
into the clone first; if you have not cloned it yet:

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/techeiFatima/HandsFree.git
cd HandsFree
```

If your home directory really is a git repo for something else, it is worth
untangling separately — `git add -A` run there would stage your entire home
folder, keys and all.

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

Once the PR is merged, his repo is the trunk, so `origin` should mean his repo
and the daily loop below just works.

**Rename the remote, don't `reset --hard`.** Renaming keeps your old repo
reachable as a fallback, and `pull --rebase` replays any local commits you had
not pushed yet on top of his history. `git reset --hard origin/main` deletes
them without asking — tested, and it really does lose the work.

> **Paste these without the surrounding prose.** Interactive zsh — the default
> shell on macOS — does not treat `#` as a comment, so a trailing
> `# like this` is handed to git as an argument and you get
> `fatal: ambiguous argument '#'`. Nothing is harmed, but the command does not
> run. Every block below is therefore comment-free and safe to paste whole.

**1. Look before you leap.** Commit or stash anything the first command lists;
anything the second lists is committed but not yet pushed.

```bash
git status
git log --oneline origin/main..main
```

**2. Make `origin` mean his repo.** Your own repo survives as `myfork`.

```bash
git remote rename origin myfork
git remote add origin https://github.com/Nicohlutta/handsfree-hci
git fetch origin
```

**3. Point `main` at his `main` and take his work.**

```bash
git checkout main
git branch -u origin/main main
git pull --rebase origin main
```

**4. Confirm.** `origin` should be his repo, and the log should show his commits
and yours in one straight line.

```bash
git remote -v
git log --oneline -5
```

If step 3 stops with `refusing to merge unrelated histories`, the two repos grew
from different starting points. Do **not** pass `--allow-unrelated-histories` to
get past it — work out with Nicholas which trunk is real first, because forcing
it merges two parallel versions of the same project into one tree.

Should anything go wrong, nothing is lost: `git remote -v` still lists `myfork`,
and `git reflog` still has where you were. To back all the way out,
`git fetch myfork && git reset --hard myfork/main`.

## The daily loop

The plan says no branches: commit to the trunk often and push. That only works
if you **pull before you push**, every time.

Take their work first, do your bit, run the tests, then commit and push:

```bash
git pull --rebase origin main
git add -A
git commit -m "what changed and why"
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

Fatima, with no camera:

```bash
python -m handsfree.actions --fire mute_toggle
```

Nicholas, with no actions built yet — print the word instead of firing it, then
swap in the real call when you're ready:

```python
from handsfree.actions import fire
fire(word)
```

If a word needs to change, change it **here first**, tell the other person, and
only then touch code. A renamed string is a gesture that silently fires nothing.

## Before you push

43 tests; no camera, board or display needed:

```bash
python -m pytest tests/ -q
```

A red test on the trunk blocks both of you, so run them before pushing, not
after.
