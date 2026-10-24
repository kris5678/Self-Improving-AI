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
3. **Don't settle on the first answer (mine, the owner's, or one the owner approved)** — what would a better or cheaper way to reach the *goal* look like? Ask it **before starting work**, not only before presenting. An owner's proposal or "yes" settles *whether*, not *how*: improve it, don't only make it safe.
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
   **old wording** (for a revert) and the score.
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
