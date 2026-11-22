"""Self-check hooks for Claude Code: catch misses before the owner has to ask, and count the ones that slip.

One script for three hook events (the event name is in the hook's JSON on stdin):
- Stop: after each reply. Free checks on the 🟣 Self-check line; on high-stakes replies an
  independent one-shot check (a separate `claude -p` session, small model). Something important
  missing → the reply is sent back once (shown to the owner as a 🔵 line).
- PreToolUse: before the first risky change of a reply (and before a plan is shown for approval):
  were the decisions and alternatives listed? If not, the independent check; a flagged
  question blocks the change once, before anything is built.
- UserPromptSubmit: counts the owner's prompts that show a miss slipped through ("that's a miss",
  doubt, correction, check request) and tells the session to log real misses.

Manual use (from the knowledge-base folder):
  python -I core/tools/selfcheck.py rate <id> right|wrong [note]   record the owner's rating of check #id
  python -I core/tools/selfcheck.py backfill-history               count past prompts from ~/.claude/history.jsonl (once)

Private data lives next to core/ (never in this repo): selfcheck-config.json, selfcheck-checker-prompt.md
and the selfcheck/ folder (log, queue, per-session state). Create the file selfcheck-off there to turn
every hook off at once. Hooks never block the session on an error: they exit 0 and do nothing.
"""

import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

# core/tools/selfcheck.py → the knowledge-base folder is two levels above tools/ (tests override it).
KB = pathlib.Path(os.environ.get("SELFCHECK_KB") or pathlib.Path(__file__).resolve().parent.parent.parent)
CORE = pathlib.Path(__file__).resolve().parent.parent
DATA = KB / "selfcheck"
CHECKS = DATA / "checks.jsonl"
QUEUE = DATA / "queue.jsonl"
CHILD_ENV = "SELFCHECK_CHILD"  # set inside the independent check's own session: hooks do nothing there

DEFAULTS = {
    "send_back": True,           # False: log only, never send a reply back or block a change
    "stop_checks": True,
    "gate": True,
    "independent_check": True,
    "model": "claude-haiku-5-5",
    "effort": "medium",
    "exchanges": 2,              # owner prompt + tools run + final reply, the latest N
    "check_timeout_seconds": 60,
    "max_chars_per_message": 4000,
    "presenting_min_words": 150,
    "notes_to_session": True,    # the short "may be a miss, log it" note on matching prompts
    "playbook_reminder": True,   # send back once when a run of changes ends with no playbook written
    "playbook_after_risky_replies": 3,
    "offer_check": True,         # send back a reply that ends by handing the owner a choice the goal answers
    "playbook_triggers": True,   # a playbook's `triggers:` line sends its first matching call back once
    "question_check": True,      # a reply asking the owner something gets the independent check
    "review_reminder": True,     # once a day: the session suggests a due review (never runs it)
}

# Patterns written from the owner's own prompts (history since 2026-05). Order = priority.
KINDS = [
    ("miss", r"\bthat'?s an? miss\b|\bthat was an? miss\b"),
    ("doubt", r"\bare you (sure|certain)\b|\bhow (sure|confident) are you\b"
              r"|\b(did|have) you (check|test|verify|ask|look|consider|think|run|try|read|review)\w*\b"
              r"|\bwhy (didn'?t|did not|haven'?t) you\b|\byou (forgot|missed|skipped|ignored|didn'?t follow)\b"
              r"|\byou should have\b|\bis (it|this|that)( now)? perfect\b"
              r"|\b(any|a) (better|cheaper|simpler) (way|option|approach)s? (than|to)\b|\bthink of any better\b"
              r"|\bany (better|cheaper|simpler) (way|option|approach)s?\b"
              r"|\bwill (a|the) (future|new|fresh|next) session\b|\bhow (does|do|will) (it|we|you) (know|measure|monitor)\b"
              r"|\bwhere did you get\b"),
    ("correction", r"^\s*no[,.!]\s|\b(that'?s|this is|it'?s) (wrong|not right|incorrect)\b"
                   r"|\bnot what i (asked|said|meant)\b|\bi (already|just) (said|told|asked|answered|explained)\b"
                   r"|\bi told you\b|\b(still|again) (not working|doesn'?t work|wrong|broken|the same|fail\w*)\b"
                   r"|\b(don'?t|do not|stop|no need to) (keep )?(tell|remind|mention)\w* (me )?(about|again)\b"
                   r"|\b(don'?t|do not|stop) (stop and )?(keep )?ask(ing)? me\b"
                   r"|\b(as|like) i (said|told you|mentioned)\b|\bi('ve| have) (already )?(said|told you|answered|mentioned)\b"),
    ("check-request", r"\bdouble.?check\b|\bmake sure (you|we) (didn'?t|don'?t|did not|do not) (miss|break|introduce)\b"
                      r"|\b(anything|nothing) (you )?missed\b|\b(will|does|did) (it|this|the fix|your fix|this change) (break|introduce)\b"
                      r"|\b(don'?t|do not|doesn'?t|not) (break|introduce new bugs)|\bnew bugs\b"
                      r"|\bthink (about|of) (all )?(the )?edge cases\b|\bcode review (the fix )?first\b"),
]
KIND_RE = [(k, re.compile(p, re.I | re.M)) for k, p in KINDS]
NOTE_KINDS = {"miss", "doubt", "correction"}
SLASH_RE = re.compile(r"^\s*/[A-Za-z][\w:.-]*(\s|$)")
PASTE_RE = re.compile(r'<pasted_content id="[^"]*">.*?</pasted_content id="[^"]*">', re.S)
PASTE_TAG_RE = re.compile(r'</?pasted_content id="[^"]*">')
# Text Claude Code puts where the owner's messages go, which the owner didn't write.
SYSTEM_TEXT = ("<command-", "<bash-", "<local-command", "<task-notification", "<system-reminder")

LINE_RE = re.compile(r"🟣\s*Self-check\s*\((?P<stakes>low|high)\s*,\s*(?P<passes>\d+)\s*pass(?:es)?\s*,"
                     r"\s*(?P<k>\d+)\s*/\s*8 purposes\)\s*:(?P<rest>.*)", re.I)
PARTS_RE = re.compile(r"checked\s*(?P<checked>.*?)\s*·\s*alt\s*(?P<alt>.*?)\s*·\s*fixed\s*(?P<fixed>.*?)"
                      r"\s*·\s*open\s*(?P<open>.*)$", re.I)
EMPTY = {"", "none", "-", "—", "n/a", "na", "…", "<…>", "nothing"}
# The case-19/21 rule's findable line: "Decisions: goal … · ways … · alt: …" (written before
# building). The goal and the ways must be there: alternatives that are only ways to build the
# first idea were the case-21 miss.
DECISIONS_RE = re.compile(r"(?im)^\W*decisions?\s*:.*\bgoal\b.*\bways?\b.*\balt\b")

# git's own options may come before the command word: `git -C core push`, `git -c x=y commit`.
GIT_OPTS = (r"(?:\.exe)?[\"']?(?:\s+(?:-C\s+(?:\"[^\"]*\"|'[^']*'|\S+)|-c\s+(?:\"[^\"]*\"|'[^']*'|\S+)"
            r"|--(?:git-dir|work-tree|namespace)(?:=|\s+)(?:\"[^\"]*\"|'[^']*'|\S+)|--[\w-]+))*\s+")
# …and the git commands that publish, rewrite history or throw away uncommitted work.
GIT_RISKY = (r"(?:push|commit|reset\s+--hard|rebase|clean\s+(?:-\w+\s+)*(?:-\w*f\w*|--force)"
             # case matters for these flags: -D force-deletes a branch (-d doesn't), -S/-W are restore's
             # --staged/--worktree (-s is --source and still discards work).
             r"|branch\s+(?:-\w+\s+)*(?-i:-\w*D)\w*|stash\s+(?:drop|clear)|checkout\s+(?:\S+\s+)?(?:--|\.)(?=\s|$)"
             r"|restore(?=\s)(?![^;&|\n]*(?:--staged|(?-i:\s-S\b)))|restore(?=[^;&|\n]*(?:--worktree|(?-i:\s-W\b))))"
             r"(?![\w-])")
RISKY_COMMAND = re.compile(
    r"\bgit" + GIT_OPTS + GIT_RISKY +
    r"|\bflutter\s+build\b|codemagic\.io/builds|\bfastlane\b"
    r"|\beas\s+(build|submit)\b|\bsupabase\s+(db|migration|functions\s+deploy)\b|\bpsql\b|\bdrop\s+table\b"
    r"|\bgh\s+(release|repo\s+delete)\b|\bnpm\s+publish\b|" + r"(?P<delete>"
    # deletes: rm with a recursive flag in any position, Remove-Item, del, rmdir/rd with /s or -r…
    r"\brm\s+(?:--?[\w-]+\s+)*(?:-\w*[rR]\w*|--recursive)\b|\bRemove-Item\b|(?<![$\w])del(?!\s*=)\s+"  # not $del = …
    r"|\b(?:rmdir|rd)\s+(?:[^;&|\n]*\s)?(?:/s|-r\w*)\b)", re.I)
SEGMENT_END = re.compile(r";|&&|\|\||\||\n")
# Text written into a file isn't run: `cat > fix.ps1 <<'EOF' … EOF`, `@' … '@ | Set-Content x`. A
# heredoc fed to a program (python - <<EOF, bash <<EOF) still counts.
HEREDOC_RE = re.compile(r"^(?P<head>[^\n]*?)<<-?\s*([\"']?)(?P<tag>\w+)\2(?P<tail>[^\n]*)\n(?P<body>.*?)^[ \t]*(?P=tag)[ \t]*$",
                        re.S | re.M)
HERESTRING_RE = re.compile(r"@([\"'])\r?\n.*?\r?\n\1@(?=\s*\|\s*(?:Set-Content|Add-Content|Out-File)\b)", re.S | re.I)


