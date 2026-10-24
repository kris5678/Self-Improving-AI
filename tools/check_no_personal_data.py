"""Block personal data from reaching this shared repo (git hooks call it; see install_hooks.py).

Terms come from private-terms.txt in the knowledge-base folder (the folder above core/), or the
path in the PRIVATE_TERMS environment variable. One term per line, case-insensitive, `#` = comment.
Fails closed: no terms file, no commit.

  --staged        files staged for commit + the author email   (pre-commit)
  --message FILE  the commit message                            (commit-msg)
  --push RANGE    every tracked file, and each commit's message and author email in RANGE (pre-push)
  --all           every tracked and untracked file (manual check before a first commit)
"""

import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_TERMS = REPO.parent / "private-terms.txt"
NOREPLY = "@users.noreply.github.com"


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, check=True).stdout


def load_terms():
    path = pathlib.Path(os.environ.get("PRIVATE_TERMS", DEFAULT_TERMS))
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        sys.exit(f"BLOCKED: no terms file at {path}. Create it (one personal term per line) first.")
    terms = [t.strip().lower() for t in lines if t.strip() and not t.strip().startswith("#")]
    if not terms:
        sys.exit(f"BLOCKED: {path} has no terms.")
    return terms


def hits_in(text, terms):
    low = text.lower()
    return [t for t in terms if t in low]


def check_text(label, text, terms, found):
    for n, line in enumerate(text.splitlines(), 1):
        for t in hits_in(line, terms):
            found.append(f"{label}:{n}: contains a private term ({t!r})")


def check_email(label, email, terms, found):
    email = email.strip()
    if not email.lower().endswith(NOREPLY):
        found.append(f"{label}: author email {email!r} is not a GitHub no-reply address")
    for t in hits_in(email, terms):
        found.append(f"{label}: author email contains a private term ({t!r})")


def blob_text(data):
    return data.decode("utf-8", errors="replace")


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    terms, found, mode = load_terms(), [], argv[0]
    if mode == "--staged":
        names = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split(b"\0")
        for name in filter(None, names):
            check_text(name.decode(), blob_text(git("show", ":" + name.decode())), terms, found)
        check_email("identity", git("config", "user.email").decode(), terms, found)
    elif mode == "--message":
        check_text("commit message", pathlib.Path(argv[1]).read_text(encoding="utf-8"), terms, found)
    elif mode == "--push":
        for name in filter(None, git("ls-files", "-z").split(b"\0")):
            check_text(name.decode(), blob_text(git("show", "HEAD:" + name.decode())), terms, found)
        for sha in git("rev-list", argv[1]).decode().split():
            check_text(f"message {sha[:7]}", git("log", "-1", "--format=%B", sha).decode(), terms, found)
            check_email(f"commit {sha[:7]}", git("log", "-1", "--format=%ae", sha).decode(), terms, found)
    elif mode == "--all":
        names = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")
        for name in filter(None, names):
            path = REPO / name.decode()
            check_text(name.decode(), blob_text(path.read_bytes()), terms, found)
    else:
        print(__doc__)
        return 2
    if found:
        print("BLOCKED - personal data found:")
        print("\n".join("  " + f for f in found))
        return 1
    print("OK: no private terms found.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
