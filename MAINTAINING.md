# Maintaining the knowledge base

Read only when writing a new playbook or a `NO_PLAYBOOK.md` line, or restructuring. The
lookup recipe and the quick after-task updates (used playbook, partial miss) live in the
always-loaded instructions (`~/.claude/CLAUDE.md`, from `CLAUDE-snippet.md`); if a rule changes,
update it there, here, `CLAUDE-snippet.md`, and the copy in `ai-knowledge-base-token-cheap-lookup.md`.

Layout: the knowledge-base folder (private) holds your playbooks, `NO_PLAYBOOK.md`,
`self-review-log.md` and `README.md`; `core/` inside it is this repo (the method, shared).
Personal playbooks go in the knowledge-base folder, never in `core/`.

## Playbook format

Sessions read a playbook only down to its first `---` line, so keep that top part short
(about 25 lines).

(Indented here so this file never matches a search; in a playbook these lines start at column 1.)

```
  keywords: <lowercase words and stems, plenty of synonyms; multi-word terms both ways: play-console play console>
  # <Title>
  Use when: <one line>
  verified: <YYYY-MM-DD, last time seen working>

  ## Quick steps
  1. … (at most 10)

  ## Top gotchas
  - … (at most 5)

  ---

  <details: sections, [verified …] tags, Changelog at the bottom>
```

- Line 1 must start with `keywords:` (step 1 searches `^keywords:`). No other file may have a
  line starting with `keywords:`.
- Include short words (≤ 3 letters, e.g. `ipa`, `aab`) as they are; searches wrap them in
  `\b…\b` so they don't match inside longer words (`ipa` in `ipad`).
- Leave a blank line before `---` (otherwise Markdown makes the line above a heading).
- File name: descriptive, lowercase, hyphens (`ios-testflight-codemagic.md`).

## After each lookup

- **Partial miss** (step 1 found nothing, step 2 or 3 found the playbook): add the words you
  searched with to that playbook's `keywords:` line.
- **Full miss** (nothing found):
  - repeatable task → write a playbook (below);
  - one-off → add one line to `NO_PLAYBOOK.md`:
    `task: <several words describing exactly this task> — <YYYY-MM-DD> — <why no playbook>`
    (`task:`, never `keywords:`, so lookup step 1 never matches it).
- **Playbook used**: fix wrong steps, add new gotchas, update `verified:` and the tags,
  add one changelog line. Do it in the same turn.

## Writing a new playbook

1. Run the lookup first; if a playbook is close, extend it instead of adding another.
2. Use the format above.
3. Grep `NO_PLAYBOOK.md` with the new keywords and delete lines for the same task.
4. Test it: run lookup step 1 with 2–3 words a future user would say; only the new playbook
   should match. Drop over-general keywords (`setup`, `app`, `fix`, `test`) that would match
   unrelated tasks.
5. Add one line for it to the knowledge-base folder's `README.md` list (the owner's overview).
6. Above ~50 playbooks: move them into category folders (`ios/`, `android/`, `stores/`,
   `flutter/`, `web/`, `tools/`); step 3 then reads only the relevant folder.

## Content rules

1. **Confidence tags**: `[verified YYYY-MM-DD]` = done and seen working; `[unverified]` =
   believed, not tested; `[changed?]` = the UI differed last time.
2. **Never store secrets**: no passwords, keys, tokens, bank or ID data. Say where to find
   them (e.g. "key.properties, git-ignored"), never the value.
3. **Generic**: placeholders (`<app id>`, `<package name>`); project facts stay in that
   project's own notes.
4. **Owner decisions stay marked as the owner's**: never turn them into defaults.
5. **Short and scannable**: numbered steps, tables, one idea per bullet; put "stop and ask
   the owner" points where they happen.
6. **Facts over opinions**; if you add advice, say why.