def without_written_text(command):
    def heredoc(m):
        head = SEGMENT_END.split(m.group("head"))[-1]
        writes = re.match(r"\s*(cat|tee)\b", head) and (">" in head + m.group("tail") or head.lstrip().startswith("tee"))
        if writes and "|" not in m.group("tail"):
            return m.group(0).replace(m.group("body"), "")
        return m.group(0)
    return HERESTRING_RE.sub("@''@", HEREDOC_RE.sub(heredoc, command))
ARG_RE = re.compile(r"\"[^\"]*\"|'[^']*'|\S+")
RISKY_PATH = re.compile(
    r"(payment|billing|subscri|revenuecat|purchase|paywall|migration|\.sql$|settings(\.local)?\.json$"
    r"|CLAUDE\.md$|privacy|terms|AndroidManifest\.xml$|Info\.plist$|\.entitlements$|key\.properties"
    r"|build\.gradle)", re.I)
RISKY_DOC = re.compile(r"^CLAUDE\.md$|privacy|terms", re.I)
# Browser (Claude in Chrome): a click's action_summary starts with what it does. Only the first verb
# counts, so "Opens the payments page (view only)" or "Cancels without saving" aren't risky.
BROWSER = "mcp__claude-in-chrome__"
RISKY_CLICK = re.compile(
    r"^\W*(?:(?:clicks|presses|taps|hits)\s+(?:the\s+|on\s+)?)?(sav|submit|send|publish|releas|roll|delet|remov"
    r"|revok|grant|invit|creat|upload|activat|deactivat|confirm|appl|enabl|disabl|pay|purchas|buy|subscrib"
    r"|approv|accept|transfer|connect|discard|archiv|promot|updat|start|add|attach|finish|install|uninstall"
    r"|reset|restor|merg|deploy|launch|sign|regenerat|rotat)\w*", re.I)
# The owner saying a task is finished (from the owner's prompt history): "done, all steps worked",
# "tested on iphone it's working", "revenuecat is green now".
FINISHED_RE = re.compile(
    r"\b(it'?s|is|now|all|everything'?s?) (now )?(working|works|green|done|live|fixed|good|approved|sorted)\b"
    r"|\b(tested|checked|works|working)\b[^.?!]{0,40}\b(fine|ok|okay|now|on (my |the )?(phone|iphone|android|device))\b"
    r"|\bthank(s| you)\b|\bthat'?s (all|it|done)\b|^\s*(done|finished|perfect|great)\b", re.I)
# Knowledge-base files that aren't playbooks: writing them doesn't count as "lessons saved".
NOT_PLAYBOOKS = {"self-review-log.md", "core-changes.md", "handoff.md", "self-improvement-roadmap.md"}
# Lessons saved somewhere other than a playbook (project memory, the miss log): one real chat
# updated its memory 9 times and wrote no playbook.
LESSON_FILES = re.compile(r"/\.claude/projects/[^/]+/memory/[^/]+\.md$|/self-review-log\.md$", re.I)
WRITE_TARGET_RE = re.compile(
    r"(?:(?<![0-9&])>>?|\btee\s+(?:-a\s+)?|\b(?:Set|Add)-Content\s+(?:-Path\s+)?|\bOut-File\s+(?:-FilePath\s+)?"
    r"|\bsed\s+-i\S*\s+(?:'[^']*'|\"[^\"]*\"|\S+)\s+)\s*[\"']?([^\s\"'|;&>]+\.md)\b", re.I)
# A reply ending by handing the owner a choice ("If you want, I can also…", "Shall I…?"). The
# owner: "if it benefits the goal then you don't need to ask me" (2026-10-25, all projects).
OFFER_RE = re.compile(
    r"(?im)^[^\n]*(?:\bif you(?:'d)? (?:want|like|prefer)\b[^\n]{0,40}\b(?:i can|i'll|i could)\b"
    r"|\b(?:want|would you like) me to\b|\bshall i\b|\bdo you want me to\b"
    r"|\bshould i (?:also|go ahead|add|copy|make|update|fix|write|create|move|keep)\b"
    r"|\blet me know if you(?:'d)? (?:want|like)\b|\bi can also\b[^\n]*\bif you\b)[^\n]*")
# …unless the choice is really the owner's: money, publishing, deleting, permissions, commits.
OWNER_CALL_RE = re.compile(
    r"\b(commit\w*|push\w*|publish\w*|submit\w*|review|release\w*|deploy\w*|merg\w*|delet\w*|remov\w*"
    r"|pay\w*|purchas\w*|pric\w*|charg\w*|refund\w*|permission\w*|grant\w*|approv\w*|accounts?|password\w*"
    r"|sign(?:ing)? (?:in|up)|budget|cost\w*|spend\w*|send\w*|email\w*|post|posting|invite\w*|public\w*"
    r"|contract\w*|legal|names?|naming|design|colou?rs?|wording)\b", re.I)
RISKY_JS = re.compile(r"\.click\(|\.submit\(|requestSubmit|dispatchEvent"
                      r"|method\s*:\s*['\"](POST|PUT|PATCH|DELETE)", re.I)
TEMP_RE = re.compile(r"[\\/](temp|tmp|scratchpad)[\\/]|\$S\b|\$TMP|\$TEMP|\$env:(?:TEMP|TMP)\b|mktemp", re.I)
REJECTED = "the user said:"
LEAD_RE = re.compile(r"^(?:\s*(?:\w+=(?:\"[^\"]*\"|'[^']*'|\S+)|cd\s+(?:\"[^\"]*\"|\S+))\s*(?:;|&&)?\s*)+")


# ---------- small helpers ----------

def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


RETRIES = 5  # hooks can run at the same time (parallel tool calls, several sessions)


def retry(action):
    """Windows refuses to read or replace a file while another hook is replacing or reading it
    (PermissionError): try again shortly instead of losing the state."""
    for attempt in range(RETRIES):
        try:
            return action()
        except PermissionError:
            if attempt == RETRIES - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


