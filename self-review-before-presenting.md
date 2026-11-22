keywords: self-review self review checklist self-check sceptic skeptic verify verification evidence proof are-you-sure certain alternatives cheaper simpler fallback edge-case regression assumption perfect rounds owner-prompts future-session reproducible purpose principles
# Self-review before presenting a fix, design, diagnosis or "done"
Use when: about to start work on, or to present, a fix, a design/process, a diagnosis or explanation ("why does X happen?"), a form/declaration, or to say "done". Derive the owner's likely questions yourself, act on them, and only bring real decisions.
verified: not yet proven in a new session (created 2026-10-24; dry runs on itself and on 2 new scenarios)

## Quick steps
1. **Size the effort to the stakes:** one-line or cosmetic change → purposes 1–2; a release, money, privacy, legal, data, or a design/process others will reuse → all purposes. **Unsure → treat as high.**
2. For each purpose below, **write the questions it raises for this task** (they differ per task; the examples are not the questions).
3. Act on the answers before presenting (get the evidence, fix what you find).
4. **Passes:** repeat 2–3 while a pass changes something important; stop when a full pass finds nothing important (low stakes: one pass). Cap 5 passes, then present what's left.
5. **Present** plainly and concisely: what was checked, the evidence, guesses labelled as guesses, what's still open, and only decisions that are really the owner's (check CLAUDE.md/memory first that it wasn't already decided). End with one line: `🟣 Self-check (<low|high>, <n> pass, <k>/8 purposes): checked <concrete things> · alt <options compared> · fixed <…> · open <…>` — it shows the owner it ran (and tests this playbook); name real checks, never claim one that wasn't done.

## The purposes (why the owner asks what they ask)
1. **Truth over belief** — would I bet on this? What evidence turns it into a fact?
2. **Do no harm** — what that works today could this break? What could it cost the owner's business (stores, money, privacy, legal, reputation)?
3. **Don't settle on the first answer (mine, the owner's, or one the owner approved)** — what would a better or cheaper way to reach the *goal* look like? Ask it **before starting work**, not only before presenting, and **write it down before building**: one line `Decisions: goal <what it's for> · ways <different ways to reach that goal, not only ways to build the first idea> · alt: <the alternatives compared for each material choice of the chosen way>` (the optional gate in `tools/selfcheck.py` checks for it). An owner's proposal or "yes" settles *whether*, not *how*: improve it, don't only make it safe.
4. **Plan for being wrong** — when it fails, who notices, and what does the miss cost vs a safeguard?
5. **Stay healthy over time** — does it learn, clean up, and keep recurring costs low?
6. **Outlive this session** — would someone with no memory find it, understand it and repeat it?
7. **Prove it in reality** — have I run it, or only reasoned about it?
8. **Compound the learning, and be honest** — worth a playbook? What's still not perfect?

