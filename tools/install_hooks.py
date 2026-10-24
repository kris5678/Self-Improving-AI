"""Install the personal-data guard as git hooks in this repo (run once per clone).

  python -I tools/install_hooks.py

Hooks live in .git/hooks (never pushed), so every clone must run this once.
"""

import pathlib
import stat

REPO = pathlib.Path(__file__).resolve().parent.parent
HOOKS = REPO / ".git" / "hooks"
CHECK = "tools/check_no_personal_data.py"

SCRIPTS = {
    "pre-commit": f'#!/bin/sh\nexec python -I "$(git rev-parse --show-toplevel)/{CHECK}" --staged\n',
    "commit-msg": f'#!/bin/sh\nexec python -I "$(git rev-parse --show-toplevel)/{CHECK}" --message "$1"\n',
    # stdin: <local ref> <local sha> <remote ref> <remote sha> per pushed ref
    "pre-push": (
        "#!/bin/sh\n"
        'top="$(git rev-parse --show-toplevel)"\n'
        "zero=0000000000000000000000000000000000000000\n"
        "while read local_ref local_sha remote_ref remote_sha; do\n"
        '  [ "$local_sha" = "$zero" ] && continue\n'
        '  if [ "$remote_sha" = "$zero" ]; then range="$local_sha"; else range="$remote_sha..$local_sha"; fi\n'
        f'  python -I "$top/{CHECK}" --push "$range" || exit 1\n'
        "done\n"
    ),
}


def main():
    if not HOOKS.is_dir():
        raise SystemExit(f"No {HOOKS}: run this inside a git clone of the repo.")
    for name, body in SCRIPTS.items():
        path = HOOKS / name
        path.write_text(body, encoding="utf-8", newline="\n")
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print("installed", path)


if __name__ == "__main__":
    main()