def load_json(path, default):
    try:
        return json.loads(retry(lambda: path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")  # own name: two hooks never share one
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        retry(lambda: os.replace(tmp, path))
    finally:
        try:
            tmp.unlink()  # only still there when writing or replacing failed
        except OSError:
            pass


def append(path, entry):
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")

    def write():  # one unbuffered write: lines from hooks running at once don't get mixed
        with open(path, "ab", buffering=0) as f:
            f.write(line)
    retry(write)


def config():
    cfg = dict(DEFAULTS)
    cfg.update(load_json(KB / "selfcheck-config.json", {}))
    return cfg


def next_id():
    path = DATA / "counter.txt"
    try:
        n = int(retry(path.read_text)) + 1
    except FileNotFoundError:
        n = 1
    except (OSError, ValueError):
        # Unreadable counter: continue after the highest id in the log, never restart at 1.
        n = max([e.get("id") for e in read_jsonl(CHECKS) if isinstance(e.get("id"), int)] + [0]) + 1
    save_json(path, n)  # written whole: a reader never sees a half-written number
    return n


def session_state(sid):
    state = load_json(DATA / "sessions" / f"{safe(sid)}.json", {})
    return state if isinstance(state, dict) else {}  # a damaged file starts the session fresh


def save_session(sid, state):
    save_json(DATA / "sessions" / f"{safe(sid)}.json", state)


def safe(text):
    return re.sub(r"[^\w-]", "_", str(text or "unknown"))[:80]


HEARTBEAT_EVERY = datetime.timedelta(minutes=10)  # the report only asks "ran in the last 2 days?"


def heartbeat(event):
    """Last run time per hook event, written at most every 10 minutes (fewer writes, fewer clashes).
    A failure here never stops the hook's real work."""
    try:
        beats = load_json(DATA / "heartbeat.json", {})
        beats = beats if isinstance(beats, dict) else {}
        try:
            age = datetime.datetime.now() - datetime.datetime.fromisoformat(beats.get(event))
            if datetime.timedelta(0) <= age < HEARTBEAT_EVERY:  # a time in the future (clock change): rewrite
                return
        except (TypeError, ValueError):
            pass  # never written, or unreadable: write it now
        beats[event] = now()
        save_json(DATA / "heartbeat.json", beats)
    except Exception:
        pass


def emit(obj):
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def shorten(text, limit):
    text = text or ""
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n[… {len(text) - limit} characters cut …]\n" + text[-half:]


def classify(text):
    """Kinds found in an owner prompt, pasted blocks removed (they're not the owner's words)."""
    text = PASTE_RE.sub(" ", text or "")
    if SLASH_RE.match(text) or text.lstrip().startswith(SYSTEM_TEXT):
        return [], ""
    kinds, first = [], ""
    for kind, rx in KIND_RE:
        m = rx.search(text)
        if m:
            kinds.append(kind)
            first = first or m.group(0)
    return kinds, first


def first_time(state, text):
    """True once per text per session: a message seen by two hooks is counted once."""
    h = hashlib.sha1(PASTE_RE.sub(" ", text or "").strip().encode("utf-8")).hexdigest()[:12]
    seen = state.get("seen", [])
    if h in seen:
        return False
    state["seen"] = (seen + [h])[-100:]
    return True


def project_name(cwd):
    return pathlib.PurePath(cwd or "").name or "unknown"


# ---------- transcript ----------

def read_tail(path, max_bytes):
    """Last lines of a transcript as parsed JSON (the file can be many MB; read only its end)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            raw = f.read()
    except OSError:
        return []
    lines = raw.split(b"\n")
    if size > max_bytes:
        lines = lines[1:]  # first line is cut
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def is_owner_prompt(d):
    if d.get("type") != "user" or d.get("isSidechain") or d.get("isMeta"):
        return False
    content = (d.get("message") or {}).get("content")
    if not isinstance(content, str):
        return False
    origin = d.get("origin") or {}
    if origin.get("kind") not in (None, "human"):
        return False
    return not content.lstrip().startswith(SYSTEM_TEXT + ("Caveat:",))


def tool_label(name, args):
    args = args or {}
    if name in ("Bash", "PowerShell"):
        # Drop leading variable set-up and `cd …&&` so the label shows what actually ran.
        command = LEAD_RE.sub("", str(args.get("command", "")).strip())
        return f"{name}: {command[:140]}"
    if str(name).startswith(BROWSER):
        # What a click did is only in its action_summary (coordinates mean nothing to the checker).
        said = [str(i.get("action_summary")) for i in browser_items(name, args)[1] if i.get("action_summary")]
        if said:
            return f"browser: {'; '.join(said)[:140]}"
    for key in ("file_path", "notebook_path", "path", "url", "pattern"):
        if args.get(key):
            return f"{name}: {str(args[key])[:140]}"
    return name


def exchanges(entries):
    """Split transcript entries into exchanges: owner prompt (+ messages sent while working and
    rejection feedback), tools run, assistant text."""
    out = []
    for d in entries:
        if d.get("isSidechain"):
            continue
        if is_owner_prompt(d):
            out.append({"prompt": d["message"]["content"], "prompt_id": d.get("promptId"),
                        "tools": [], "texts": [], "risky": [], "kb_write": False, "lesson_write": False,
                        "memory_write": False, "doc_write": False})
            continue
        if not out:
            continue
        ex = out[-1]
        if d.get("type") == "attachment" and (d.get("attachment") or {}).get("type") == "queued_command":
            queued = str(d["attachment"].get("prompt", ""))
            if not queued.lstrip().startswith(SYSTEM_TEXT):  # e.g. a background task's notice
                ex["prompt"] += "\n(sent while the assistant was working) " + queued
        elif d.get("type") == "user" and isinstance((d.get("message") or {}).get("content"), list):
            for b in d["message"]["content"]:
                if b.get("type") == "tool_result":
                    txt = b.get("content")
                    txt = txt if isinstance(txt, str) else " ".join(
                        x.get("text", "") for x in (txt or []) if isinstance(x, dict))
                    if REJECTED in txt:
                        ex["prompt"] += "\n(owner rejected a tool call and said) " + txt.split(REJECTED, 1)[1].strip()
        elif d.get("type") == "assistant":
            for b in (d.get("message") or {}).get("content") or []:
                if b.get("type") == "text" and b.get("text", "").strip():
                    ex["texts"].append(b["text"])
                elif b.get("type") == "tool_use":
                    label = tool_label(b.get("name"), b.get("input"))
                    if label not in ex["tools"]:
                        ex["tools"].append(label)
                    reason = risky_reason(b.get("name"), b.get("input"))
                    if reason and reason not in ex["risky"]:
                        ex["risky"].append(reason)
                    ex["kb_write"] = ex["kb_write"] or kb_write(b.get("name"), b.get("input"))
                    ex["lesson_write"] = ex["lesson_write"] or lesson_write(b.get("name"), b.get("input"))
                    ex["memory_write"] = ex["memory_write"] or memory_write(b.get("name"), b.get("input"))
                    ex["doc_write"] = ex["doc_write"] or doc_write(b.get("name"), b.get("input"))
    return out


def recent_exchanges(transcript_path, n):
    """The last n exchanges; the latest one carries `earlier_tools` (tool runs before them)."""
    size = 2_000_000
    while True:
        exs = exchanges(read_tail(transcript_path, size))
        try:
            whole = size >= os.path.getsize(transcript_path)
        except OSError:
            whole = True
        if len(exs) > n or whole or size > 64_000_000:
            break
        size *= 4
    earlier = [t for ex in exs[:-n] for t in ex["tools"]] if len(exs) > n else []
    last = exs[-n:]
    if last:
        last[-1]["earlier_tools"] = list(dict.fromkeys(earlier))[-40:]
    return last


def kb_forms():
    """The knowledge-base path as tools write it: X:/KB and Git Bash's /x/KB."""
    norm = str(KB).replace("\\", "/").lower().rstrip("/")
    m = re.match(r"^([a-z]):(/.*)$", norm)
    return [norm] + ([f"/{m.group(1)}{m.group(2)}"] if m else [])


def lesson_write(name, args):
    """True when a tool call saves lessons outside the playbooks (project memory, the miss log)."""
    args = args or {}
    if name in ("Edit", "Write"):
        return bool(LESSON_FILES.search(str(args.get("file_path") or "").replace("\\", "/")))
    if name in ("Bash", "PowerShell"):
        return any(t.lower().endswith("self-review-log.md") for t in WRITE_TARGET_RE.findall(str(args.get("command", ""))))
    return False


MEMORY_DIR_RE = re.compile(r"/\.claude/projects/[^/\s\"']+/memory(?=[/\s\"']|$)", re.I)
NOT_DOCS = {"self-review-log.md", "core-changes.md"}  # logs, not docs


def md_targets(name, args):
    """(paths of .md files a tool call writes, the Bash command or '')."""
    args = args or {}
    if name in ("Edit", "Write"):
        path = str(args.get("file_path") or "").replace("\\", "/")
        return ([path] if path.lower().endswith(".md") else []), ""
    if name in ("Bash", "PowerShell"):
        command = str(args.get("command", ""))
        return [t.replace("\\", "/") for t in WRITE_TARGET_RE.findall(command)], command.replace("\\", "/")
    return [], ""


def memory_write(name, args):
    """True when a tool call updates the project memory notes (~/.claude/projects/<p>/memory/)."""
    targets, command = md_targets(name, args)
    return any(MEMORY_DIR_RE.search(t) or (command and MEMORY_DIR_RE.search(command) and "/" not in t)
               for t in targets)


def doc_write(name, args):
    """True when a tool call updates a .md doc (project docs or the knowledge base; not memory,
    logs, temporary files or Claude's own settings folder)."""
    targets, command = md_targets(name, args)
    return any(not MEMORY_DIR_RE.search(t) and not (command and MEMORY_DIR_RE.search(command) and "/" not in t)
               and pathlib.PurePath(t).name.lower() not in NOT_DOCS and "/.claude/" not in t.lower()
               and not TEMP_RE.search("/" + t) and "/selfcheck/" not in t.lower() for t in targets)


def kb_write(name, args):
    """True when a tool call writes a playbook (a .md in the knowledge base, not a log)."""
    args = args or {}
    forms = kb_forms()
    if name in ("Edit", "Write", "NotebookEdit"):
        path = str(args.get("file_path") or args.get("notebook_path") or "").replace("\\", "/").lower()
        targets = [path] if any(path.startswith(f + "/") for f in forms) else []
    elif name in ("Bash", "PowerShell"):
        command = str(args.get("command", ""))
        targets = WRITE_TARGET_RE.findall(command) if any(f in command.replace("\\", "/").lower() for f in forms) else []
    else:
        return False
    return any(t.lower().endswith(".md") and "/selfcheck/" not in t.lower()
               and pathlib.PurePath(t.replace("\\", "/")).name.lower() not in NOT_PLAYBOOKS for t in targets)


def browser_items(name, args):
    """(short tool names, inputs) of one browser call; browser_batch holds several."""
    items = [(str(name)[len(BROWSER):], args or {})]
    for a in (args or {}).get("actions") or []:
        if isinstance(a, dict):
            items.append((str(a.get("name", "")).rsplit("__", 1)[-1], a.get("input") or {}))
    return [n for n, _ in items], [i for _, i in items]


def browser_reason(name, args):
    for short, item in zip(*browser_items(name, args)):
        if short == "file_upload":
            return "browser: file upload"
        if short == "javascript_tool" and RISKY_JS.search(str(item.get("text", ""))):
            return "browser: script clicks or sends"
        said = str(item.get("action_summary") or "")
        if RISKY_CLICK.search(said):
            return f"browser: {said[:60]}"
    return ""


ASSIGN_RE = re.compile(r"(?:^|[;&|\s(])(?:export\s+|\$)?([A-Za-z_]\w*)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s;&|]+)")
CD_RE = re.compile(r"(?:^|[;&|\s(])(?:cd|pushd|Set-Location)\s+(?:-\w+\s+)?(\"[^\"]*\"|'[^']*'|[^\s;&|]+)", re.I)
VAR_RE = re.compile(r"\$(?:\{(\w+)\}|(\w+))")


def expand(text, values):
    """Replace $NAME / ${NAME} with what the same command assigned to it (S="…/scratchpad"; rm -rf "$S/x")."""
    for _ in range(5):  # R="$S/x" refers to S
        new = VAR_RE.sub(lambda v: values.get((v.group(1) or v.group(2)).lower(), v.group(0)), text)
        if new == text:
            break
        text = new
    return text


def _is_temp(t):
    return bool(TEMP_RE.search("/" + t)) and ".." not in t


def _relative(t):
    return not re.match(r"[\\/~$%]|[A-Za-z]:", t) and ".." not in t


def temp_context(command, pos):
    """(variables the command assigned before `pos`, whether the last `cd` before `pos` went into a temp folder)."""
    before = command[:pos]
    values = {}
    for a in ASSIGN_RE.finditer(before):
        values[a.group(1).lower()] = expand(a.group(2).strip("\"'"), values)
    cds = [expand(c.group(1).strip("\"'"), values) for c in CD_RE.finditer(before)]
    return values, bool(cds) and _is_temp(cds[-1] + "/")  # the last cd before the action counts


def deletes_only_temp(command, m):
    """True when every target of this one delete (up to the next ; && || | or line) is a temp path.
    A temp path mentioned elsewhere in the command doesn't count; variables assigned earlier in the
    command and a `cd` into a temp folder before the delete do."""
    values, in_temp = temp_context(command, m.start())
    is_temp = _is_temp
    end = SEGMENT_END.search(command, m.end())
    targets, skip = [], False
    for a in ARG_RE.findall(command[m.end():end.start() if end else len(command)]):
        if skip:
            skip = False  # the value of the option before it (-ErrorAction SilentlyContinue)
        elif re.fullmatch(r"\d*>>?|&>", a):
            skip = True  # `2> /dev/null`: the file after it is output, not deleted
        elif re.fullmatch(r"-(?:ErrorAction|ea|WarningAction|InformationAction|ErrorVariable|Filter|Include|Exclude|Depth)",
                          a, re.I):
            skip = True
        elif not (a.startswith("-") or re.fullmatch(r"/\w|\d*>>?\S+|&>\S+|[(){}\[\]]+|\$null", a, re.I)):
            targets.append(expand(a.strip("\"'"), values))  # -Recurse, /s, /q, 2>/dev/null, } aren't targets
    return bool(targets) and all(is_temp(t) or (in_temp and _relative(t)) for t in targets)


# Actions the owner can order in so many words ("commit and push all to main"). Deletes, risky files,
# browser clicks and plans are never skipped: the owner's words rarely say exactly which.
ORDERABLE = re.compile(r"\b(push|commit|rebase|merge|tag|build|publish|release|deploy|submit)\b", re.I)
NEGATED = re.compile(r"\b(?:don'?t|do not|never|not|no|without|stop)\b[^.,;!?\n]{0,25}$", re.I)
# An order starts a sentence or clause ("commit and push", "now build the app", "ok commit …");
# "the build plan", "build failed again" and "push notifications" aren't orders.
ORDER_AT = (r"(?:^|[,;:]|\b(?:and|then|now|please|ok|okay|just|also|so|yes|you can|can you|could you"
            r"|go ahead and)\b)\s*")
NOT_ORDER_AFTER = (r"(?!\w)(?!\s+(?:failed|fails|failing|error|errors|is|was|still|number|plan|log|logs|output"
                   r"|step|steps|notifications?)\b)")
POLITE_ASK = re.compile(r"^\W*(?:please\b|(?:can|could|would|will) you\b)", re.I)


def ordered(prompt, reason):
    """True when the owner's own prompt asks for this risky command: the owner decided it, so it
    isn't gated or checked (owner, 2026-10-25: "with a very clear instruction like commit and push…
    just execute my instructions"). Not inside a question, not after "don't"."""
    verbs = ORDERABLE.findall(reason[len("command: "):]) if reason.startswith("command: ") else []
    if not verbs:
        return False
    text = PASTE_RE.sub(" ", prompt or "")  # pasted text isn't the owner's words
    for sentence in re.split(r"(?<=[.!?\n])", text):
        for m in re.finditer(rf"\b{verbs[-1]}\b", sentence, re.I):
            if NEGATED.search(sentence[:m.start()]):
                return False  # "commit to the private repo, don't commit to public": keep the check
    for sentence in re.split(r"(?<=[.!?\n])", text):
        if sentence.rstrip().endswith("?") and not POLITE_ASK.search(sentence):
            continue  # "did you push?" asks; "can you commit and push?" orders
        if re.search(rf"{ORDER_AT}({verbs[-1]}){NOT_ORDER_AFTER}", sentence, re.I):
            return True  # (a "don't push" anywhere already returned False above)
    return False


def risky_reason(name, args):
    args = args or {}
    if name == "ExitPlanMode":
        return "plan shown for approval"
    if str(name).startswith(BROWSER):
        return browser_reason(name, args)
    if name in ("Bash", "PowerShell"):
        command = without_written_text(str(args.get("command", "")))
        for m in RISKY_COMMAND.finditer(command):
            if not (m.group("delete") and deletes_only_temp(command, m)):
                return f"command: {m.group(0)}"
        return ""  # nothing risky, or it only deletes temporary/scratch files
    path = str(args.get("file_path") or args.get("notebook_path") or "")
    if name in ("Edit", "Write", "NotebookEdit") and RISKY_PATH.search(path):
        file = pathlib.PurePath(path).name
        # Notes about payments are just notes; legal text and CLAUDE.md count even as Markdown.
        if file.lower().endswith((".md", ".txt")) and not RISKY_DOC.search(file):
            return ""
        return f"file: {file}"
    return ""


def render(exs, latest_reply=None, cfg=None):
    limit = (cfg or DEFAULTS)["max_chars_per_message"]
    parts = []
    earlier = exs[-1].get("earlier_tools") if exs else None
    if earlier:
        parts.append("EARLIER TOOL RUNS IN THIS SESSION (before the exchanges below; count them as done): "
                     + "; ".join(earlier))
    for i, ex in enumerate(exs, 1):
        latest = i == len(exs)
        reply = latest_reply if (latest and latest_reply is not None) else "\n\n".join(ex["texts"])
        parts.append(
            f"=== Exchange {i}{' (latest)' if latest else ''} ===\n"
            # Pasted text stays in: it's often the whole request (only counting ignores it).
            f"OWNER: {shorten(PASTE_TAG_RE.sub('[pasted]', ex['prompt']), limit)}\n"
            f"TOOLS RUN: {'; '.join(ex['tools'][-30:]) or 'none'}\n"
            f"ASSISTANT: {shorten(reply, limit)}")
    return "\n\n".join(parts)


# ---------- the independent check ----------

def owner_questions():
    """'Owner had to ask' column of the cases table in self-review-log.md (the owner's examples)."""
    try:
        text = (KB / "self-review-log.md").read_text(encoding="utf-8")
    except OSError:
        return []
    out, in_cases = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            in_cases = line.startswith("## Cases")
            continue
        if in_cases and re.match(r"^\|\s*\d+\s*\|", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[2]:
                out.append(cells[2])
    return out


def checker_prompt_file():
    own = KB / "selfcheck-checker-prompt.md"
    return own if own.exists() else CORE / "templates" / "selfcheck-checker-prompt.md"


def independent_check(cfg, stage, body):
    """One-shot check in a separate session. Returns a dict for the log; ok None = check failed."""
    questions = "\n".join(f"- {q}" for q in owner_questions()) or "- (none logged yet)"
    stage_note = ("STAGE: BEFORE BUILDING. The assistant is about to make the change below. Flag only a "
                  "question that should change the approach before building."
                  if stage == "before-build" else "STAGE: AFTER THE REPLY. Judge only the latest assistant reply.")
    text = ("You are the CHECKER, not the assistant below. Do not answer the owner, do not continue "
            "the conversation. Output only the JSON verdict.\n\n"
            f"{stage_note}\n\nQuestions the owner had to ask in the past:\n{questions}\n\n"
            f"<exchanges_to_check>\n{body}\n</exchanges_to_check>\n\nOutput the JSON verdict now.")
    result = {"model": cfg["model"], "effort": cfg["effort"], "exchanges": cfg["exchanges"],
              "input": text, "output": None, "ok": None, "question": None, "seconds": None,
              "input_tokens": None, "output_tokens": None, "error": None}
    claude = os.environ.get("SELFCHECK_CLAUDE") or shutil.which("claude")
    if not claude:
        result["error"] = "claude command not found"
        return result
    child = DATA / "child"  # empty folder: no project settings or hooks load in the check's session
    child.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, **{CHILD_ENV: "1"})
    lead = [sys.executable, claude] if claude.endswith(".py") else [claude]  # tests use a fake .py
    args = lead + ["-p", "--model", cfg["model"], "--effort", cfg["effort"],
            "--setting-sources", "project,local", "--no-session-persistence", "--tools", "",
            "--strict-mcp-config", "--system-prompt-file", str(checker_prompt_file()),
            "--output-format", "json"]
    start = time.time()
    try:
        run = subprocess.run(args, input=text.encode("utf-8"), capture_output=True, cwd=str(child),
                             env=env, timeout=cfg["check_timeout_seconds"])
        result["seconds"] = round(time.time() - start, 1)
        data = json.loads(run.stdout.decode("utf-8", errors="replace"))
        usage = data.get("usage") or {}
        result["input_tokens"] = sum(usage.get(k) or 0 for k in (
            "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        result["output_tokens"] = usage.get("output_tokens")
        result["output"] = data.get("result")
        if data.get("is_error"):
            result["error"] = f"check session error: {str(data.get('result'))[:200]}"
            return result
        m = re.search(r"\{.*\}", result["output"] or "", re.S)
        verdict = json.loads(m.group(0)) if m else None
        if not isinstance(verdict, dict) or not isinstance(verdict.get("ok"), bool):
            result["error"] = "answer was not the expected JSON"
            return result
        result["ok"] = verdict["ok"]
        result["question"] = str(verdict.get("question") or "").strip() or None
        if result["ok"] is False and not result["question"]:
            result["ok"], result["error"] = None, "flagged without a question"
    except subprocess.TimeoutExpired:
        result["seconds"], result["error"] = round(time.time() - start, 1), "timeout"
    except (OSError, ValueError) as e:
        result["seconds"], result["error"] = round(time.time() - start, 1), f"{type(e).__name__}: {e}"[:200]
    return result


# ---------- free checks on the 🟣 line ----------

def line_problems(reply, cfg, risky):
    """Problems a script can be sure of. Returns (problems, stakes or None)."""
    words = len((reply or "").split())
    m = None
    for m in LINE_RE.finditer(reply or ""):
        pass  # the last 🟣 line counts
    if not m:
        if words >= cfg["presenting_min_words"]:
            return [f"a {words}-word reply has no 🟣 Self-check line"], None
        return [], None
    stakes = m.group("stakes").lower()
    parts = PARTS_RE.search(m.group("rest").strip())
    if not parts:
        return ["the 🟣 line is missing one of its parts (checked · alt · fixed · open)"], stakes
    part = lambda p: parts.group(p).strip(" .:").lower()  # "alt: none" is written too
    # "fixed none" / "open none" are honest answers; only a blank part is missing. "checked none" isn't.
    problems = [f"the 🟣 line's '{p}' part is empty" for p in ("fixed", "open") if not part(p)]
    if part("checked") in EMPTY:
        problems.insert(0, "the 🟣 line names no real checks ('checked' is empty)")
    alt = part("alt")
    # "none needed for a test" or "none — trivial" gives a reason and passes; a bare "none" doesn't.
    bare_none = alt in EMPTY or re.fullmatch(
        r"(?:none|no(?: other)? (?:alternatives?|options?|ways?)|not needed|not applicable)"
        r"(?:\s+(?:needed|compared|considered|found|here))?\W*", alt)
    if stakes == "high" and bare_none:
        problems.append("high stakes but no alternatives were compared ('alt' is empty)")
    if stakes == "low" and risky:
        problems.append(f"labelled low stakes, but this reply did something risky ({risky[0]})")
    return problems, stakes


# ---------- events ----------

def on_prompt(data, cfg):
    kinds, phrase = classify(data.get("prompt", ""))
    sid, pid = data.get("session_id"), data.get("prompt_id")
    state = session_state(sid)
    prompts = state.get("prompts", {})
    prompts[str(pid)] = kinds
    state["prompts"] = dict(list(prompts.items())[-20:])
    last = state.get("last_check")
    if kinds and last and last.get("independent_ok") is True:
        append(CHECKS, {"type": "rating", "id": last["id"], "rating": "possible false pass", "by": "auto",
                        "time": now(), "kinds": kinds})
        state["last_check"] = None
    new = first_time(state, data.get("prompt", ""))
    save_session(sid, state)
    notes = []
    if kinds and new:
        append(QUEUE, {"time": now(), "source": "prompt", "session": sid, "prompt_id": pid,
                       "project": project_name(data.get("cwd")), "kinds": kinds, "matched": phrase,
                       "excerpt": PASTE_RE.sub("[pasted]", data.get("prompt", ""))[:160]})
        if cfg["notes_to_session"] and set(kinds) & NOTE_KINDS:
            always = "miss" in kinds
            notes.append(
                f"[selfcheck hook, not the owner's words] This prompt may show a self-review miss (matched '{phrase}'). "
                + ("The owner said it's a miss: log it" if always else
                   "If the owner had to ask what the self-review purposes should have caught, log it")
                + f" in {KB / 'self-review-log.md'} as core/self-review-benchmark.md says, and run "
                  "core/tools/benchmark_summary.py (in plan mode: as soon as you can). Otherwise ignore this "
                  "note and don't mention it.")
    try:
        due = review_due_today(cfg)
    except Exception:  # never let the reminder break a prompt
        due = None
    if due:
        notes.append(
            f"[selfcheck hook, not the owner's words] The self-review is due ({due} misses logged since the last "
            "review). End your reply with one line suggesting it, e.g. 'Self-review due (" + str(due) + " misses): "
            "say \"run the self-review\" to start it.' Don't start it yourself: the owner starts tasks (session "
            "limits, owner rule 2026-11-22).")
    if notes:
        emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n\n".join(notes)}})


REVIEW_MARK = "review-reminder.json"


def review_due_today(cfg):
    """Misses since the last review when a review is due and nobody was reminded today, else None. The loop
    improves itself only if reviews happen; the owner decides when (2026-11-22)."""
    if not cfg["review_reminder"]:
        return None
    mark = DATA / REVIEW_MARK
    today = datetime.date.today().isoformat()
    if load_json(mark, {}).get("date") == today:
        return None
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # -I leaves this folder out
    import benchmark_summary
    rows = list(benchmark_summary.log_rows((KB / "self-review-log.md").read_text(encoding="utf-8")))
    last = max((i for i, (_, t) in enumerate(rows) if t == "review"), default=-1)
    since = sum(1 for _, t in rows[last + 1:] if t in benchmark_summary.MISS_TYPES)
    if since < benchmark_summary.REVIEW_EVERY:
        return None
    save_json(mark, {"date": today, "since": since})
    return since


def scan_new_entries(data, state):
    """Rejection feedback and messages sent while working: counted like prompts (no hook sees them)."""
    path = data.get("transcript_path")
    try:
        size = os.path.getsize(path)
    except (OSError, TypeError):
        return
    start = state.get("offset")
    state["offset"] = size
    if start is None or start > size:
        return  # first run in this session: start counting from now
    try:
        with open(path, "rb") as f:
            f.seek(start)
            raw = f.read(size - start)
    except OSError:
        return
    for line in raw.split(b"\n"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        texts = []
        if d.get("type") == "attachment" and (d.get("attachment") or {}).get("type") == "queued_command":
            texts.append(("while-working", str(d["attachment"].get("prompt", ""))))  # classify skips notices
        elif d.get("type") == "user" and isinstance((d.get("message") or {}).get("content"), list):
            for b in d["message"]["content"]:
                c = b.get("content") if b.get("type") == "tool_result" else None
                c = c if isinstance(c, str) else " ".join(x.get("text", "") for x in (c or []) if isinstance(x, dict))
                if REJECTED in c:
                    texts.append(("rejection", c.split(REJECTED, 1)[1].strip()))
        for source, text in texts:
            kinds, phrase = classify(text)
            if kinds and first_time(state, text):
                append(QUEUE, {"time": now(), "source": source, "session": data.get("session_id"),
                               "project": project_name(data.get("cwd")), "kinds": kinds, "matched": phrase,
                               "excerpt": PASTE_RE.sub("[pasted]", text)[:160]})


def offer_problem(reply):
    """The reply's ending hands the owner a choice the goal may already answer → the problem text."""
    for m in OFFER_RE.finditer((reply or "")[-900:]):
        line = m.group(0).strip()
        if not OWNER_CALL_RE.search(line):
            return (f"the reply ends by handing the owner a choice (\"{shorten(line, 120)}\"). If the goal "
                    "answers it and it is a small step of the current task, do it now (say so in one line); if it "
                    "is a new task, make it a one-line suggestion (\"Next I suggest X; say go\") and never start it "
                    "(owner rule 2026-11-22: session limits); otherwise drop it. Keep the question only if it is "
                    "truly the owner's call (money, publishing or review, deleting, permissions, commits, what to "
                    "work on next, product scope or taste), and say in one line why")
    return ""


# A question to the owner anywhere in the reply (2026-11-20 repeat: A/B questions with "My recommendation"
# sat above the ending the offer check reads). Not code, quotes, tables or headings; a "?" ending a sentence,
# not inside quotes (the owner's own words being cited).
ASK_LINE_RE = re.compile(r"(?m)^(?![ \t]*(?:[>|#]|```))[^\n]*?[^\s\"'”`]\?(?:\*\*|\)|[ \t]|$)[^\n]*$")
# …addressed to the owner (a rhetorical "why does X happen?" in an explanation isn't): replay 2026-11-22,
# 204 of 905 replies had any "?", the addressed ones are far fewer.
ADDRESSED_RE = re.compile(r"\b(?:you|your|should|shall|can i|may i|do we|which|prefer|ok|okay|want)\b", re.I)


def owner_questions_in(reply):
    """Lines of the reply that ask the owner something which isn't plainly the owner's call."""
    text = re.sub(r"```.*?```", "", reply or "", flags=re.S)
    out = []
    for m in ASK_LINE_RE.finditer(text):
        line = m.group(0)
        if ADDRESSED_RE.search(line) and not OWNER_CALL_RE.search(line) and not LINE_RE.search(line):
            out.append(line.strip())
    return out


def whole_reply(ex, last):
    """The whole reply the owner reads: every text block of the latest exchange (text written
    before tool calls too), plus the hook's last message if the transcript doesn't have it yet."""
    texts = list((ex or {}).get("texts") or [])
    last = last or ""
    if last.strip() and not (texts and texts[-1].strip() == last.strip()):
        texts.append(last)
    return "\n\n".join(texts) or last


UPKEEP = {  # what the owner used to ask for after every task, in this order
    "memory": ("memory_write", "project memory (long-term knowledge: one concise current-state note per topic)"),
    "docs": ("doc_write", "the relevant .md docs (project CLAUDE.md, setup / release / to-do files)"),
    "playbook": ("kb_write", "a playbook in the knowledge base (if the task is repeatable)"),
}


def new_run(seen):
    return {"risky": 0, "counted": [], "nudged_at": None, "examples": [], "seen": seen[-150:],
            "done": {k: False for k in UPKEEP}}


def playbook_reminder(state, exs, cfg):
    """End-of-task upkeep: count replies that did work, and which of memory / docs / playbook were
    updated during that run. When the run looks finished (the owner says so, lessons were just
    saved, or it gets long) and something is missing, return the reminder text. Once per run."""
    work = state.get("work") or {}
    if "done" not in work:  # first run, or a state from before 2026-10-25's upkeep version
        work = new_run([])
    for ex in exs:  # earlier exchange too: updates made in a send-back's follow-up count
        pid = str(ex.get("prompt_id"))
        for kind, (flag, _) in UPKEEP.items():
            if ex.get(flag) and f"{pid}:{kind}" not in work["seen"]:
                work["seen"].append(f"{pid}:{kind}")
                work["done"][kind] = True
    if all(work["done"].values()):
        work = new_run(work["seen"])  # all three kept up to date: a new run starts
    latest = exs[-1] if exs else {}
    pid = str(latest.get("prompt_id"))
    # Lessons saved to memory or the miss log count as work and as a sign that a step is
    # finished: the session is writing down what it learned.
    lessons = bool(latest.get("lesson_write")) and not latest.get("kb_write")
    if (latest.get("risky") or lessons) and pid not in work["counted"]:
        work["risky"] += 1
        work["counted"] = (work["counted"] + [pid])[-50:]
        work["examples"] = (work["examples"] + (latest.get("risky") or ["lessons saved to memory / miss log"])[:1])[-3:]
    state["work"] = work
    n, need = work["risky"], max(1, cfg["playbook_after_risky_replies"])
    prompt = PASTE_RE.sub(" ", latest.get("prompt") or "")
    asked = re.search(r"knowledge ?base|playbook|\bmemory\b|documentation|\.md\b|\bdocs\b", prompt, re.I)
    if not cfg["playbook_reminder"] or n < need or asked:
        return None  # too early, or the owner already asked for it (the session will do it)
    finished = bool(FINISHED_RE.search(prompt))
    last = work["nudged_at"]
    # After a reminder, again only once more work followed: the owner says it's done, lessons are
    # saved again after another `need` replies, or the run has grown long again.
    if last is None:
        due = finished or lessons or n >= 2 * need
    else:
        due = (finished and n > last) or (lessons and n >= last + need) or n >= last + 2 * need
    if not due:
        return None
    missing = [label for kind, (_, label) in UPKEEP.items() if not work["done"][kind]]
    work["nudged_at"] = n
    return (f"the last {n} replies did work (e.g. {'; '.join(work['examples'])}) but did not update: "
            f"{'; '.join(missing)}. If a task, or a reusable part of it, is finished, update what is "
            "relevant now, concisely and without asking (playbooks as ~/.claude/CLAUDE.md, Knowledge "
            "base, says); for anything not needed or not finished yet, say why in one line")


def on_stop(data, cfg):
    sid = data.get("session_id")
    state = session_state(sid)
    scan_new_entries(data, state)
    reply = data.get("last_assistant_message") or ""
    if data.get("stop_hook_active"):
        # The follow-up after a send-back: log it, never check it again (no loops).
        last = state.get("last_check") or {}
        if last.get("sent_back"):
            append(CHECKS, {"type": "follow-up", "id": last.get("id"), "time": now(),
                            "words": len(reply.split()), "reply": shorten(reply, 4000)})
            last["sent_back"] = False
            state["last_check"] = last
        save_session(sid, state)
        return
    if not cfg["stop_checks"]:
        save_session(sid, state)
        return
    exs = recent_exchanges(data.get("transcript_path"), max(1, cfg["exchanges"]))
    latest = exs[-1] if exs else {"risky": [], "prompt": "", "prompt_id": None}
    reminder = playbook_reminder(state, exs, cfg)
    # The hook's last_assistant_message is only the text after the last tool call; checking that
    # alone flagged options the reply had listed earlier (check #47).
    reply = whole_reply(latest, reply)
    risky = [r for r in latest["risky"] if not ordered(latest["prompt"], r)]
    owner_order = bool(latest["risky"]) and not risky  # every risky action was the owner's own order
    problems, stakes = line_problems(reply, cfg, risky)
    words = len(reply.split())
    prompt_kinds = state.get("prompts", {}).get(str(latest.get("prompt_id")), []) or classify(latest["prompt"])[0]
    reasons = (["🟣 says high"] if stakes == "high" else []) + risky[:3] + (
        [f"owner prompt: {k}" for k in prompt_kinds if k in ("check-request", "miss")])
    presenting = (stakes is not None or words >= cfg["presenting_min_words"]) and not owner_order
    offer = offer_problem(reply) if cfg["offer_check"] else ""
    asks = owner_questions_in(reply) if cfg["question_check"] and not owner_order else []
    ask_reason = [f"asks the owner: {shorten(asks[0], 100)}"] if asks else []
    if not presenting and not reminder and not offer and not asks:
        state["last_check"] = None  # a later doubt can't be about an older checked reply
        save_session(sid, state)
        return
    reasons += ask_reason  # the independent check judges whether the goal already answers it
    if not presenting:
        problems, reasons = [], ask_reason  # a short reply: the reminder, the offer and the question check
    if offer:
        problems = problems + [offer]
    check = None
    if cfg["independent_check"] and reasons:  # runs with the free checks: one send-back for both
        check = independent_check(cfg, "after-reply", render(exs, reply, cfg))
    question = check and check["ok"] is False and check["question"]
    if reminder:
        problems = problems + [reminder]
    cid = next_id()
    send = bool(cfg["send_back"] and (problems or question))
    verdict = "sent back" if send else ("flagged (log only)" if (problems or question) else (
        "check failed" if check and check["ok"] is None else "passed"))
    append(CHECKS, {"type": "check", "id": cid, "time": now(), "stage": "after-reply", "session": sid,
                    "project": project_name(data.get("cwd")), "verdict": verdict, "words": words,
                    "stakes": stakes, "high_stakes_reasons": reasons, "free_problems": problems,
                    "playbook_reminder": bool(reminder),
                    "independent": check, "send_back_enabled": cfg["send_back"]})
    state["last_check"] = {"id": cid, "sent_back": send,
                           "independent_ok": check["ok"] if check else None}
    save_session(sid, state)
    if send:
        asks = "; ".join(problems) + ("; " if problems and question else "") + (
            f"the owner would likely ask: \"{question}\"" if question else "")
        emit({"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": (
            f"[selfcheck #{cid}, from a hook, not the owner] Before the owner reads on: {asks}. "
            "Reply with a short follow-up that adds only what's missing (check it for real if needed); "
            "don't repeat your reply. If it's already covered, say so in one line.")},
            "systemMessage": f"🔵 #{cid} sent back: {shorten(asks, 160)}"})
    elif check:
        status = {True: "passed", False: "flagged (log only)", None: "check failed"}[check["ok"]]
        emit({"systemMessage": f"🔵 #{cid} independent check {status} ({check['seconds']} s)"})


PLANS = pathlib.Path(os.environ.get("SELFCHECK_PLANS") or pathlib.Path.home() / ".claude" / "plans")
PLAN_CODE_RE = re.compile(r"\.(?:dart|ts|tsx|js|py|kt|kts|swift|rs|sql|ya?ml|gradle|cs|go|java)\b|\blib/|\bsrc/", re.I)
PLAN_PASS_RE = re.compile(r"problems?\s+(?:found\s+)?in\s+(?:my|the|your)\s+(?:first\s+|previous\s+)?draft"
                          r"|critical\s+(?:second\s+)?pass", re.I)


def plan_text(args):
    """The plan being shown: the tool input, else the newest plan file of the last 6 hours."""
    text = str(args.get("plan") or "")
    if text.strip():
        return text
    try:
        files = sorted(PLANS.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files and time.time() - files[0].stat().st_mtime < 6 * 3600:
            return files[0].read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    return ""


def plan_lacks_critical_pass(args):
    """Case 24 (repeated 2026-11-01, 11-03): a plan that changes code but shows no critical second pass.
    Deterministic, so it doesn't depend on the session remembering. Fails open on any error."""
    try:
        text = plan_text(args)
        return bool(text.strip()) and bool(PLAN_CODE_RE.search(text)) and not PLAN_PASS_RE.search(text)
    except Exception:  # a broken check must never block a plan
        return False


def on_plan_sections(data, cfg, sid):
    """Runs before the once-per-prompt gate, every time a plan is shown (so a fixed plan passes)."""
    args = data.get("tool_input") or {}
    if data.get("tool_name") != "ExitPlanMode" or not plan_lacks_critical_pass(args):
        return False
    cid = next_id()
    block = bool(cfg["send_back"])
    append(CHECKS, {"type": "check", "id": cid, "time": now(), "stage": "plan-sections", "session": sid,
                    "project": project_name(data.get("cwd")), "verdict": "blocked" if block else "flagged (log only)",
                    "tool": "ExitPlanMode", "high_stakes_reasons": ["plan without a critical pass"],
                    "send_back_enabled": cfg["send_back"]})
    if not block:
        return False
    emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
          "permissionDecisionReason": (
              f"[selfcheck #{cid}, plan check, not the owner] This plan changes code but has no "
              "\"Problems found in my draft\" section. Before showing it, do the owner's critical pass against the "
              "code itself: assume there are problems and look for them; regressions and earlier fixes kept; edge "
              "cases (empty/null, limits, concurrency, error paths); duplicated logic and reuse; assumptions and "
              "unsure areas; small screens / no overflow. Fix what it finds, add a \"Problems found in my draft\" "
              "section (what the pass found and changed, or \"none: <what was checked>\"), then show the plan again.")},
          "systemMessage": f"🔵 #{cid} plan sent back: no critical pass in a plan that changes code"})
    return True


# Optional helpers in your own knowledge base: named in the send-back only when they exist there, so the
# rule works without them (others don't have the maintainer's playbooks or phone script).
BROWSER_PLAYBOOK = "browser-automation-text-not-screenshots.md"
PHONE_PLAYBOOK = "android-phone-usb-test-flutter-app.md"
SCREEN_TEXT = "scripts/android_screen_text.py"
SHOTS = DATA / "screenshots"  # one empty file per sent-back call: its identical retry passes
SHOTS_LOG = DATA / "screenshots.jsonl"  # own log: these never count as "blocked" in the report

# A phone screenshot or screen recording started from the command line (one command part, so a
# `grep screencap` or a word in a message never matches): Android adb, iOS simulator / device, Flutter.
PHONE_SHOT_RE = re.compile(
    r"\badb(?:\.exe)?\b[^;|&\n]*?\b(?:exec-out|shell)\b[^;|&\n]*?\b(?:screencap|screenrecord)\b"
    r"|\bsimctl\b[^;|&\n]*?\bio\b[^;|&\n]*?\b(?:screenshot|recordVideo)\b"
    r"|(?:^|[\s;&|(\"'])idevicescreenshot\b"
    r"|\bflutter(?:\.bat)?\s+screenshot\b", re.I)


def mcp_items(name, args):
    """(short tool name, input) of one MCP call; a browser_batch holds several."""
    items = [(str(name).rsplit("__", 1)[-1], args or {})]
    for a in (args or {}).get("actions") or []:
        if isinstance(a, dict):
            items.append((str(a.get("name", "")).rsplit("__", 1)[-1], a.get("input") or {}))
    return items


def screenshot_kind(name, args):
    """'phone' for a command-line phone capture, 'screen' for an MCP screenshot (browser, desktop),
    None otherwise. Clicks, typing and text lookups are never screenshots."""
    name = str(name or "")
    if name in ("Bash", "PowerShell"):
        return "phone" if PHONE_SHOT_RE.search(str((args or {}).get("command", ""))) else None
    if not name.startswith("mcp__"):
        return None
    for short, item in mcp_items(name, args):
        short = short.lower()
        if "screenshot" in short:
            return "screen"
        if short == "computer" and str(item.get("action", "")) in ("screenshot", "zoom"):
            return "screen"
    return None


def call_what(name, args):
    """"The same call" = what it does: the command, or the inputs without the labels written for the owner
    (a retry naturally gets a new description, which made phone retries never pass: live test 2026-11-17)."""
    args = args or {}
    if name in ("Bash", "PowerShell"):
        return args.get("command")
    return {k: v for k, v in args.items() if k not in ("description", "action_summary")}


def first_attempt(sid, name, what, prefix=""):
    """True the first time this exact call is made (send it back); its identical retry passes once, then
    the next identical call is sent back again. A fault here makes the hook err, so the call goes through."""
    key = prefix + hashlib.sha256(json.dumps([safe(sid), name, what], sort_keys=True, ensure_ascii=False)
                                  .encode("utf-8")).hexdigest()[:32]
    mark = SHOTS / key
    if mark.exists():
        mark.unlink(missing_ok=True)
        return False
    SHOTS.mkdir(parents=True, exist_ok=True)
    mark.write_bytes(b"")  # written before the reply
    try:
        cutoff = time.time() - 86_400
        for old in SHOTS.iterdir():  # marks never retried
            if old.stat().st_mtime < cutoff:
                old.unlink(missing_ok=True)
    except OSError:
        pass  # housekeeping only
    return True


def on_screenshot(data, sid):
    """Owner rule (browser 2026-11-05, phone 2026-11-04; every call 2026-11-17 after a miss): look by text,
    screenshot last. Every screenshot is sent back once with the rule; the identical call retried passes,
    so a real need still works. Any fault lets the call through (never blocks the owner's session)."""
    name, args = data.get("tool_name"), data.get("tool_input") or {}
    kind = screenshot_kind(name, args)
    if not kind:
        return False
    if not first_attempt(sid, name, call_what(name, args)):
        return False
    try:
        append(SHOTS_LOG, {"time": now(), "session": sid, "project": project_name(data.get("cwd")),
                           "kind": kind, "tool": str(name), "agent": bool(data.get("agent_id"))})
    except OSError:
        pass  # housekeeping only
    playbook = lambda f: f" (playbook {f})" if (KB / f).exists() else ""
    if kind == "phone":
        script = KB / SCREEN_TEXT
        read = (f"python {script.as_posix()} (labels + tap points; --find \"X\", --tap \"X\"); a control missing from "
                "it: " if script.exists() else "")
        how = (f"Owner rule: look at the phone by text, not screenshots{playbook(PHONE_PLAYBOOK)}: {read}"
               "read the uiautomator dump (`adb shell uiautomator dump /sdcard/u.xml`, then `adb exec-out cat "
               "/sdcard/u.xml`: every node with its text and bounds). Screenshot only for looks (layout, "
               "colours), maps, photos, or an empty dump (locked/crashed screen); if so, retry this exact command "
               "(it will pass) and shrink the image before reading it.")
    else:
        how = (f"Owner rule: drive pages by text, not screenshots{playbook(BROWSER_PLAYBOOK)}: find \"<what>\" "
               "(refs), read_page(ref_id, filter=interactive) or get_page_text, click/type by ref, check saves by "
               "re-reading text. Screenshot only when text can't answer (icon-only buttons, canvas, layout, an "
               "option list missing from the text); if so, retry this exact call (it will pass) at scale 0.35-0.45.")
    emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
          "permissionDecisionReason": f"[selfcheck, screenshot rule, not the owner] {how}"},
          "systemMessage": "🔵 screenshot sent back once: text first"})
    return True