## Top gotchas
- Copying the example questions instead of deriving new ones for the task.
- Anchoring on the approach the owner proposed or approved: before starting, look for a better way to the goal (cases 15, 17).
- Over-checking a trivial change, or reviewing forever: size it, stop when a pass finds nothing.
- A reasoned explanation presented as fact (this session's first answer): say "likely" until evidence confirms.
- Owner decisions (prices, publishing, legal answers, what to leave unfixed) still go to the owner.

---

## Same purpose, different questions (examples)

| Purpose | Voice bug fix (real, 2026-10-24) | Knowledge-base design (real, 2026-10-24) | Payment screen (illustrative) | Store/legal form (illustrative) |
|---|---|---|---|---|
| 1 Truth | Read the iPhone log for the real error | Run the searches for real | Sandbox purchase on a real phone | Read the official source, not memory |
| 2 No harm | Android path and other errors unchanged? | Existing playbooks still found? | Free features still free; restore still works? | Earlier answers still consistent? |
| 3 Alternatives | Narrow vs broad retry rule | Index vs keyword line vs skills | Fewer taps? | A truer answer than the one that just passes? |
| 4 Being wrong | Online retry; no mic after Stop | Steps 2–3 back up step 1 | Paid but not unlocked → restore path | What if review rejects it: is it reversible? |
| 5 Over time | Remember per session; no repeated failure | Miss list, clean-up, per-use cost | Renewal, expiry, offline | Re-check when the store's rules change |
| 6 Outlive | CLAUDE.md note, test, comment | Rule in the always-loaded file | Owner guide steps | Decision recorded with its reason |
| 7 Reality | TestFlight build on the phone | Fresh-session test | Real store sandbox | Preview shows what was submitted |
| 8 Compound | Voice playbook; leave list | Playbook of the design | Billing playbook | Store playbook update |

## Learning loop

Never change these rules just because a rule says "improve", and never for wording polish.
A change needs a trigger — a **real miss**, the **owner's request**, or a **concrete defect**
(a contradiction, a wrong fact, a broken search, the global bullet over its cap) — and must be
**measurably better** (the method: `core/self-review-benchmark.md`; your data: `self-review-log.md`
in the knowledge-base folder).
1. Real miss (the owner had to ask something the purposes should have caught, the
   `🟣 Self-check` line was missing or empty, or the owner says "that's a miss"): add a row to
   the miss log in `self-review-log.md` (type `gap`/`lapse`/`repeat`, newest last) and a case,
   then run `core/tools/benchmark_summary.py`; review if it says REVIEW DUE. A `lapse` needs no
   rule change.
2. Draft a change (sharpen a purpose, add an example, or — only if it fits none — a purpose;
   merge before adding).
3. Score old vs new on every case. Accept only if it fixes its trigger, no earlier case fails,
   and the global bullet doesn't grow. Otherwise keep the old version (the logged miss stays).
4. Accepted: update the playbook and the global bullet together; changelog line with the
   **old wording** (for a revert) and the score; an entry in the knowledge-base folder's
   `core-changes.md` (why, evidence, undo, outcome pending). Reviews fill in each entry's
   outcome (right / wrong / unclear) from the trend.
5. When the owner confirms a `🟣 Self-check` line saved them a round, set `verified:` to that date.

## Where it came from (owner's prompts, 2026-10-24 → purpose)

"Are you sure? Can you see the logs?" → 1 · "Check the previous model's fix", "code review first" → 1, 2 ·
"Don't break anything, no new bugs" + checklist (regressions, edge cases, duplication, assumptions) → 2, 8 ·
"Any better way with even less tokens?" → 3 · "Use 2–3 methods as backups" → 4 ·
"Add misses to a list, delete when adding" → 5 · "Will reading that file every time cost tokens?" → 5 ·
"Will a future/new session know and do what you did?" → 6 · "Is it perfect?", "double-check the full logic" → 2, 8 ·
"Make it a knowledge base itself" → 8 · "Understand the purpose, not the exact questions; don't loop" → steps 1–4 ·
"Please be concise" (many times) → step 5 · "Improve it again until nothing is left" (important, foundational work) → step 4.

The always-loaded short version lives in the owner's global CLAUDE.md ("Before presenting…"); keep both in step.
The owner's own "Plans: include…" list there is what a plan must *show*; these purposes are how to *think*.
Never edit the owner's list to match; link to it.

## Changelog

- 2026-10-24: created from the owner's prompts in the voice-fix + knowledge-base session.
- 2026-10-24: rewritten as purposes (not fixed questions) after its own dry run: added stakes sizing, stop rule, learning loop, cross-domain examples, honest `verified:`.
- 2026-10-24: 3 more passes on itself (owner asked to repeat until nothing is left): scope incl. diagnoses, unsure → high, repeat-until-clean rule (max 5), concise presenting, business harm in purpose 2, link to the owner's Plans list, illustrative examples labelled. Pass 3 found nothing.
- 2026-10-24: visible `Self-check` line (owner: to see it ran and to test it).
- 2026-10-24: 🟣 marker (markdown has no colours); "improve at once" replaced by benchmark-gated
  changes (owner: only with a purpose, only if better). Old wording: "When I still have to ask
  something, improve it at once, in the same turn, per …". Score: 13/13 cases.
- 2026-10-24 (owner's request): change triggers widened to miss / owner request / concrete defect
  (old: "only for a real miss"); "that's a miss" shortcut; self-graded and cap origin labelled;
  global bullet trimmed back under 200 words (old: "derive the questions I would ask…",
  "never claim a check that wasn't done", "When I had to ask something these should have caught…").
  Score: 14/14 (self-graded).
- 2026-10-24: cap may be raised (owner) with guardrails in the benchmark: move out, trim, benchmark, owner approval, ≤ +25 words.
- 2026-10-24: miss (case 15): the 200-word bullet cap and "+25 per raise" replaced by a whole-file
  budget (~700 words), one in one out, ranked by benchmark evidence, protected owner lines.
  Purpose 3 now "(mine or yours)"; 🟣 line shows `<k>/8 purposes`. Old wording: "don't settle on
  the first answer ·", "(<low|high>, <n> pass)", "a fresh session finds and repeats it". Score 15/15 (self-graded).
- 2026-10-24: monitoring (owner): miss types gap/lapse/repeat, `tools/benchmark_summary.py`
  (counts, never hand-kept), review every 5 rows or on request, spot-checks. Case 16 (lapse). 16/16.
- 2026-10-24: repeat of case 15 (case 17): applies **before starting** too; purpose 3 covers approved
  plans; 🟣 line names `alt <options compared>`. Old wording: "Before presenting a fix…",
  "(mine or yours)", "checked <…> · fixed", "Log every miss (I had to ask what these should catch,
  or I say …)", "compound the learning and say what's still open". 17/17 (self-graded).
- 2026-10-24: owner's trend view: the summary script also writes `self-review-trend.html` and a daily
  snapshot in `self-review-history.csv`; `tools/self-review-trend.bat` (double-click, no AI).
- 2026-10-24 (owner's request, 3 passes on the trend tools): 14-day verdict windows with numbers,
  "rough / zero can mean nothing logged" note, budget read from the benchmark (note if not found),
  history file locked by Excel → report still updates with a note. Rules unchanged.
- 2026-10-25 (owner's design): `tools/selfcheck.py` hooks check the work independently of the 🟣
  line: a gate before the first risky change and before plan approval, free checks plus an
  independent `claude -p` check after replies (sent back once), and counting of what the owner
  still had to ask. Rules unchanged (global CLAUDE.md +0 words); 19 cases, 18 pass (case 19
  waits for its rule change).
- 2026-10-25 (owner approved): case 19 (repeat of 17, purposes 1 + 3).
  - Purpose 3 now says: before building, write `Decisions: … · alt: …`. It's a visible line the
    gate can check, the review's planned "list material decisions, alternatives for each".
  - In the owner's global file, "Log every miss (I had to ask, or said "that's a miss")" became
    "Log every miss.", since the prompt hook detects both and the benchmark defines a miss.
    `CLAUDE-snippet.md` keeps the brackets, because users without the hooks need them.
  - Old wording: "don't settle on the first answer (mine, yours or approved)"; "Log every miss (I
    had to ask, or said "that's a miss")". Global file 699 → 698 words.
  - Score: 19/19 (self-graded). Case 19's "read the source" half is purpose 1, so it counts as a
    lapse there.
- 2026-10-25 (owner approved): repeat of case 19 (case 21). The `Decisions` line was written, but
  its alternatives were ways to build the first idea, not ways to reach the goal.
  - Purpose 3's line is now `Decisions: goal … · ways … · alt: …`: naming the goal first makes
    the compared ways start from it. The gate in `tools/selfcheck.py` now passes only a line with
    goal and ways.
  - To stay in budget, "guesses labelled as guesses" became "guesses labelled" (case 14 still
    passes). Global file 698 → 700 words.
  - Old wording: "before building, write "Decisions: … · alt: …"".
  - Score: 20/21 (self-graded; case 20 waits for the owner).
- 2026-10-25 (owner approved): case 22 (gap). Global file, under "Never decide for me": "Choices
  the goal already answers aren't mine: decide them, say so in one line." The owner's heading
  read like "ask about everything"; this line removes that conflict. No swap possible (the
  section is the owner's wording), so the owner raised the budget 700 → 715 words. The selfcheck
  offer check enforces it in every project. Score: 21/22 (case 20 waits until it repeats).
- 2026-10-31 (owner approved, review of 9 misses): case 24 (repeat of the 10-29 plan-review lapse).
  - Global file: "Plans: before asking for approval, walk each step through the code it changes and
    include:"; to stay at 715 words, "problems found in your draft" and "what's fixed and what's left".
  - Old wording: "review the plan yourself and include:", "problems you found in your own draft;",
    "what is fixed and what is left." Global file 715 → 715 words.
  - Checker prompt (private `selfcheck-checker-prompt.md`): a plan or fix list whose self-review names
    no code it was checked against gets the question "was each step walked through the actual code?".
  - Score: 23/24 (self-graded; case 20 still waits).
- 2026-11-22 (owner approved, review of 26 misses since 11-12): rules text unchanged except one owner line in
  the global file ("Suggest what to do next, but never start a task I didn't ask for…", +30 words, owner's
  request; over budget: 1305 / 715; the owner declined merging the store sections (−176), keep them). Lapses fixed by hooks, not wording: playbook `triggers:` (case 27), question check + checker lines
  (cases 28, 29), log guard + shrink warning (the 11-12 log overwrite), daily review suggestion (owner goal: a
  self-improving loop that never starts tasks unasked). Score: 23/24 old cases unchanged (case 20 waits);
  cases 25–35 logged, hooks judged by replay (core-changes 2026-11-22).
