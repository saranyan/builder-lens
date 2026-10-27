"""Local git reads. Only `git` is ever run, read-only, against repos already on disk."""
import os
import subprocess
from datetime import timedelta

from .model import Commit
from .sources import parse_ts

COMMIT_LIMIT = 1000          # Paxel caps author commits per repo at 1000 [upload.sh]
_SEP = "\x1f"


def git(cwd, args, timeout=60):
    try:
        p = subprocess.run(["git", "-C", cwd] + args, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        return p.stdout if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


_top_cache = {}


def toplevel(cwd):
    """Repo root for a session cwd, or '' if it isn't (or no longer is) a git repo."""
    if not cwd:
        return ""
    if cwd not in _top_cache:
        _top_cache[cwd] = git(cwd, ["rev-parse", "--show-toplevel"]).strip() if os.path.isdir(cwd) else ""
    return _top_cache[cwd]


def user_emails(repos):
    emails = set()
    for r in [None] + list(repos):
        out = git(r or os.path.expanduser("~"), ["config", "--global" if r is None else "--local", "user.email"])
        if out.strip():
            emails.add(out.strip().lower())
    return emails


def author_commits(repo, emails, since, until):
    """Author-filtered commits in [since, until] with numstat totals, newest first, capped."""
    since = (since - timedelta(days=1)).strftime("%Y-%m-%d")
    until = (until + timedelta(days=1)).strftime("%Y-%m-%d")
    out = git(repo, ["log", "--no-merges", f"--since={since}", f"--until={until}", "--numstat",
                     f"--format=@@C{_SEP}%H{_SEP}%aI{_SEP}%aE{_SEP}%s"], timeout=180)
    commits, cur = [], None
    for line in out.splitlines():
        if line.startswith("@@C" + _SEP):
            _, sha, ts, email, subject = (line.split(_SEP, 4) + [""] * 5)[:5]
            cur = None
            if email.lower() in emails and len(commits) < COMMIT_LIMIT:
                cur = Commit(sha, parse_ts(ts), email.lower(), subject, repo=repo)
                commits.append(cur)
        elif cur and line.strip():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():   # '-' = binary
                cur.added += int(parts[0])
                cur.deleted += int(parts[1])
    return [c for c in commits if c.ts]


def tracked_files(repo):
    return [f for f in git(repo, ["ls-files"]).splitlines() if f]