# The owner's history files: rows are added or edited, never written over (2026-11-12: a session copied the
# template over the real miss log; 25 cases and 57 rows were missing for 10 days).
HISTORY_LOGS = r"(?:self-review-log|core-changes)\.md"
_T = r"[\"']?[^\s\"'|;&>]*" + HISTORY_LOGS + r"\b"
LOG_OVERWRITE_RE = re.compile("|".join([
    r"(?<![>0-9&])>(?!>)\s*" + _T,                                                      # shell `>` (not `>>`)
    r"\b(?:Set-Content|Out-File)\b(?![^;&|\n]*-Append)[^;&|\n]*" + HISTORY_LOGS,       # PowerShell, not appending
    r"\b(?:cp|copy|Copy-Item|mv|move|Move-Item)\b[^;&|\n]*\s" + _T + r"[\"']?\s*(?:$|[;&|\n])",  # copied onto it
    HISTORY_LOGS + r"[\"']?\s*,\s*[\"']w[\"']",                                         # open('…log.md', 'w')
    HISTORY_LOGS + r"[\"']?\s*\)\s*\.write_text\(",                                     # Path(…).write_text(
    r"writeFileSync\([^)\n]*" + HISTORY_LOGS,                                           # node
]), re.I | re.M)


def history_overwrite(name, args):
    """The history file a call would write over, or ''."""
    args = args or {}
    if name == "Write":
        path = pathlib.Path(str(args.get("file_path") or ""))
        return path.name if re.fullmatch(HISTORY_LOGS, path.name, re.I) and path.exists() else ""
    if name in ("Bash", "PowerShell"):
        command = str(args.get("command", ""))
        for m in LOG_OVERWRITE_RE.finditer(command):
            # A copy in a temp folder (a test of the template, 2026-11-22 false alarm) isn't the history.
            t = re.search(r"[^\s\"'|;&>(),=]*" + HISTORY_LOGS, m.group(0), re.I)
            values, in_temp = temp_context(command, m.start())
            path = expand(t.group(0), values) if t else ""
            if not (_is_temp(path) or (in_temp and _relative(path))):
                return re.search(HISTORY_LOGS, m.group(0), re.I).group(0)
    return ""


