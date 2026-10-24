# Tasks with no playbook (one-offs)

Checked before lookup step 3: a line for **the same task** means step 3 can be skipped.
Steps 1–2 always run, so a stale line can never hide a playbook. Rules: `core/MAINTAINING.md`.
One line per task, starting with `task:` (never `keywords:`):

`task: <several words describing exactly this task> — <YYYY-MM-DD> — <why no playbook>`

