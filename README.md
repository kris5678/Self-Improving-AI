# Self-Improving AI

A small method that makes an AI coding assistant **remember how it did repeatable tasks, check
its own work before showing it to you, and get measurably better over time**, at a low token
cost. It is plain Markdown files plus a few small Python scripts. Nothing runs as a service; the
optional hooks run only at moments Claude Code calls them.

Built and used with **Claude Code**. Other assistants: see [Which assistants it works with](#which-assistants-it-works-with).
Not an official Anthropic product.

## How it works

```
 your request
     │
     ▼
 1. LOOK UP ─── one cheap search of your playbooks' first lines (keywords: …)
     │           found → follow the playbook's short top part
     ▼
 2. PLAN ────── self-review "before starting": derive your likely questions from 8 purposes;
     │           compare better or cheaper ways to the goal ("Decisions: goal … · ways … · alt: …")
     │           [hook] before the first risky change or a plan for approval: an independent
     │           check may stop it once, with a question, before anything is built
     ▼
 3. DO THE WORK
     ▼
 4. PRESENT ─── self-review "before presenting"; the reply ends with the 🟣 Self-check line
     │           [hook] free checks on that line + an independent check on high-stakes replies;
     │           something important missing → sent back once for a short follow-up (🔵 line)
     ▼
 5. LEARN ───── repeatable task → write or update a playbook
                a question you still had to ask → logged as a miss (gap / lapse / repeat)
                [hook] counts those questions for you
                rules change only through the benchmark; every change gets a change-log entry
                → the trend report shows whether it's getting better
```

**The parts:**
- **Playbooks** are short Markdown notes the assistant writes after real tasks: line 1
  `keywords: …`, a 25-line top part, then details. Finding one costs about 30–50 tokens (it
  searches only the first lines) and reading its top about 250. If the keyword search finds
  nothing, it searches the full text, then picks by meaning, then checks a list of one-off tasks,
  so nothing is searched for twice.
- **The self-review** is eight purposes, not a fixed checklist: truth over belief, do no harm,
  don't settle on the first answer, plan for being wrong, stay healthy over time, outlive this
  session, prove it in reality, compound the learning. From them the assistant works out the
  questions *you* would ask about this task and answers them first. Every reply that presents
  work ends with:
  `🟣 Self-check (high, 2 pass, 7/8 purposes): checked … · alt … · fixed … · open …`
- **The benchmark** keeps the rules from drifting:
  - every question you still had to ask is a *miss*: `gap` (no rule covered it), `lapse` (a rule
    existed but wasn't followed) or `repeat` (it came back after a fix);
  - a rule changes only for a real miss, your request or a concrete defect, and only if every
    earlier case still passes;
  - the always-loaded file stays within a fixed word budget: one rule in, one out.
- **The self-check hooks** (optional, Claude Code) check the work without relying on the
  assistant's own word. See [Self-check hooks](#self-check-hooks-optional-claude-code).
- **The change log** (`core-changes.md` in your folder) records every change to the method: why,
  the evidence, how to undo it, and later whether it was right. Use it to audit, and to go back.
- **The trend report** (`self-review-trend.html`, one double-click, no AI) shows:
  - misses per week and a rough better / same / worse verdict;
  - word-budget use;
  - what the hooks caught and what each check cost;
  - how often you still had to ask;
  - warnings: a hook stopped running, or a method change has no log entry.

## What's in this folder

| File | What it is |
|---|---|
| `CLAUDE-snippet.md` | The always-loaded rules (~370 words) you paste into your assistant's instructions file |
| `MAINTAINING.md` | How playbooks are written and kept healthy; the rule for logging changes to `core/` |
| `self-review-before-presenting.md` | The 8 purposes, passes, the 🟣 line, the learning loop, the changelog of old wordings |
| `self-review-benchmark.md` | How rule changes are scored, the budget rule, miss types, monitoring and reviews |
| `ai-knowledge-base-token-cheap-lookup.md` | Why the lookup is designed this way, token costs, lessons |
| `tools/benchmark_summary.py` | Reads your miss log; writes the trend report and a daily history CSV |
| `tools/self-review-trend.bat` / `.sh` | Double-click (Windows) or run (macOS/Linux) to update and open the report |
| `tools/selfcheck.py` | Optional Claude Code hooks: checks before building and after replies, counts what you still had to ask |
| `tools/test_selfcheck.py` | Tests for the hooks and the report (a fake `claude`, no model calls) |
| `tools/check_no_personal_data.py`, `tools/install_hooks.py` | Git hooks that block personal data from commits (for contributors) |
| `templates/` | Starting files for your private folder (listed in step 3 below) |
| `docs/` | Images for this README |
| `CONTRIBUTING.md`, `LICENSE` | How to contribute; MIT licence |

## Set it up (about 10 minutes)

You need git and Python 3 (only the scripts use it).

1. **Make a private folder** for your knowledge base, for example `~/Knowledgebase`.
2. **Put this repo inside it as `core/`:** `git clone <this repo's URL> ~/Knowledgebase/core`
3. **Copy everything in `core/templates/` into your folder** (not into `core/`), **including the
   hidden `.gitignore` and `.ignore`**. Without `.ignore`, search tools skip `core/` and can't find
   its playbooks. You get:

   | File | For |
   |---|---|
   | `NO_PLAYBOOK.md` | The list of one-off tasks |
   | `self-review-log.md` | Your word budget, cases and miss log (delete the example rows at your first real miss) |
   | `core-changes.md` | The change log of the method |
   | `README.md` | Your own overview |
   | `private-terms.txt` | Your personal words (only needed if you contribute) |
   | `selfcheck-config.json`, `selfcheck-checker-prompt.md` | Only for the optional hooks |
   | `.gitignore`, `.ignore` | Keep `core/`, the report and the hooks' log out of your backup; let search see `core/` |

4. **Paste the block from `core/CLAUDE-snippet.md`** into the file your assistant loads in every
   session (Claude Code: `~/.claude/CLAUDE.md`), and replace every `<KB>` with your folder's
   path. Keep the whole file within the budget in your `self-review-log.md` (700 words by default).
5. **Back up your folder to a private repo** or a private cloud drive. Your playbooks, logs and
   notes are yours: they never go into `core/`. If you change `core/` yourself, back those
   changes up privately too. They aren't in your folder's repo, because `core/` is git-ignored
   there.
6. **Optional:** set up the [self-check hooks](#self-check-hooks-optional-claude-code).
7. **Test it in a fresh session:** do a small task and check that the reply ends with a
   `🟣 Self-check` line.

Your folder will look like this:

```
~/Knowledgebase/                 ← private
├── core/                        ← this repo (shared)
├── your-playbooks.md            (written by the assistant after real tasks)
├── NO_PLAYBOOK.md, self-review-log.md, core-changes.md, README.md, private-terms.txt
├── selfcheck-config.json, selfcheck-checker-prompt.md, selfcheck/   (only with the hooks)
└── self-review-history.csv, self-review-trend.html   (written by the summary script)
```

## Using it day to day

- **Work as usual.** Before a task that looks like it was done before, the assistant searches
  your playbooks. After a repeatable task, it writes or updates one.
- **Watch the 🟣 line.** It says what was checked, which alternatives were compared, what was
  fixed and what is still open. If the line is missing or claims a check that wasn't done, that
  counts as a miss.
- **Say "that's a miss"** whenever you had to ask something the assistant should have asked
  itself. It logs the miss, and the rules change only through the benchmark.
- **Check the trend now and then:** double-click `core/tools/self-review-trend.bat` (Windows) or
  run `core/tools/self-review-trend.sh` (macOS/Linux).
- **Audit the method:** `core-changes.md` lists every change with why, evidence and undo. At each
  review the assistant marks older entries `right`, `wrong` or `unclear`, and reverts wrong ones
  using their Undo line.
- **Update the method:** `git pull` inside `core/`. Your own files are never touched.

## Self-check hooks (optional, Claude Code)

The 🟣 line is the assistant marking its own work. These hooks add checks that don't depend on
its word. A real example:

![A real send-back: the reply's 🟣 line claimed both briefs were re-read; the hook sent it back, and the assistant read the missed file and fixed three gaps](docs/selfcheck-sendback-example.png)

The reply's 🟣 line said both briefs were checked "line by line", but no tool run in that turn had
read them. The after-reply check (#1923) asked the owner's likely question: "Did you actually re-read
both briefs?" The assistant admitted it had skipped one, read it, and found and fixed three gaps,
all before the owner read on or had to ask.

One script, `tools/selfcheck.py`, runs at three moments:

| When | What it does | Cost |
|---|---|---|
| **Before the first risky change** of a reply (payment code, database, release builds, git commit or push, git commands that rewrite history or throw away uncommitted work, settings, CLAUDE.md, privacy or terms text, deletes outside temp folders; in Chrome: clicks that save, submit, send, delete, grant, create or publish, and file uploads), and **before a plan is shown for approval** | If the reply hasn't written its decisions with alternatives (a line `Decisions: … · alt: …`), an independent check runs. A question it raises **blocks the change once**, before anything is built. Not when your own message ordered exactly that action ("commit and push", "now build the app"): then it just runs, and the reply isn't checked either. Deletes, risky files, browser clicks and plans are always checked, and so is an action your message also forbids somewhere ("push here, don't push there"). | 0 when the decisions are written |
| **After each reply** that presents work | Free checks: is the 🟣 line there and complete; were alternatives compared at high stakes; was risky work labelled low stakes. On high-stakes replies, an independent check too. Something important missing → the reply is **sent back once** for a short follow-up. | 0 for the free checks |
| **When a run of work looks finished** (3+ replies that changed things or saved lessons to project memory / the miss log, while project memory, the relevant .md docs or a playbook were not updated, and you say "done", "it's working", "thanks"…, or lessons were just saved, or the run reaches 6) | The reply is sent back once, naming only what is missing: "update memory / the relevant docs / a playbook now, or say in one line why not" (a 🔵 line). There is no "session finished" event a session can still act on, so this is the moment. Off: `"playbook_reminder": false` | 0 (no model call) |
| **When a reply ends by handing you a choice** ("If you want, I can also…", "Shall I…?") that isn't about money, publishing, deleting, permissions, commits, what to work on next or taste | Sent back once: decide by the goal (a small step of the current task: do it; a new task: a one-line suggestion, never started; else drop it), or say in one line why it's yours. Off: `"offer_check": false` | 0 (no model call) |
| **When a reply asks you something** (a question line anywhere in it, addressed to you, not about money, publishing, deleting, permissions, commits or taste) | The independent check judges whether your goal already answers it; if so, the reply is sent back once to decide it. A new task stays a one-line suggestion, never started. Off: `"question_check": false` | one independent check (~6 a day in a replay of 905 real replies) |
| **Before a step that has a playbook** (a playbook's `triggers:` line matches the command or Chrome call, see `MAINTAINING.md`) | The first matching call of a session is sent back once: "read this playbook first"; the retry passes. Skipped when the session already used or named it. Off: `"playbook_triggers": false` | 0 (no model call); 25 of 112 sessions in a 14-day replay |
| **Before a screenshot** (a browser or desktop screenshot tool, or a phone capture: `adb … screencap`, `simctl io … screenshot`, `flutter screenshot`), helper agents too | Sent back once: read the page or phone as text first (find / read_page / get_page_text; the uiautomator dump). The identical retry passes, for looks, maps or photos. It names your own playbook (`browser-automation-text-not-screenshots.md`, `android-phone-usb-test-flutter-app.md`) and `scripts/android_screen_text.py` only if they exist in your folder | 0; a text read costs far fewer tokens than an image |
| **Before writing over the miss log or `core-changes.md`** (a Write, `>`, `Set-Content`, `cp` onto it, `open(…, 'w')`) | Sent back once: add rows with Edit or `>>`; a real restore passes on retry | 0 |
| **On each of your prompts** | Counts what you still had to ask (doubt, corrections, "double check", "that's a miss"), and tells the assistant to log real misses. Once a day, when a review is due (5 misses since the last), the assistant suggests it in one line; it never starts it. Off: `"review_reminder": false` | ~60 tokens on ~1% of prompts |

**A reply counts as high stakes** when its 🟣 line says high, when it did something risky (as
listed above), or when your prompt asked for care ("double check", "make sure you didn't miss
anything") or said "that's a miss". A plan shown for approval is checked by the gate, before the
approval dialog.

**The independent check** is a separate, one-off `claude -p` session on a small model (default
Claude Haiku 5.5, medium effort):
- **It sees only:** your last 2 exchanges (your prompts, the tools that were run, the replies),
  plus the questions you had to ask in the past (from your miss log), as examples.
- **It answers:** `{"ok": true}` (then nothing happens) or one question you'd likely ask.
- **It's safe:**
  - it runs on your Claude subscription (no API key needed);
  - it has no tools and loads no hooks, settings or connectors, so it can't loop or act;
  - if it fails or times out, the reply simply passes and the failure is logged.
- **Cost:** about 5–7k tokens and 5–9 s per check.
- **Accuracy:** in a small test on 14 real past replies, scored against what the owner asked next:

  | Effort | Caught | False flags |
  |---|---|---|
  | medium | 4 of 7 | 1 of 7 |
  | high | 6 of 7 | 1 of 7 |

  Try both, using your own ratings.

**Limits:** it judges only what's written in the conversation. A miss that depends on what's
inside a file the assistant read but didn't quote can pass. Expect occasional fair-but-extra
questions; rate them.

**Set up:**
1. Copy `templates/selfcheck-config.json` and `templates/selfcheck-checker-prompt.md` into your
   folder, next to `core/`. Describe yourself in the prompt's first line if you like.
2. Add the hooks to `~/.claude/settings.json`, keeping any hooks you already have. Use the full
   path to `core/tools/selfcheck.py`:

   ```json
   "hooks": {
     "Stop": [{"hooks": [{"type": "command", "command": "python -I -S \"<KB>/core/tools/selfcheck.py\"", "timeout": 90}]}],
     "PreToolUse": [{"matcher": "Edit|Write|NotebookEdit|Bash|PowerShell|ExitPlanMode|mcp__claude-in-chrome__.*|mcp__.*screenshot.*|mcp__.*__computer|mcp__.*__browser_batch",
                     "hooks": [{"type": "command", "command": "python -I -S \"<KB>/core/tools/selfcheck.py\"", "timeout": 90}]}],
     "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python -I -S \"<KB>/core/tools/selfcheck.py\"", "timeout": 15}]}]
   }
   ```

   Use `python3` instead of `python` if that's your command.
3. Optional: `python -I core/tools/selfcheck.py backfill-history` (from your folder) counts your
   past prompts once, which gives the report a starting point.
4. Check it: `python -I core/tools/test_selfcheck.py` should pass. Then a long reply without a 🟣
   line should come back once with a 🔵 note.

**Use:**
- A 🔵 line shows each time a check ran, sent a reply back or blocked a change, with its number.
- Rate a check: tell the assistant "#12 was right / wrong", or run
  `python -I core/tools/selfcheck.py rate 12 wrong`. A pass followed by your doubt is marked
  "possible false pass" automatically.
- Change the model, effort or number of exchanges in `selfcheck-config.json`. The report compares
  settings side by side. `"send_back": false` only logs, never interrupts.
- **Off switch:** create an empty file `selfcheck-off` in your folder. Delete it to turn them back on.
- **The report** shows checks, cost, accuracy per setting, what you still had to ask each week,
  and the last 50 checks. Tap one to read exactly what the check received and answered.

**Privacy:** the hooks' log (`selfcheck/` in your folder) holds conversation text. It stays on your
computer: the template `.gitignore` keeps it out of your backup repo.

## Which assistants it works with

The method is plain text, so it works with any assistant that loads an instructions file in
every session **and** can search and read the files on your computer.

| Assistant | Paste the snippet into | Status |
|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` | Built and tested with this; the hooks work only here |
| OpenAI Codex CLI | `~/.codex/AGENTS.md` | Should work, not tested yet |
| Gemini CLI | `~/.gemini/GEMINI.md` | Should work, not tested yet |
| Cursor and other coding agents | their user/global rules | Should work, not tested yet |
| ChatGPT, Claude or Gemini in a browser or chat app | — | Only partly: they can't search your folder, so playbooks don't work. You can paste the self-review purposes into custom instructions, but those have a short length limit. |

The snippet uses Claude Code's tool names (`Grep`, `files_with_matches`). Other agents understand
the same steps through their own search tools (`rg`, `grep`).

## Contributing

Improvements are welcome. Rule changes follow the same benchmark as everything else; see
`CONTRIBUTING.md`. Before your first commit, run `python -I tools/install_hooks.py` inside `core/`
and use a no-reply commit email.

MIT licence, provided as is.