def on_history_overwrite(data, sid):
    name, args = data.get("tool_name"), data.get("tool_input") or {}
    file = history_overwrite(name, args)
    if not file or not first_attempt(sid, name, call_what(name, args), "log-"):
        return False
    emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
          "permissionDecisionReason": (
              f"[selfcheck, history guard, not the owner] This writes over {file}, the owner's miss/change history "
              "(on 2026-11-12 a session wrote the template over the real log). Add rows with Edit or `>>` instead. "
              "Only if a full rewrite is really needed (a restore): keep every existing row, then retry this exact "
              "call (it will pass).")},
          "systemMessage": f"🔵 sent back once: would write over {file}"})
    return True


# A playbook can name the tool calls that start its sub-task: `triggers: <regex>` in its first lines, matched
# (case-insensitive, multi-line) against a Bash/PowerShell command, or against "<tool name>\n<input as JSON>".
# Text rules ("look up a playbook for each new kind of sub-task") kept being missed mid-task (2026-11-01..03
# undo checks, 11-05 and 11-17 Chrome, 11-17 downloaded keys, 11-18 `flutter run`); a check at the call works.
TRIGGER_LINE = re.compile(r"(?im)^triggers:\s*(.+?)\s*$")
TRIGGER_INDEX = "triggers.json"


