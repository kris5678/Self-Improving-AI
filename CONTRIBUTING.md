# Contributing

Improvements are welcome. The method improves itself by the same rules it asks of the assistant,
so pull requests follow them too:

1. **A trigger.** Say which real miss (a question you had to ask that the rules should have
   caught), concrete defect (a contradiction, a wrong fact, a broken search) or missing need
   your change fixes. No wording polish on its own.
2. **A case.** Add the miss as an anonymised example in your PR description: situation → what you
   had to ask → which purpose should have caught it.
3. **Still passes the earlier cases.** Read `self-review-benchmark.md`, rule 2: a session reading
   only the new text must still ask the right question for the cases in `templates/` and in
   your PR's description.
4. **Fits the budget.** `CLAUDE-snippet.md` should not grow; if it must, show what you removed
   (one in, one out) or explain why nothing can go.
5. **No personal data.** Run `python -I tools/install_hooks.py` once; commit with a no-reply email.
   Never include real names, emails, paths, account or project names.
6. **Small and focused.** One change per PR; update every file that repeats the rule
   (`CLAUDE-snippet.md`, the playbook, the benchmark) in the same PR.

Bug reports and ideas: open an issue with the situation and what you expected.
