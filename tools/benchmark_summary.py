"""Summarise the self-review miss log, so sessions never read or count it by hand.

Usage (from the knowledge-base folder): python -I core/tools/benchmark_summary.py [path to self-review-log.md]
Default log: self-review-log.md in the folder above core/ (the owner's private data, never in this repo).

- Prints a short summary (for sessions): counts by type, rows since the last review, REVIEW DUE.
- Writes for the owner (free to view, no AI needed):
  - self-review-history.csv: one snapshot row per day (re-running the same day replaces it);
  - self-review-trend.html: weekly misses incl. zero weeks, a better/same/worse verdict, repeats,
    gaps vs lapses, the global CLAUDE.md size vs its budget, and the snapshot history.
"""

import csv
import datetime
import html
import pathlib
import re
import sys
from collections import Counter

REVIEW_EVERY = 5
BUDGET_FALLBACK = 700  # used only if the log's "Budget: about **N words**" can't be read
# core/tools/benchmark_summary.py → the knowledge-base folder is two levels above tools/.
KB = pathlib.Path(__file__).resolve().parent.parent.parent
DEFAULT = KB / "self-review-log.md"
GLOBAL_MD = pathlib.Path.home() / ".claude" / "CLAUDE.md"
# History and report are written next to the log read (tests never touch the real ones).
HISTORY = REPORT = None
MISS_TYPES = ("gap", "lapse", "repeat")
FIELDS = ["date", "misses_total", "gap", "lapse", "repeat", "misses_last_7_days",
          "cases", "global_words", "budget_words"]


def log_rows(text):
    in_log = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_log = line.startswith("## Miss log")
            continue
        if not in_log or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("Date", "") or set(cells[0]) <= set("-: "):
            continue
        yield cells[0], cells[1].lower()


def count_cases(text):
    in_cases, n = False, 0
    for line in text.splitlines():
        if line.startswith("## "):
            in_cases = line.startswith("## Cases")
            continue
        if in_cases and re.match(r"^\|\s*\d+\s*\|", line):
            n += 1
    return n


def week_start(d):
    return d - datetime.timedelta(days=d.weekday())


def main():
    global HISTORY, REPORT
    path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    HISTORY = path.parent / "self-review-history.csv"
    REPORT = path.parent / "self-review-trend.html"
    text = path.read_text(encoding="utf-8")
    log = list(log_rows(text))
    if not log:
        print("No miss-log rows found: check the table format in", path)
        return 1

    today = datetime.date.today()
    misses, bad_dates = [], 0
    for d, t in log:
        if t not in MISS_TYPES:
            continue
        try:
            misses.append((datetime.date.fromisoformat(d), t))
        except ValueError:
            bad_dates += 1
    by_type = Counter(t for _, t in misses)
    last_review = max((i for i, (_, t) in enumerate(log) if t == "review"), default=-1)
    since = sum(1 for _, t in log[last_review + 1:] if t in MISS_TYPES)
    last7 = sum(1 for d, _ in misses if (today - d).days < 7)
    # 14-day windows: steadier than week vs week with such small numbers.
    last14 = sum(1 for d, _ in misses if (today - d).days < 14)
    prev14 = sum(1 for d, _ in misses if 14 <= (today - d).days < 28)
    repeats14 = sum(1 for d, t in misses if t == "repeat" and (today - d).days < 14)
    if repeats14:
        verdict = "WORSE: a fix failed (repeat) in the last 14 days"
    elif last14 < prev14:
        verdict = f"BETTER: {last14} misses in the last 14 days, {prev14} in the 14 before"
    elif last14 > prev14:
        verdict = f"WORSE: {last14} misses in the last 14 days, {prev14} in the 14 before"
    else:
        verdict = f"SAME: {last14} misses in the last 14 days and in the 14 before"
    budget_match = re.search(r"about \*\*(\d+) words\*\*", text)
    budget_words = int(budget_match.group(1)) if budget_match else BUDGET_FALLBACK

    try:
        global_words = len(GLOBAL_MD.read_text(encoding="utf-8").split())
    except OSError:
        global_words = ""
    cases = count_cases(text)

    # Weekly counts from the first miss to this week, zero weeks included.
    weeks = Counter(week_start(d) for d, _ in misses)
    first = min(weeks) if weeks else week_start(today)
    weekly, w = [], first
    while w <= week_start(today):
        weekly.append((w, weeks.get(w, 0)))
        w += datetime.timedelta(days=7)

    # Daily snapshot history (same day replaced).
    snapshot = {"date": today.isoformat(), "misses_total": len(misses), "gap": by_type["gap"],
                "lapse": by_type["lapse"], "repeat": by_type["repeat"],
                "misses_last_7_days": last7, "cases": cases, "global_words": global_words,
                "budget_words": budget_words}
    history, notes = [], []
    if not budget_match:
        notes.append(f"Budget line not found in the log: using {BUDGET_FALLBACK} words.")
    try:
        if HISTORY.exists():
            with HISTORY.open(encoding="utf-8", newline="") as f:
                history = [r for r in csv.DictReader(f) if r.get("date") != snapshot["date"]]
        history.append({k: str(v) for k, v in snapshot.items()})
        with HISTORY.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(history)
    except PermissionError:
        # Excel locks an open CSV: keep going, the report still updates.
        notes.append(f"History not saved: close {HISTORY.name} (open in Excel?) and run again.")

    try:
        write_report(today, verdict, by_type, since, weekly, global_words, budget_words, cases,
                     history, bad_dates, notes)
    except PermissionError:
        notes.append(f"Report not saved: {REPORT.name} is locked.")
    for note in notes:
        print(note)

    # Short summary for sessions.
    print("Misses:", len(misses), "| gap", by_type["gap"], "| lapse", by_type["lapse"],
          "| repeat", by_type["repeat"])
    print("Verdict:", verdict)
    if bad_dates:
        print("Rows with unreadable dates:", bad_dates)
    print("Since last review:", since, "(review every", REVIEW_EVERY, ")")
    if by_type["repeat"]:
        print("WARNING: repeats found - a fix failed; check them first.")
    if since >= REVIEW_EVERY:
        print("REVIEW DUE")
    print("Report for the owner:", REPORT)
    return 0