def playbook_triggers():
    """[(file, title, compiled regex)] from the knowledge base's playbooks, cached until one changes."""
    files = sorted(KB.glob("*.md"))
    stamp = [len(files), max((f.stat().st_mtime for f in files), default=0)]
    cache = DATA / TRIGGER_INDEX
    index = load_json(cache, {})
    if not isinstance(index, dict) or index.get("stamp") != stamp:
        items = []
        for f in files:
            try:
                with f.open(encoding="utf-8", errors="replace") as fh:
                    head = "".join(fh.readline() for _ in range(8))
            except OSError:
                continue
            m = TRIGGER_LINE.search(head)
            if m:
                title = next((l[2:].strip() for l in head.splitlines() if l.startswith("# ")), f.stem)
                items.append([f.name, title, m.group(1)])
        index = {"stamp": stamp, "items": items}
        save_json(cache, index)
    out = []
    for name, title, pattern in index.get("items", []):
        try:
            out.append((name, title, re.compile(pattern, re.I | re.M)))
        except re.error:
            continue  # a broken trigger line never blocks anything
    return out


def call_text(name, args):
    """What a trigger is matched against: the command run (text written into a file removed), or an MCP call
    as "<name>\n<input JSON>". Edits and writes only *mention* a step (a plan saying `flutter run`): ''."""
    args = args or {}
    if name in ("Bash", "PowerShell"):
        return without_written_text(str(args.get("command", "")))
    if str(name).startswith("mcp__"):
        return f"{name}\n{json.dumps(args, ensure_ascii=False, sort_keys=True)}"
    return ""


