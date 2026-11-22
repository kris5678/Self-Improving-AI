# Core change log (private audit trail)

Every change to `core/` (the method: rules, playbooks, tools, templates, README), with **why**,
the **evidence** at the time, **how to undo it**, and later the **outcome**. Use it to audit what
went right or wrong as the method improves itself, and to go back when something broke.

- Written by the session making the change, in the same turn. Newest **last**.
- **Outcome** is filled in at reviews (`core/self-review-benchmark.md`): `right`, `wrong` or
  `unclear`, with the evidence. Until then: `pending`.
- Not a playbook (no keywords line).

```
### <YYYY-MM-DD> — <short title>
- What: <files / behaviour>
- Why: <owner request | miss (case n) | defect> — <one line>
- Evidence: <tests, benchmark score, live run>
- Undo: <old wording / setting / how to remove>
- Outcome: pending
```

---
