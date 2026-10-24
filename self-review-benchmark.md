# Self-review benchmark (the method)

Read only when a real miss happened or a change to the self-review rules is proposed.
Not a playbook (no keywords line). **Your data** — budget, cases, miss log — lives in your own
`self-review-log.md` in the knowledge-base folder (one level above `core/`), never in this repo;
start it from `templates/self-review-log.md`.

## How to measure

1. **Real-world trend (the goal):** every real miss gets a row in your miss log.
   Fewer misses per week = it is improving. More after a change = revert that change
   (old wording is in the playbook's changelog). Rough: there is no count of tasks behind it.
2. **Cases (the guard):** each miss becomes a case. A proposed change is scored by reading
   **only the new rule text** and asking, per case: "would a session with no memory, reading
   only this, have asked the question?" Pass / fail per case.
3. **A change is accepted only if:** it fixes its trigger (the new case, the owner's request,
   or the concrete defect), it passes every earlier case (score never drops), and it fits the
   budget. Otherwise: log the miss only.
4. **Budget:** the whole always-loaded instructions file (e.g. `~/.claude/CLAUDE.md`; every
   session pays for all of it) stays at about the word count set in your log
   (`Budget: about **N words**`). **One in, one out:** new wording replaces something worth
   less. Worth is evidence: each phrase should serve a logged case or miss; a phrase no case
   needs goes first. First move anything that doesn't make a session *act* into a playbook.
   **Protected:** the owner's own wording and lines the owner marks protected are never
   swapped out (rare but vital rules can look unused). Only when no swap is possible: ask the
   owner to raise the budget, with the reason in the playbook's changelog.
5. **Bias guard:** the session scoring its own change is biased. For a big change, run the cases
   with a fresh agent given only the old text, then only the new text (costs tokens: ask the
   owner first), or let the owner spot-check two cases.

A "real miss" = the owner had to ask something the purposes should have caught, the
`🟣 Self-check` line was missing or named nothing real, or the owner says "that's a miss"
(always logged). Not a miss: the owner's own decisions, new information only the owner had,
a change of mind.

## Monitoring (cheap: the script counts, sessions don't read the whole log)

- **Miss type** (column in the log):
  - `gap` — no rule covered it → fix the rules.
  - `lapse` — a rule covered it but wasn't followed → make the rule more visible, never longer.
    Lapses that keep coming mean the always-loaded rules are too long or buried.
  - `repeat` — a case that happened again after its fix → that fix failed: revert or redo it.
    The clearest "getting worse" signal.
- **Summary:** `python -I core/tools/benchmark_summary.py` (from the knowledge-base folder)
  prints counts by type, rows since the last review, and "REVIEW DUE" (~50 tokens; the owner can
  run it free). Run it after every logged miss. Each run also writes, next to your log,
  `self-review-trend.html` (weekly misses incl. zero weeks, a rough BETTER / SAME / WORSE
  verdict from 14-day windows — any repeat in 14 days is WORSE —, budget, cases) and one
  snapshot per day in `self-review-history.csv` (kept forever; read only when the owner asks).
  The owner double-clicks `tools/self-review-trend.bat` (Windows) or runs
  `tools/self-review-trend.sh` (macOS/Linux) to update and open the report (no AI).
- **Review** (when it says REVIEW DUE — 5 rows since the last review — or the owner asks "how is
  the self-review doing?"): read only the rows since the last review; report in a few lines:
  trend, gaps vs lapses, repeats, budget pressure, changes to keep or revert; then add a
  `review` row with that summary.
- **Spot-check at each review:** the owner checks two cases, or (owner's OK, costs tokens) a
  fresh agent scores old vs new text, so scoring isn't only self-graded. Also check a few recent
  `🟣` lines: does each claim (`k/8`, `alt`, checks) match what was really done?
- Keep the log's columns as they are: the script reads them.