def transcript_mentions(path, text):
    """True when the session itself already used or named the file (a tool call or its own reply). The
    transcript also holds the global CLAUDE.md text, which names playbooks: that doesn't count."""
    needle = text.encode("utf-8")
    try:
        with open(path, "rb") as f:
            for line in f:
                if needle in line:
                    try:
                        if json.loads(line).get("type") == "assistant":
                            return True
                    except ValueError:
                        continue
    except (OSError, TypeError):
        return False
    return False


def on_playbook_trigger(data, cfg, sid):
    """Send the first call of a sub-task back once per session and playbook, unless the playbook was already
    read or named in this session. The retry passes (the playbook is then marked as seen)."""
    if not cfg["playbook_triggers"]:
        return False
    name, args = data.get("tool_name"), data.get("tool_input") or {}
    text = call_text(name, args)
    if not text:
        return False
    hits = [(f, t) for f, t, rx in playbook_triggers() if rx.search(text)]
    if not hits:
        return False
    state = session_state(sid)
    seen = state.get("playbooks_seen", [])
    new = [(f, t) for f, t in hits if f not in seen and not transcript_mentions(data.get("transcript_path"), f)]
    state["playbooks_seen"] = (seen + [f for f, _ in hits if f not in seen])[-100:]
    save_session(sid, state)
    if not new:
        return False
    names = "; ".join(f"{KB / f} (\"{t}\")" for f, t in new)
    append(CHECKS, {"type": "check", "id": next_id(), "time": now(), "stage": "playbook-trigger", "session": sid,
                    "project": project_name(data.get("cwd")), "verdict": "sent back", "tool": tool_label(name, args),
                    "high_stakes_reasons": [f for f, _ in new], "send_back_enabled": True})
    emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
          "permissionDecisionReason": (
              f"[selfcheck, playbook trigger, not the owner] This step has a playbook: {names}. Read it down to its "
              "first `---` and follow it (owner rule: look up the playbook for each new kind of sub-task), then "
              "retry this call (it will pass).")},
          "systemMessage": f"🔵 sent back once: read {', '.join(f for f, _ in new)} first"})
    return True


