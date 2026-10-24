keywords: knowledge-base knowledge base kb playbook playbooks lookup index indexing search grep keywords token tokens cheap low-token claude-md claude.md memory ai assistant agent repeatable no-playbook maintaining
# Token-cheap knowledge base of playbooks for AI assistants
Use when: setting up (or copying to a new PC, team or AI tool) a folder of playbooks that AI sessions find with almost no tokens.
verified: 2026-10-24

## Quick steps
1. Make a private knowledge-base folder; clone this repo into `core/` inside it; copy `core/templates/*` into the folder (`NO_PLAYBOOK.md`, `self-review-log.md`, `README.md`).
2. Every playbook (in the knowledge-base folder, not `core/`): line 1 `keywords: …` (many synonyms), then title, `Use when:`, `verified:`, ≤ 10 quick steps, ≤ 5 gotchas, blank line, `---`, details.
3. Paste `core/CLAUDE-snippet.md` into the instructions every session loads (Claude Code: `~/.claude/CLAUDE.md`), with `<KB>` replaced by the folder path.
4. Test from a fresh session: ask for a known task; it should find it with one search and read only the top.
5. Back the folder up to a **private** repo (hourly scheduled task); `core/` stays a separate repo.

## Top gotchas
- Short words match inside longer ones (`ipa` in `ipad`): search them as `\bipa\b`.
- Any non-playbook line starting `keywords:` (format examples, the one-off list) becomes a false hit: indent examples; one-offs use `task:`.
- A separate index file drifts and costs upkeep; the keyword lines *are* the index.
- Skills/always-loaded descriptions cost tokens in every session: avoid for many playbooks.
- Over-general keywords (`setup`, `app`, `fix`) match unrelated tasks: test each new keyword line with step 1.
- Search tools skip git-ignored folders: a nested `core/` ignored by the private repo needs a `.ignore` with `!core/`.

---

## Why this design (cost per lookup, ~100 playbooks)

| Approach | Tokens | Problem |
|---|---|---|
| Read a README index each time | ~4,000, grows | grows forever |
| Grep a README index | ~150 | index drifts |
| **Grep each file's `keywords:` line, file names only** | **~30–50, then ~250 for the top part** | a missed synonym → backups below |
| One skill per playbook | ~40 × N in every session | fixed cost even when unused |
| Semantic-search server | small per query | server to run; overkill |

## The lookup (cheapest first, stop at the first hit)

1. `^keywords:.*(stem1|stem2)` — case-insensitive, file names only.
2. Specific stems in the full text, file names only; more than 5 files → narrow first.
3. Only if the task looks done before (store, release, device, account, deploy, setup) or the
   user says "again": check `NO_PLAYBOOK.md` (same task → stop), then list every keyword line
   and choose by meaning.

Also run step 1 when a new kind of sub-task appears mid-task. A stale `NO_PLAYBOOK.md` line can't
hide a playbook, because steps 1–2 always run.

## After a task (learning loop)

- Playbook used: fix it, set `verified:`, changelog line (quick; no need to read MAINTAINING.md).
- Partial miss (found only at step 2/3): add the searched words to its keywords line.
- Full miss: repeatable → new playbook (delete matching `NO_PLAYBOOK.md` lines); one-off → a `task:` line.

## Block for the always-loaded instructions

The one copy is `CLAUDE-snippet.md` (in this repo); never paste a second copy here.

## Lessons from building it

- Test the searches yourself right after setting up: the test run found both gotchas above.
- Keep the always-loaded part to a few lines; rarely needed rules go in `MAINTAINING.md`.
- Instructions only reach future sessions if they are in a file every session loads; a
  knowledge-base README alone is never seen.
- Back it up with an hourly scheduled task (commit + push only when something changed, refuse
  any other remote), not by sessions committing: 0 tokens, no exception to a "never commit
  unless I ask" rule, and it also catches the owner's own edits. [verified 2026-10-25, Windows
  Task Scheduler + `conhost.exe --headless`, no window flash]
- Personal and public files in **separate repos** (public one nested and git-ignored), never
  branches or subtree: commit history and messages can leak. Public commits need an
  anonymous author email (git records it in every commit).

## Changelog

- 2026-10-24: created after designing and testing the lookup with the owner.
- 2026-10-24: gotcha on over-general keywords (new-playbook test step added to MAINTAINING.md).
- 2026-10-25: split into a shared `core/` repo + private folder; the instructions block moved to `CLAUDE-snippet.md`.
- 2026-10-25: gotcha: lookups missed `core/` (ignored folders are skipped) → `.ignore` with `!core/`. [verified 2026-10-25]
