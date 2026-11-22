"""Block personal data from reaching this shared repo (git hooks call it; see install_hooks.py).

Terms come from private-terms.txt in the knowledge-base folder (the folder above core/), or the
path in the PRIVATE_TERMS environment variable. One term per line, case-insensitive, `#` = comment.
`\\` and `/` count as the same (a term `C:\\Users\\me` also catches `C:/Users/me` and `C:\\\\Users`).
Fails closed: no terms file, no commit.

  --staged        files staged for commit (names and contents) + the author and committer   (pre-commit)
  --message FILE  the commit message                                                       (commit-msg)
  --push RANGE    the files at the pushed commit, and for each commit in RANGE: every added line and
                  file name, the message, the author and the committer (pre-push). A word added in
                  one commit and deleted in a later one is still in the history, so it is caught.
  --all           every tracked and untracked file (manual check before a first commit)
"""

import os
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_TERMS = REPO.parent / "private-terms.txt"
NOREPLY = "@users.noreply.github.com"
SLASHES = re.compile(r"[\\/]+")


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, check=True).stdout


def norm(text):
    return SLASHES.sub("/", text.lower())


def load_terms():
    path = pathlib.Path(os.environ.get("PRIVATE_TERMS", DEFAULT_TERMS))
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        sys.exit(f"BLOCKED: no terms file at {path}. Create it (one personal term per line) first.")
    terms = [norm(t.strip()) for t in lines if t.strip() and not t.strip().startswith("#")]
    if not terms:
        sys.exit(f"BLOCKED: {path} has no terms.")
    return terms


def hits_in(text, terms):
    low = norm(text)
    return [t for t in terms if t in low]


def check_text(label, text, terms, found):
    for n, line in enumerate(text.splitlines(), 1):
        for t in hits_in(line, terms):
            found.append(f"{label}:{n}: contains a private term ({t!r})")


def check_person(label, name, email, terms, found):
    """Git records a name and an email for both the author and the committer of every commit."""
    email = email.strip()
    if not email.lower().endswith(NOREPLY):
        found.append(f"{label}: email {email!r} is not a GitHub no-reply address")
    for t in hits_in(f"{name} {email}", terms):
        found.append(f"{label}: name or email contains a private term ({t!r})")


def blob_text(data):
    return data.decode("utf-8", errors="replace")


def ident(var):
    """(name, email) git will record, environment overrides included (GIT_AUTHOR_EMAIL …)."""
    m = re.match(r"(.*?)\s*<([^>]*)>", blob_text(git("var", var)))
    return (m.group(1), m.group(2)) if m else ("", "")


def files_at(rev):
    """Paths of the files (blobs) in a commit; submodule entries have no content to read."""
    out = []
    for entry in filter(None, git("ls-tree", "-r", "-z", rev).split(b"\0")):
        info, _, path = entry.partition(b"\t")
        if info.split()[1] == b"blob":
            out.append(path.decode("utf-8", errors="replace"))
    return out


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    terms, found, mode = load_terms(), [], argv[0]
    if mode == "--staged":
        names = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split(b"\0")
        for name in filter(None, names):
            check_text("file name", name.decode(), terms, found)
            check_text(name.decode(), blob_text(git("show", ":" + name.decode())), terms, found)
        for var, who in (("GIT_AUTHOR_IDENT", "author"), ("GIT_COMMITTER_IDENT", "committer")):
            check_person(who, *ident(var), terms, found)
    elif mode == "--message":
        check_text("commit message", pathlib.Path(argv[1]).read_text(encoding="utf-8", errors="replace"),
                   terms, found)
    elif mode == "--push":
        tip = argv[1].split("..")[-1]  # what is pushed, not what happens to be checked out
        for name in files_at(tip):
            check_text("file name", name, terms, found)
            check_text(name, blob_text(git("show", f"{tip}:{name}")), terms, found)
        for sha in git("rev-list", argv[1]).decode().split():
            c = sha[:7]
            check_text(f"message {c}", blob_text(git("log", "-1", "--format=%B", sha)), terms, found)
            for who, fmt in (("author", "%an%x00%ae"), ("committer", "%cn%x00%ce")):
                check_person(f"commit {c} {who}", *blob_text(git("log", "-1", f"--format={fmt}", sha)).split("\0", 1),
                             terms, found)
            for name in filter(None, blob_text(git("show", "--format=", "--name-only", "-z", sha)).split("\0")):
                check_text(f"commit {c} file name", name, terms, found)
            diff = blob_text(git("show", "--format=", "--text", "--no-color", "--no-ext-diff", "-U0", sha))
            added = [line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
            check_text(f"commit {c} added lines", "\n".join(added), terms, found)
    elif mode == "--all":
        names = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")
        for name in filter(None, names):
            path = REPO / name.decode()
            check_text("file name", name.decode(), terms, found)
            if path.is_file():  # a deleted-but-tracked file has nothing to read
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
    try:
        sys.exit(main(sys.argv[1:]))
    except subprocess.CalledProcessError as e:  # fail closed, with a readable reason
        sys.exit(f"BLOCKED: git {' '.join(e.cmd[3:])} failed: {blob_text(e.stderr or b'').strip()[:300]}"
                 " (e.g. the remote has commits you haven't fetched: git fetch, then push again)")