def on_pre_tool(data, cfg):
    if not cfg["gate"]:
        return
    sid, pid = data.get("session_id"), data.get("prompt_id")
    if on_screenshot(data, sid):  # helper agents too: their screenshots cost the same tokens
        return
    if on_history_overwrite(data, sid):
        return
    try:
        if on_playbook_trigger(data, cfg, sid):  # helper agents too: they run `flutter run` as well
            return
    except Exception:  # a broken trigger check must never block a call
        pass
    if data.get("agent_id"):
        return  # helper agents' other tool calls aren't gated
    if on_plan_sections(data, cfg, sid):
        return
    state = session_state(sid)
    if pid and str(pid) in state.get("gated", []):
        return
    name, args = data.get("tool_name"), data.get("tool_input") or {}
    reason = risky_reason(name, args)
    prompt_kinds = state.get("prompts", {}).get(str(pid), []) if pid else []
    if not reason and "check-request" in prompt_kinds and name in ("Edit", "Write", "NotebookEdit"):
        reason = "owner asked for a careful change"
    if not reason:
        return
    exs = recent_exchanges(data.get("transcript_path"), max(1, cfg["exchanges"]))
    if exs and ordered(exs[-1]["prompt"], reason):
        return  # the owner ordered exactly this; a later risky step of the same reply is still gated
    # Once per reply: keyed by the prompt id, or the latest owner prompt's id from the transcript.
    key = str(pid or (exs[-1].get("prompt_id") if exs else None) or "")
    if key and key in state.get("gated", []):
        return
    state["gated"] = (state.get("gated", []) + [key])[-50:]
    save_session(sid, state)
    current_text = "\n".join(exs[-1]["texts"]) if exs else ""
    listed = bool(DECISIONS_RE.search(current_text)) and name != "ExitPlanMode"
    check = None
    if not listed and cfg["independent_check"]:
        about = tool_label(name, args)
        if name == "ExitPlanMode":
            about += "\nPLAN:\n" + shorten(str(args.get("plan", "")), 8000)
        body = render(exs, None, cfg) + f"\n\nABOUT TO RUN: {about}"
        check = independent_check(cfg, "before-build", body)
    question = check and check["ok"] is False and check["question"]
    cid = next_id()
    block = bool(cfg["send_back"] and question)
    verdict = ("passed (decisions listed)" if listed else "blocked" if block else
               "flagged (log only)" if question else "check failed" if check and check["ok"] is None else
               "passed" if check else "not checked (independent check off)")
    append(CHECKS, {"type": "check", "id": cid, "time": now(), "stage": "before-build", "session": sid,
                    "project": project_name(data.get("cwd")), "verdict": verdict, "tool": tool_label(name, args),
                    "high_stakes_reasons": [reason], "decisions_listed": listed, "independent": check,
                    "send_back_enabled": cfg["send_back"]})
    if block:
        emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
              "permissionDecisionReason": (
                  f"[selfcheck #{cid}, independent check before building, not the owner] Before this change "
                  f"({reason}), answer the owner's likely question: \"{question}\". Then write the material "
                  "decisions as one line `Decisions: goal … · ways … · alt: …` (ways to reach the goal, "
                  "not only ways to build the first idea) and continue.")},
              "systemMessage": f"🔵 #{cid} check before building: {shorten(question, 160)}"})
    elif check:
        status = "passed" if check["ok"] else ("flagged (log only)" if question else "check failed")
        emit({"systemMessage": f"🔵 #{cid} check before building {status} ({check['seconds']} s)"})


# ---------- report (used by benchmark_summary.py) ----------

def read_jsonl(path):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def summary(days=14):
    """Numbers for the trend report. Empty dict when the hooks never ran."""
    entries, queue = read_jsonl(CHECKS), read_jsonl(QUEUE)
    beats = load_json(DATA / "heartbeat.json", {})
    if not (entries or queue or beats):
        return {}
    since = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
    checks = [c for c in entries if c.get("type") == "check" and c.get("time", "") >= since]
    ratings = {}
    for r in entries:
        if r.get("type") == "rating":
            ratings[r.get("id")] = r.get("rating")  # the latest rating of a check counts
    by_setting = {}
    for c in [c for c in entries if c.get("type") == "check" and c.get("independent")]:
        i = c["independent"]
        key = f"{i.get('model')} · {i.get('effort')} · {i.get('exchanges')} exchanges"
        s = by_setting.setdefault(key, {"runs": 0, "flagged": 0, "failed": 0, "seconds": 0.0, "tokens": 0,
                                        "right": 0, "wrong": 0, "possible false pass": 0})
        s["runs"] += 1
        s["flagged"] += i.get("ok") is False
        s["failed"] += i.get("ok") is None
        s["seconds"] += i.get("seconds") or 0
        s["tokens"] += i.get("input_tokens") or 0
        if ratings.get(c.get("id")) in ("right", "wrong", "possible false pass"):
            s[ratings[c["id"]]] += 1
    weekly = {}
    for q in queue:
        try:
            d = datetime.date.fromisoformat(q["time"][:10])
        except (KeyError, ValueError):
            continue
        week = (d - datetime.timedelta(days=d.weekday())).isoformat()
        row = weekly.setdefault(week, {"miss": 0, "doubt": 0, "correction": 0, "check-request": 0})
        kind = (q.get("kinds") or [None])[0]
        if kind in row:
            row[kind] += 1
    stale = []
    for event in ("UserPromptSubmit", "Stop", "PreToolUse"):
        last = beats.get(event)
        if not last or last < (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat():
            stale.append(event)
    count = lambda v: sum(1 for c in checks if c.get("verdict") == v)
    follow_ups = {f.get("id"): f for f in entries if f.get("type") == "follow-up"}
    recent = []
    for c in [c for c in entries if c.get("type") == "check"][-50:][::-1]:
        i = c.get("independent") or {}
        recent.append({"id": c.get("id"), "time": c.get("time"), "stage": c.get("stage"),
                       "verdict": c.get("verdict"), "project": c.get("project"),
                       "why": c.get("high_stakes_reasons") or [], "free": c.get("free_problems") or [],
                       "tool": c.get("tool"), "model": i.get("model"), "effort": i.get("effort"),
                       "exchanges": i.get("exchanges"), "seconds": i.get("seconds"),
                       "tokens": i.get("input_tokens"), "question": i.get("question"),
                       "error": i.get("error"), "input": i.get("input"), "answer": i.get("output"),
                       "rating": ratings.get(c.get("id")),
                       "follow_up": (follow_ups.get(c.get("id")) or {}).get("reply")})
    return {"days": days, "checks": len(checks), "sent_back": count("sent back"), "blocked": count("blocked"),
            "recent": recent,
            "failed": count("check failed"), "by_setting": by_setting, "weekly": dict(sorted(weekly.items())),
            "heartbeat": beats, "stale": stale, "errors": len(read_jsonl(DATA / "errors.jsonl")),
            "off": (KB / "selfcheck-off").exists()}


# ---------- manual commands ----------

def rate(args):
    if len(args) < 2 or not re.fullmatch(r"#?[0-9]+", args[0]) or args[1].lower() not in ("right", "wrong"):
        print("usage: selfcheck.py rate <id> right|wrong [note]")
        return 2
    cid = int(args[0].lstrip("#"))
    if not any(e.get("type") == "check" and e.get("id") == cid for e in read_jsonl(CHECKS)):
        print(f"No check #{cid} in {CHECKS}: nothing recorded.")
        return 1
    append(CHECKS, {"type": "rating", "id": cid, "rating": args[1].lower(), "by": "owner",
                    "time": now(), "note": " ".join(args[2:])})
    print(f"Recorded: #{cid} {args[1].lower()}")
    return 0


def backfill_history():
    marker = DATA / "history-backfilled.txt"
    if marker.exists():
        print("Already done on", marker.read_text().strip())
        return 0
    path = pathlib.Path.home() / ".claude" / "history.jsonl"
    n = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        print("No prompt history at", path)
        return 1
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        text = d.get("display", "")
        if text.startswith("[Pasted"):
            continue
        kinds, phrase = classify(text)
        if kinds:
            ts = datetime.datetime.fromtimestamp(d.get("timestamp", 0) / 1000).isoformat(timespec="seconds")
            append(QUEUE, {"time": ts, "source": "history", "session": d.get("sessionId"),
                           "project": project_name(d.get("project")), "kinds": kinds, "matched": phrase,
                           "excerpt": text[:160]})
            n += 1
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(now())
    print(f"Counted {n} past prompts from {len(lines)} history lines.")
    return 0


def main(argv):
    if argv:
        if argv[0] == "rate":
            return rate(argv[1:])
        if argv[0] == "backfill-history":
            return backfill_history()
        print(__doc__)
        return 2
    if os.environ.get(CHILD_ENV) or (KB / "selfcheck-off").exists():
        return 0
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace") or "{}")
    event, cfg = data.get("hook_event_name"), config()
    heartbeat(event or "unknown")
    if event == "UserPromptSubmit":
        on_prompt(data, cfg)
    elif event == "Stop":
        on_stop(data, cfg)
    elif event == "PreToolUse":
        on_pre_tool(data, cfg)
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(main(sys.argv[1:]))
    try:
        main([])
    except Exception as e:  # never break the owner's session; leave a trace for the report
        try:
            append(DATA / "errors.jsonl", {"time": now(), "error": f"{type(e).__name__}: {e}"[:300]})
        except Exception:
            pass
    sys.exit(0)
