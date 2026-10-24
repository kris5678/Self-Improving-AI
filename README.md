# Self-Improving AI

A small method that makes an AI coding assistant **remember how it did repeatable tasks, check
its own work before showing it to you, and get measurably better over time**, at a low token
cost. It is plain Markdown files plus a few small Python scripts: nothing to install as a
service, nothing running in the background.

Built and used with **Claude Code**. Other assistants: see [Which assistants it works with](#which-assistants-it-works-with).
Not an official Anthropic product.

## What it does

- **A knowledge base of playbooks.** After a repeatable task (a store release, a device setup,
  a deploy) the assistant writes a short playbook. Next time it finds it with one cheap search
  on each playbook's first line (`keywords: …`), about 30–50 tokens, and reads only the
  playbook's short top part. If that search finds nothing, it tries a full-text search, then
  picks by meaning, and finally checks a list of one-off tasks, so nothing is searched for twice.
- **Self-review before presenting.** Eight purposes: truth over belief, do no harm, don't settle
  on the first answer, plan for being wrong, stay healthy over time, outlive this session, prove
  it in reality, compound the learning. From them the assistant works out the questions *you*
  would ask about this particular task and answers them before showing you the work. Each such
  reply ends with a visible line, for example:
  `🟣 Self-check (high, 2 pass, 7/8 purposes): checked … · alt … · fixed … · open …`
- **A benchmark, so the rules improve instead of drifting.** Every question you still had to ask
  is a *miss*. It is logged as a `gap` (no rule covered it), a `lapse` (a rule existed but wasn't
  followed) or a `repeat` (it came back after a fix). The rules change only for a real miss, your
  request or a concrete defect. A change is accepted only if every earlier case still passes and
  the always-loaded file stays within a fixed word budget (one rule in, one out).
- **A free trend report.** One double-click updates `self-review-trend.html`. It shows misses per
  week, a rough better / same / worse verdict, repeats, and how much of the word budget is used.
  No AI, no tokens.

## What's in this folder

| File | What it is |
|---|---|
| `CLAUDE-snippet.md` | The always-loaded rules (~370 words) you paste into your assistant's instructions file |
| `MAINTAINING.md` | How playbooks are written and kept healthy (read only when writing one) |
| `self-review-before-presenting.md` | The 8 purposes, passes, the 🟣 line, the learning loop |
| `self-review-benchmark.md` | How rule changes are scored; miss types; monitoring |
| `ai-knowledge-base-token-cheap-lookup.md` | Why the lookup is designed this way, token costs, lessons |
| `tools/benchmark_summary.py` | Counts your miss log; writes the trend report and a daily history CSV |
| `tools/self-review-trend.bat` / `.sh` | Double-click (Windows) or run (macOS/Linux) to update and open the report |
| `tools/check_no_personal_data.py`, `tools/install_hooks.py` | Git hooks that block personal data from your commits (for contributors) |
| `templates/` | Starting files for your own private folder |

## Set it up (about 10 minutes)

You need git and Python 3 (only the scripts use it).

1. **Make a private folder** for your knowledge base, for example `~/Knowledgebase`.
2. **Put this repo inside it as `core/`:** `git clone <this repo's URL> ~/Knowledgebase/core`
3. **Copy the templates** into your folder (not into `core/`): everything in `core/templates/`,
   **including the hidden `.gitignore` and `.ignore`**. Without `.ignore`, search tools skip
   `core/` and can't find its playbooks. You get:
   - `NO_PLAYBOOK.md`: the list of one-off tasks;
   - `self-review-log.md`: your word budget, cases and miss log. Delete the example rows when you
     log your first real miss;
   - `README.md`: your own overview;
   - `private-terms.txt`: your personal words, needed only if you contribute.
4. **Paste the block from `core/CLAUDE-snippet.md`** into the file your assistant loads in every
   session (Claude Code: `~/.claude/CLAUDE.md`), and replace every `<KB>` with your folder's
   path. Keep the whole file within the budget set in your `self-review-log.md` (700 words by
   default).
5. **Back up your folder to a private repo** (or a private cloud drive). Your playbooks and miss
   log are yours: they never go into `core/`.
6. **Test it in a fresh session:** do a small task and check that the reply ends with a
   `🟣 Self-check` line.

Your folder will look like this:

```
~/Knowledgebase/                 ← private
├── core/                        ← this repo (shared)
├── your-playbooks.md            (written by the assistant after real tasks)
├── NO_PLAYBOOK.md, self-review-log.md, README.md, private-terms.txt
└── self-review-history.csv, self-review-trend.html   (written by the summary script)
```

## Using it day to day

- **Work as usual.** Before a task that looks like it was done before, the assistant searches
  your playbooks. After a repeatable task, it writes or updates one.
- **Watch the 🟣 line.** It says what was checked, which alternatives were compared, what was
  fixed and what is still open. If the line is missing or claims a check that wasn't done, that
  counts as a miss.
- **Say "that's a miss"** whenever you had to ask something the assistant should have asked
  itself. It logs the miss, and the rules only change through the benchmark.
- **Check the trend now and then:** double-click `core/tools/self-review-trend.bat` (Windows) or
  run `core/tools/self-review-trend.sh` (macOS/Linux).
- **Update the method:** `git pull` inside `core/`. Your own files are never touched.

## Which assistants it works with

The method is plain text, so it works with any assistant that loads an instructions file in
every session **and** can search and read the files on your computer.

| Assistant | Paste the snippet into | Status |
|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` | Built and tested with this |
| OpenAI Codex CLI | `~/.codex/AGENTS.md` | Should work, not tested yet |
| Gemini CLI | `~/.gemini/GEMINI.md` | Should work, not tested yet |
| Cursor and other coding agents | their user/global rules | Should work, not tested yet |
| ChatGPT, Claude or Gemini in a browser or chat app | — | Only partly: they can't search your folder, so playbooks don't work. You can paste the self-review purposes into custom instructions, but those have a short length limit. |

The snippet uses Claude Code's tool names (`Grep`, `files_with_matches`). Other agents
understand the same steps through their own search tools (`rg`, `grep`).

## Contributing

Improvements are welcome. Rule changes follow the same benchmark as everything else; see
`CONTRIBUTING.md`. Before your first commit, run `python -I tools/install_hooks.py` inside `core/`
and use a no-reply commit email.

MIT licence, provided as is.