def write_report(today, verdict, by_type, since, weekly, global_words, budget_words, cases,
                 history, bad_dates, notes):
    e = html.escape
    top = max([n for _, n in weekly] + [1])
    colour = "#2e7d32" if verdict.startswith("BETTER") else (
        "#c62828" if verdict.startswith("WORSE") else "#555")
    bars = "".join(
        f"<tr><td>{w.isoformat()}</td><td><div class='bar' style='width:{n / top * 100:.0f}%'>"
        f"</div></td><td>{n}</td></tr>" for w, n in weekly)
    hist = "".join(
        "<tr>" + "".join(f"<td>{e(str(r.get(k, '')))}</td>" for k in FIELDS) + "</tr>"
        for r in reversed(history))
    budget = (f"{global_words} / {budget_words} words" if global_words != ""
              else "global CLAUDE.md not found")
    note_html = "".join(f"<p class='verdict' style='color:#c62828'>{e(n)}</p>" for n in notes)
    REPORT.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Self-review trend</title><style>
body{{font-family:system-ui,sans-serif;max-width:860px;margin:24px auto;padding:0 16px;color:#222;background:#fff}}
h1{{font-size:1.4em}} .verdict{{font-size:1.2em;font-weight:600;color:{colour}}}
table{{border-collapse:collapse;width:100%;margin:8px 0 20px}} td,th{{border-bottom:1px solid #ddd;padding:4px 6px;text-align:left;font-size:.9em}}
.bar{{background:#7e57c2;height:12px;min-width:2px}} .muted{{color:#666;font-size:.85em}}
</style></head><body>
<h1>Self-review trend</h1>
<p class="muted">Updated {today.isoformat()} by tools/benchmark_summary.py. Fewer misses = better. Repeats = a fix failed.</p>
<p class="verdict">{e(verdict)}</p>{note_html}
<p class="muted">Rough: misses are counted only when noticed and logged (or you say "that's a miss"),
and the amount of work done isn't counted. Zero misses can also mean nothing was logged.</p>
<p>Misses: gap {by_type['gap']} · lapse {by_type['lapse']} · repeat {by_type['repeat']} ·
since last review {since} (review every {REVIEW_EVERY}) · cases {cases} · global CLAUDE.md {e(budget)}
{' · unreadable dates: ' + str(bad_dates) if bad_dates else ''}</p>
<h2>Misses per week (week starting)</h2><table>{bars}</table>
<h2>History (one snapshot per day the script ran)</h2>
<table><tr>{''.join(f'<th>{e(k)}</th>' for k in FIELDS)}</tr>{hist}</table>
<p class="muted">gap = no rule covered it · lapse = a rule existed but wasn't followed · repeat = it came back after its fix.</p>
</body></html>""", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
