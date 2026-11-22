"""Tests for selfcheck.py, the trend report and the personal-data guard.
Run from the knowledge-base folder: python -I core/tools/test_selfcheck.py

Every test uses a temporary knowledge-base folder (or git repo) and a fake `claude` (no real model
calls, no real log touched). Hooks are run the way Claude Code runs them: JSON on stdin, JSON on stdout.
"""

import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

TOOLS = pathlib.Path(__file__).resolve().parent
SCRIPT = TOOLS / "selfcheck.py"
sys.path.insert(0, str(TOOLS))
import selfcheck  # noqa: E402

GOOD_LINE = ("🟣 Self-check (high, 2 pass, 7/8 purposes): checked the logs and a real run · "
             "alt A vs B · fixed none · open the live test")
LONG = " ".join(["word"] * 200)

# The owner's own logged questions (cases table): each must be recognised.
LOGGED = [
    "Are you sure? Can you see the logs?",
    "Any better way with even less tokens?",
    "Will a future session know this?",
    "Is there a better way than +25 words?",
    "How does it monitor if it keeps improving?",
    "Before you started, did you ask if there's a better way?",
    "Did you ask yourself if there are better ways this time?",
    "please double check what you have done as this is a big change, make sure you didn't miss anything",
    "that's a miss",
    "the onboarding screen is still wrong",
    # Missed on 2026-10-25 (the owner had to say it twice; nothing was counted):
    "keep it ticked. check everything dont stop and ask me everytime.",
    "the build is uploaded now dont tell me about the review check again",
]
NORMAL = [
    "what is the 1 shell still running?",
    "how about add a new column in app_config called min_supported_ver",
    "are you stuck?",
    "start",
    "can you create a new readme file and upload it",
    "how do i check in github if it's still running?",
    "yes, go with option B",
]

FAKE = r'''
import json, os, pathlib, sys
sys.stdin.read()
log = pathlib.Path(os.environ["FAKE_LOG"])
with log.open("a", encoding="utf-8") as f:
    f.write(json.dumps({"args": sys.argv[1:], "cwd": os.getcwd(), "child": os.environ.get("SELFCHECK_CHILD")}) + "\n")
answer = pathlib.Path(os.environ["FAKE_ANSWER"]).read_text(encoding="utf-8")
print(json.dumps({"result": answer, "is_error": False,
                  "usage": {"input_tokens": 5, "cache_read_input_tokens": 3000, "output_tokens": 50}}))
'''


def prompt_entry(text, pid="p1"):
    return {"type": "user", "origin": {"kind": "human"}, "promptSource": "typed", "promptId": pid,
            "message": {"role": "user", "content": text}}


def assistant(text=None, tool=None, args=None):
    blocks = []
    if text:
        blocks.append({"type": "text", "text": text})
    if tool:
        blocks.append({"type": "tool_use", "name": tool, "input": args or {}})
    return {"type": "assistant", "message": {"content": blocks}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kb = pathlib.Path(self.tmp.name)
        (self.kb / "self-review-log.md").write_text(
            "## Cases\n\n| # | Situation | Owner had to ask | Purpose |\n|---|---|---|---|\n"
            "| 1 | x | Are you sure? | 1 |\n", encoding="utf-8")
        self.fake = self.kb / "fake_claude.py"
        self.fake.write_text(FAKE, encoding="utf-8")
        self.answer = self.kb / "answer.txt"
        self.answer.write_text('{"ok": true}', encoding="utf-8")
        self.fake_log = self.kb / "fake_log.jsonl"
        self.transcript = self.kb / "t.jsonl"
        self.write_transcript([prompt_entry("please fix the bug")])

    def tearDown(self):
        self.tmp.cleanup()

    def write_transcript(self, entries, mode="w"):
        with self.transcript.open(mode, encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    def hook(self, data, extra_env=None):
        env = dict(os.environ, SELFCHECK_KB=str(self.kb), SELFCHECK_PLANS=str(self.kb / "plans"),
                   SELFCHECK_CLAUDE=str(self.fake),
                   FAKE_ANSWER=str(self.answer), FAKE_LOG=str(self.fake_log))
        env.pop("SELFCHECK_CHILD", None)
        env.update(extra_env or {})
        data = dict({"session_id": "s1", "transcript_path": str(self.transcript), "cwd": str(self.kb)}, **data)
        run = subprocess.run([sys.executable, "-I", "-S", str(SCRIPT)], input=json.dumps(data).encode("utf-8"),
                             capture_output=True, env=env, timeout=60)
        self.assertEqual(run.returncode, 0)
        out = run.stdout.decode("utf-8").strip()
        return json.loads(out) if out else None

    def checks(self):
        path = self.kb / "selfcheck" / "checks.jsonl"
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def queue(self):
        path = self.kb / "selfcheck" / "queue.jsonl"
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def stop(self, reply, **kw):
        return self.hook(dict({"hook_event_name": "Stop", "last_assistant_message": reply,
                               "stop_hook_active": False}, **kw))


class Classify(unittest.TestCase):
    def test_logged_questions_found(self):
        for q in LOGGED:
            self.assertTrue(selfcheck.classify(q)[0], q)

    def test_normal_prompts_not_flagged(self):
        for q in NORMAL:
            self.assertEqual(selfcheck.classify(q)[0], [], q)

    def test_pasted_text_and_commands_ignored(self):
        pasted = 'lets start\n<pasted_content id="9">\nBetter ways I found, are you sure\n</pasted_content id="9">\n'
        self.assertEqual(selfcheck.classify(pasted)[0], [])
        self.assertEqual(selfcheck.classify("/review are you sure")[0], [])

    def test_pasted_request_reaches_the_independent_check(self):
        ex = [{"prompt": 'do this:\n<pasted_content id="1">\nImplement roadmap #1\n</pasted_content id="1">',
               "tools": [], "texts": ["ok"], "risky": []}]
        self.assertIn("Implement roadmap #1", selfcheck.render(ex))

    def test_kinds(self):
        self.assertEqual(selfcheck.classify("that's a miss")[0][0], "miss")
        self.assertIn("check-request", selfcheck.classify("please double check it")[0])


class LineChecks(unittest.TestCase):
    cfg = selfcheck.DEFAULTS

    def test_good_line_passes(self):
        self.assertEqual(selfcheck.line_problems(LONG + "\n" + GOOD_LINE, self.cfg, []), ([], "high"))

    def test_long_reply_without_line(self):
        problems, _ = selfcheck.line_problems(LONG, self.cfg, [])
        self.assertTrue(problems)

    def test_short_reply_needs_no_line(self):
        self.assertEqual(selfcheck.line_problems("Done, pushed.", self.cfg, []), ([], None))

    def test_high_without_alternatives(self):
        line = GOOD_LINE.replace("alt A vs B", "alt none")
        self.assertIn("alternatives", " ".join(selfcheck.line_problems(line, self.cfg, [])[0]))

    def test_none_with_a_reason_passes(self):
        line = GOOD_LINE.replace("alt A vs B", "alt none needed for a test")
        self.assertEqual(selfcheck.line_problems(line, self.cfg, [])[0], [])

    def test_none_with_a_short_reason_passes(self):
        # Review 2026-10-25: "alt none — trivial" gives a reason but was flagged (it counted words).
        for alt in ("alt none — trivial", "alt none: config only"):
            self.assertEqual(selfcheck.line_problems(GOOD_LINE.replace("alt A vs B", alt), self.cfg, [])[0], [], alt)
        self.assertTrue(selfcheck.line_problems(GOOD_LINE.replace("alt A vs B", "alt none needed"), self.cfg, [])[0])
        self.assertEqual(selfcheck.line_problems(GOOD_LINE.replace("alt A vs B", "alt none (one way exists)"),
                                                 self.cfg, [])[0], [])

    def test_bare_forms_are_flagged_with_or_without_a_colon(self):
        for alt in ("alt: none", "alt not needed", "alt no other options", "alt: no alternatives considered"):
            problems = selfcheck.line_problems(GOOD_LINE.replace("alt A vs B", alt), self.cfg, [])[0]
            self.assertIn("alternatives", " ".join(problems), alt)
        line = GOOD_LINE.replace("checked the logs and a real run", "checked: none")
        self.assertIn("checked", " ".join(selfcheck.line_problems(line, self.cfg, [])[0]))

    def test_missing_part(self):
        line = GOOD_LINE.replace(" · open the live test", "")
        self.assertTrue(selfcheck.line_problems(line, self.cfg, [])[0])

    def test_empty_checked(self):
        line = GOOD_LINE.replace("checked the logs and a real run", "checked none")
        self.assertIn("checked", " ".join(selfcheck.line_problems(line, self.cfg, [])[0]))

    def test_low_label_on_risky_work(self):
        line = GOOD_LINE.replace("(high,", "(low,")
        self.assertTrue(selfcheck.line_problems(line, self.cfg, ["command: git push"])[0])


class StopHook(Base):
    def test_missing_line_is_sent_back_once(self):
        out = self.stop(LONG)
        self.assertIn("no 🟣 Self-check line", out["hookSpecificOutput"]["additionalContext"])
        self.assertTrue(out["systemMessage"].startswith("🔵 #1 sent back"))
        # The follow-up after a send-back is never checked again (no loop).
        self.assertIsNone(self.stop(LONG, stop_hook_active=True))
        self.assertEqual([c["type"] for c in self.checks()], ["check", "follow-up"])

    def test_short_reply_does_nothing(self):
        self.assertIsNone(self.stop("Done."))
        self.assertEqual(self.checks(), [])

    def test_good_low_stakes_reply_passes_without_check(self):
        line = GOOD_LINE.replace("(high,", "(low,")
        self.assertIsNone(self.stop(LONG + "\n" + line))
        self.assertFalse(self.fake_log.exists())
        self.assertEqual(self.checks()[0]["verdict"], "passed")

    def test_high_stakes_independent_pass(self):
        out = self.stop(LONG + "\n" + GOOD_LINE)
        self.assertNotIn("hookSpecificOutput", out)
        self.assertIn("passed", out["systemMessage"])
        call = json.loads(self.fake_log.read_text(encoding="utf-8").splitlines()[0])
        self.assertIn("claude-haiku-5-5", call["args"])
        self.assertEqual(call["child"], "1")
        self.assertEqual(pathlib.Path(call["cwd"]).name, "child")
        self.assertIn("--strict-mcp-config", call["args"])

    def test_high_stakes_independent_flag(self):
        self.answer.write_text('{"ok": false, "question": "Did you test it on a real phone?"}', encoding="utf-8")
        out = self.stop(LONG + "\n" + GOOD_LINE)
        self.assertIn("Did you test it on a real phone?", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.checks()[0]["verdict"], "sent back")

    def test_broken_answer_passes_and_is_logged(self):
        self.answer.write_text("I think it's fine", encoding="utf-8")
        out = self.stop(LONG + "\n" + GOOD_LINE)
        self.assertNotIn("hookSpecificOutput", out)
        self.assertEqual(self.checks()[0]["verdict"], "check failed")

    def test_log_only_mode(self):
        (self.kb / "selfcheck-config.json").write_text('{"send_back": false}', encoding="utf-8")
        self.assertIsNone(self.stop(LONG))
        self.assertEqual(self.checks()[0]["verdict"], "flagged (log only)")

    def test_offer_the_goal_answers_is_sent_back(self):
        # 25 Oct: "If you want, I can also copy the table into SETUP_NOTES.md" → owner:
        # "please don't ask me these questions anymore ... if it benefits the goal, don't ask me".
        offer = "If you want, I can also copy the table into the project's SETUP_NOTES.md."
        out = self.stop("Playbook updated. " + offer)
        self.assertIn("handing the owner a choice", out["hookSpecificOutput"]["additionalContext"])
        for owners in ["Do you want me to commit and push now?", "Shall I send it for Google review?",
                       "Should I delete the old service account?", "Playbook updated."]:
            self.assertEqual(selfcheck.offer_problem(owners), "", owners)
        self.assertTrue(selfcheck.offer_problem("Do you want me to add those two things to the playbook?"))

    def test_checker_sees_text_written_before_tool_calls(self):
        # Check #47: the options table came before a tool call; the checker only got the last part.
        self.write_transcript([prompt_entry("did you compare other ways?"),
                               assistant("Options A–E: A hook, B memory signal", "Bash", {"command": "ls"}),
                               assistant(LONG + "\n" + GOOD_LINE)])
        self.stop(LONG + "\n" + GOOD_LINE)
        self.assertIn("Options A–E", self.checks()[0]["independent"]["input"])
        self.write_transcript([prompt_entry("next", "p9")], mode="a")  # last message not in the transcript yet
        self.stop("Only the hook has this text. " + LONG + "\n" + GOOD_LINE)
        self.assertIn("Only the hook has this text.", self.checks()[-1]["independent"]["input"])

    def run_of_changes(self, last_prompt, last_tool=("Bash", {"command": "git push"}), keep=False):
        # Owner had to ask on 2026-10-25 "did you update or create a playbook?" after a long run.
        if not keep:
            self.write_transcript([])
        outs = []
        for i, text in enumerate(["set up the service account", "now the permissions", last_prompt], 1):
            tool = last_tool if i == 3 else ("Bash", {"command": "git push"})
            self.write_transcript([prompt_entry(text, f"p{i}"), assistant("Done.", *tool)], mode="a")
            outs.append(self.stop("Done."))
        return outs

    def test_playbook_reminder_when_a_run_of_changes_is_finished(self):
        outs = self.run_of_changes("tested on my phone, it's working now")
        self.assertIsNone(outs[0])
        self.assertIn("did not update", outs[2]["hookSpecificOutput"]["additionalContext"])
        self.assertTrue(self.checks()[-1]["playbook_reminder"])
        self.assertFalse(self.fake_log.exists())  # a short reply: no independent check
        self.write_transcript([prompt_entry("thanks", "p4"), assistant("Done.")], mode="a")
        self.assertIsNone(self.stop("Done."))  # once per run

    def test_playbook_reminder_when_lessons_go_to_memory_only(self):
        # 25 Oct: one real chat updated its project memory 9 times and wrote no playbook.
        memory = {"file_path": str(pathlib.Path.home() / ".claude/projects/D--Apps-X/memory/project_setup.md")}
        outs = self.run_of_changes("now the next step", ("Edit", memory))
        text = outs[2]["hookSpecificOutput"]["additionalContext"]
        self.assertIn("a playbook", text)
        self.assertNotIn("project memory", text)  # memory was updated
        self.assertTrue(selfcheck.lesson_write("Bash", {"command": "cd /d/KB && printf x >> self-review-log.md"}))
        self.assertFalse(selfcheck.lesson_write("Edit", {"file_path": "E:/Work/X/lib/memory/cache.md"}))

    def test_upkeep_reminder_names_only_what_is_missing(self):
        # Owner, 2026-10-25: "so all the long term memory, relevant .md files are always up to date"
        # without asking every time (it used to be the owner's stock prompt after each task).
        self.write_transcript([prompt_entry("fix the release notes", "p0"), assistant("Done.", "Bash", {"command": "git push"}),
                               assistant("Saved.", "Edit", {"file_path": "E:/Work/X/RELEASE_TODO.md"})])
        self.stop("Done.")
        outs = self.run_of_changes("tested, it's working now", keep=True)
        text = outs[2]["hookSpecificOutput"]["additionalContext"]
        self.assertIn("project memory", text)
        self.assertIn("a playbook", text)
        self.assertNotIn("relevant .md docs", text)  # docs were updated
        cd = "cd /c/Users/me/.claude/projects/D--Apps-X/memory && sed -i 's/a/b/' MEMORY.md"
        self.assertTrue(selfcheck.memory_write("Bash", {"command": cd}))
        self.assertFalse(selfcheck.doc_write("Bash", {"command": cd}))
        self.assertTrue(selfcheck.doc_write("Edit", {"file_path": r"E:\Work\X\CLAUDE.md"}))
        self.assertFalse(selfcheck.doc_write("Edit", {"file_path": r"C:\Users\me\AppData\Local\Temp\claude\s\scratchpad\n.md"}))

    def test_owner_asking_for_upkeep_gets_no_reminder(self):
        self.assertIsNone(self.run_of_changes("done. Update memory and relevant documentation")[2])

    def test_no_playbook_reminder_mid_task_or_after_a_playbook(self):
        self.assertIsNone(self.run_of_changes("now the next step")[2])
        # All three kept up to date (memory, a doc, a playbook): nothing to remind.
        self.write_transcript([])
        memory = str(pathlib.Path.home() / ".claude/projects/D--Apps-X/memory/project_setup.md")
        for i, tool in enumerate([("Edit", {"file_path": memory}), ("Edit", {"file_path": "E:/Work/X/RELEASE_TODO.md"}),
                                  ("Write", {"file_path": str(self.kb / "new-playbook.md")})], 1):
            self.write_transcript([prompt_entry(f"step {i}", f"q{i}"), assistant("Done.", "Bash", {"command": "git push"}),
                                   assistant("Saved.", *tool)], mode="a")
            out = self.stop("Done.")
        self.write_transcript([prompt_entry("all working now", "q9"), assistant("Done.", "Bash", {"command": "git push"})], mode="a")
        self.assertIsNone(self.stop("Done."))

    def test_rejection_feedback_is_counted(self):
        self.stop("ok")  # first run in a session only sets the starting point
        self.write_transcript([{"type": "user", "message": {"content": [{"type": "tool_result", "content":
            "The user doesn't want to proceed with this tool use. To tell you how to proceed, the user said:"
            "\n" "did you think about a better way to do this?"}]}}], mode="a")
        self.stop("ok")
        self.assertEqual([q["source"] for q in self.queue()], ["rejection"])


class Gate(Base):
    def pre(self, tool, args, **kw):
        return self.hook(dict({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": args,
                               "prompt_id": "p1"}, **kw))

    SHOT = ("mcp__claude-in-chrome__computer", {"action": "screenshot", "tabId": 1})
    FIND = ("mcp__claude-in-chrome__find", {"query": "Save button", "tabId": 1})

    def denied(self, out):
        return bool(out) and out["hookSpecificOutput"]["permissionDecision"] == "deny"

    # Screenshot rule (owner: browser 2026-11-05, phone 2026-11-04; every call since the 2026-11-17 miss).
    def test_every_screenshot_is_sent_back_once_then_the_identical_retry_passes(self):
        out = self.pre(*self.SHOT)
        self.assertTrue(self.denied(out))
        self.assertIn("get_page_text", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.pre(*self.SHOT))  # the retry passes
        self.assertTrue(self.denied(self.pre(*self.SHOT)))  # a later identical one is sent back again

    def test_own_playbook_and_phone_script_are_named_only_when_they_exist(self):
        # Shared repo: other people don't have these files, so the message must work without them.
        reason = lambda out: out["hookSpecificOutput"]["permissionDecisionReason"]
        no_files = reason(self.pre(*self.SHOT)) + reason(self.pre("Bash", {"command": "adb exec-out screencap -p > a.png"}))
        for name in ("browser-automation-text-not-screenshots.md", "android-phone-usb-test-flutter-app.md",
                     "android_screen_text.py"):
            self.assertNotIn(name, no_files)
        self.assertIn("uiautomator dump", no_files)
        (self.kb / "browser-automation-text-not-screenshots.md").write_text("x", encoding="utf-8")
        (self.kb / "scripts").mkdir()
        (self.kb / "scripts" / "android_screen_text.py").write_text("x", encoding="utf-8")
        own = reason(self.pre("mcp__claude-in-chrome__computer", {"action": "screenshot", "tabId": 2})) + reason(
            self.pre("Bash", {"command": "adb exec-out screencap -p > b.png"}))
        self.assertIn("(playbook browser-automation-text-not-screenshots.md)", own)
        self.assertIn("android_screen_text.py", own)

    def test_a_text_lookup_before_does_not_let_screenshots_through(self):
        # The 2026-11-17 miss: a find before each screenshot reset the old count, so they all passed.
        self.write_transcript([assistant(None, *self.FIND)], mode="a")
        self.assertTrue(self.denied(self.pre(*self.SHOT)))

    def test_zoom_and_a_changed_retry_are_sent_back(self):
        self.assertTrue(self.denied(self.pre("mcp__claude-in-chrome__computer", {"action": "zoom", "region": [0, 0, 9, 9]})))
        self.assertTrue(self.denied(self.pre(*self.SHOT)))
        self.assertTrue(self.denied(self.pre("mcp__claude-in-chrome__computer", {"action": "screenshot", "tabId": 1,
                                                                                 "scale": 0.4})))  # not the same call

    def test_a_batch_holding_a_screenshot_is_sent_back_one_without_passes(self):
        batch = {"actions": [{"name": "navigate", "input": {"url": "x"}},
                             {"name": "computer", "input": {"action": "screenshot"}}]}
        self.assertTrue(self.denied(self.pre("mcp__claude-in-chrome__browser_batch", batch)))
        self.assertIsNone(self.pre("mcp__claude-in-chrome__browser_batch", batch))
        clicks = {"actions": [{"name": "navigate", "input": {"url": "x"}},
                              {"name": "computer", "input": {"action": "left_click", "ref": "ref_1"}}]}
        self.assertIsNone(self.pre("mcp__claude-in-chrome__browser_batch", clicks))

    def test_other_screenshot_tools_are_sent_back(self):
        for tool, args in [("mcp__plugin_model-apps_playwright__browser_take_screenshot", {"scale": "css"}),
                           ("mcp__playwright__browser_take_screenshot", {}),
                           ("mcp__Claude_Browser__computer", {"action": "screenshot"}),
                           ("mcp__some-desktop__take_screenshot", {})]:
            self.assertTrue(self.denied(self.pre(tool, args)), tool)

    def test_text_lookups_clicks_and_other_tools_are_never_sent_back(self):
        for tool, args in [self.FIND, ("mcp__claude-in-chrome__read_page", {"tabId": 1}),
                           ("mcp__claude-in-chrome__get_page_text", {"tabId": 1}),
                           ("mcp__claude-in-chrome__navigate", {"url": "https://example.com"}),
                           ("mcp__plugin_model-apps_playwright__browser_snapshot", {}),  # text tree, not an image
                           ("mcp__plugin_model-apps_playwright__browser_navigate", {"url": "x"}),
                           ("Read", {"file_path": "C:/x/shot.png"}), ("Grep", {"pattern": "screenshot"})]:
            self.assertIsNone(self.pre(tool, args), tool)
        self.assertIsNone(self.pre("mcp__claude-in-chrome__computer", {"action": "left_click", "coordinate": [1, 2]}))

    def test_helper_agents_screenshots_are_sent_back_too(self):
        self.assertTrue(self.denied(self.pre(*self.SHOT, agent_id="a1")))
        self.assertIsNone(self.pre(*self.SHOT, agent_id="a1"))

    PHONE_SHOTS = [
        "adb exec-out screencap -p > shot.png",
        "$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe -s R3CX exec-out screencap -p > x.png",
        "adb shell screencap -p /sdcard/s.png && adb pull /sdcard/s.png",
        'adb shell "screencap -p /sdcard/s.png"',
        "adb shell screenrecord --time-limit 5 /sdcard/v.mp4",
        "MSYS_NO_PATHCONV=1 adb shell screencap /sdcard/a.png",
        "xcrun simctl io booted screenshot shot.png",
        "idevicescreenshot shot.png",
        "cd app && flutter screenshot --out=s.png",
    ]

    def test_phone_captures_are_sent_back_once_in_bash_and_powershell(self):
        for cmd in self.PHONE_SHOTS:
            out = self.pre("Bash", {"command": cmd})
            self.assertTrue(self.denied(out), cmd)
            self.assertIn("uiautomator dump", out["hookSpecificOutput"]["permissionDecisionReason"])
            self.assertIsNone(self.pre("Bash", {"command": cmd}), cmd)  # the retry passes
        ps = '& "$env:LOCALAPPDATA\\Android\\Sdk\\platform-tools\\adb.exe" exec-out screencap -p | Set-Content -AsByteStream s.png'
        self.assertTrue(self.denied(self.pre("PowerShell", {"command": ps})))

    def test_a_retry_with_a_new_description_still_passes(self):
        cmd = self.PHONE_SHOTS[0]
        self.assertTrue(self.denied(self.pre("Bash", {"command": cmd, "description": "Take a phone screenshot"})))
        self.assertIsNone(self.pre("Bash", {"command": cmd, "description": "Retry the phone screenshot"}))
        self.assertTrue(self.denied(self.pre("Bash", {"command": cmd + " ", "description": "x"})))  # another command
        shot = {"action": "screenshot", "tabId": 1, "action_summary": "Looks at the page"}
        self.assertTrue(self.denied(self.pre("mcp__claude-in-chrome__computer", shot)))
        self.assertIsNone(self.pre("mcp__claude-in-chrome__computer", dict(shot, action_summary="Looks again")))

    def test_phone_lookalikes_and_text_tools_pass(self):
        for cmd in ["grep -rn screencap ~/kb", "echo 'take a screenshot'",
                    "python ~/kb/scripts/android_screen_text.py --find Save",
                    "adb shell uiautomator dump /sdcard/u.xml", "adb install -r app.apk", "adb exec-out ls /sdcard",
                    "adb shell input tap 10 20; echo screencap", "flutter test test/screenshot_test.dart"]:
            self.assertIsNone(self.pre("Bash", {"command": cmd}), cmd)

    def test_two_screenshots_at_once_both_pass_on_retry(self):
        other = ("mcp__claude-in-chrome__computer", {"action": "screenshot", "tabId": 2})
        self.assertTrue(self.denied(self.pre(*self.SHOT)))
        self.assertTrue(self.denied(self.pre(*other)))
        self.assertIsNone(self.pre(*self.SHOT))
        self.assertIsNone(self.pre(*other))

    def test_send_backs_are_logged_apart_from_blocked_checks(self):
        self.pre(*self.SHOT)
        self.pre("Bash", {"command": self.PHONE_SHOTS[0]})
        self.assertEqual([c for c in self.checks() if c.get("verdict") == "blocked"], [])
        lines = (self.kb / "selfcheck" / "screenshots.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(x)["kind"] for x in lines], ["screen", "phone"])

    def test_gate_off_lets_screenshots_through(self):
        (self.kb / "selfcheck-config.json").write_text('{"gate": false}', encoding="utf-8")
        self.assertIsNone(self.pre(*self.SHOT))

    def test_a_fault_lets_the_screenshot_through(self):
        data = self.kb / "selfcheck"
        data.mkdir(parents=True, exist_ok=True)
        (data / "screenshots").write_text("not a folder", encoding="utf-8")  # the marks can't be written
        self.assertIsNone(self.pre(*self.SHOT))
        self.assertIsNone(self.pre(*self.SHOT))

    def test_risky_change_without_decisions_is_blocked_once(self):
        self.answer.write_text('{"ok": false, "question": "Is a backup taken first?"}', encoding="utf-8")
        out = self.pre("Bash", {"command": "git push origin main"})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("Is a backup taken first?", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.pre("Bash", {"command": "git push origin main"}))

    def test_once_per_reply_without_a_prompt_id(self):
        self.answer.write_text('{"ok": false, "question": "Is a backup taken first?"}', encoding="utf-8")
        self.assertIsNotNone(self.pre("Bash", {"command": "git push"}, prompt_id=None))
        self.assertIsNone(self.pre("Bash", {"command": "git push"}, prompt_id=None))

    def test_decisions_listed_passes_without_check(self):
        self.write_transcript([prompt_entry("ship it"), assistant(
            "Decisions: goal release today · ways push now / wait for CI · alt: tag first")])
        self.assertIsNone(self.pre("Bash", {"command": "git push"}))
        self.assertFalse(self.fake_log.exists())
        self.assertEqual(self.checks()[0]["verdict"], "passed (decisions listed)")

    def test_decisions_without_goal_and_ways_are_checked(self):
        # Case 21: a Decisions line whose alternatives were only ways to build the first idea.
        self.write_transcript([prompt_entry("ship it"), assistant("Decisions: push now · alt: wait for CI")])
        self.pre("Bash", {"command": "git push"})
        self.assertTrue(self.fake_log.exists())
        self.assertNotEqual(self.checks()[0]["verdict"], "passed (decisions listed)")

    def test_safe_tools_not_gated(self):
        self.assertIsNone(self.pre("Bash", {"command": "git status"}))
        self.assertIsNone(self.pre("Bash", {"command": 'rm -rf "C:/Users/me/AppData/Local/Temp/x/scratchpad/t"'}))
        self.assertTrue(selfcheck.risky_reason("Bash", {"command": "rm -rf lib/"}))
        # Found by replaying real sessions: reading a file that mentions a tool isn't risky.
        self.assertEqual(selfcheck.risky_reason("Bash", {"command": "cat codemagic.yaml | head"}), "")
        self.assertEqual(selfcheck.risky_reason("Edit", {"file_path": "docs/SETUP_NOTES.md"}), "")
        self.assertTrue(selfcheck.risky_reason("Edit", {"file_path": "store/APP_PRIVACY_LABELS.md"}))
        self.assertTrue(selfcheck.risky_reason("Edit", {"file_path": "lib/subscription_service.dart"}))
        self.assertTrue(selfcheck.risky_reason("Edit", {"file_path": "/home/me/.claude/CLAUDE.md"}))
        self.assertIsNone(self.pre("Edit", {"file_path": "lib/home_screen.dart"}))
        self.assertEqual(self.checks(), [])

    def test_every_form_of_a_risky_command_is_gated(self):
        # Review 2026-10-25: `git -C <folder> push`, `rm -f -r` and a delete next to a temp path slipped.
        risky = ['git -C "E:/Work/X" commit -m x', "git -C core push", "git -c user.email=a@b commit -m x",
                 "git --git-dir=.x --work-tree=core push", "git --no-pager push",
                 '"C:/Program Files/Git/bin/git.exe" push origin main', "git add . && git commit -m y",
                 "git reset --hard HEAD~1", "git rebase main", "git clean -fdx", "git clean -n -f", "git clean --force",
                 "git branch -D old", "git stash drop", "git stash clear", "git checkout -- .",
                 "git checkout HEAD -- lib/a.dart", "git checkout .", "git restore lib/a.dart",
                 "git restore --staged --worktree a", "git restore -s HEAD a", "git branch -dD x", "rm -f -r lib", "rm -fr lib", "rm -R lib",
                 "rm --force --recursive lib", "Remove-Item -Recurse E:/Work/X/lib; echo $TMP",
                 "rm -rf $TMP/x && git push", "rm -rf $TMP/x lib", "rm -rf $S/../lib", "rd /s /q build",
                 "rmdir /s build", "rm -rf $TMP/x; rm -rf lib", 'Remove-Item -Path "E:/Work/X/old" -Recurse']
        safe = ["git status", "git -C core status", "git -C core log -3", "git commit-graph write", "git clean -n",
                "git branch -d merged", "git stash list", "git checkout main", "git checkout -b feature",
                "git restore --staged a.txt", "rm file.txt", "rmdir emptydir", "rm -rf $TMP/x",
                'Remove-Item -Recurse -Force "$S/x"', "Remove-Item -Recurse $env:TEMP\\x", 'rm -rf "$(mktemp -d)"',
                "rm -rf $S/a $TMP/b", "echo digit push", "ls .git/hooks",
                # found replaying real chats: temp paths in variables, cd into temp, options, redirects
                'S="C:/Users/me/AppData/Local/Temp/x/scratchpad"; R="$S/run2"; rm -rf "$R"; mkdir -p "$R"',
                '$d = "C:\\Users\\me\\AppData\\Local\\Temp\\x\\scratchpad\\f"\nRemove-Item "$d\\f.pdf" -ErrorAction SilentlyContinue',
                'D="$(mktemp -d)" && rm -rf "$D" 2>/dev/null', "rm -rf $TMP/x > /dev/null 2>&1",
                "cd /tmp && rm -rf apkchk && mkdir apkchk", 'if (1) { Remove-Item -Recurse "$env:TEMP\\x" }',
                "$del = UiDump | Select-String x", "const del  = 2", "cat >\"$TEMP/fix.ps1\" <<'EOF'\nRemove-Item -Recurse C:/proj\ngit push\nEOF",
                "@'\nRemove-Item -Recurse C:/proj\n'@ | Set-Content x.ps1"]
        risky += ["cd /tmp/x && cd /e/proj && rm -rf build", 'S="E:/Work/X"; rm -rf "$S/lib"', "rm -rf ../lib",
                  "python - <<'EOF'\nimport os\nEOF\ngit push", "bash <<'EOF'\ngit push\nEOF",
                  "cat <<'EOF' | bash\nrm -rf lib\nEOF", 'rm -rf "$S/x" lib 2>/dev/null']
        for command in risky:
            self.assertTrue(selfcheck.risky_reason("Bash", {"command": command}), command)
        for command in safe:
            self.assertEqual(selfcheck.risky_reason("Bash", {"command": command}), "", command)
        # The reason names the real risk, not the harmless temp delete before it.
        self.assertEqual(selfcheck.risky_reason("Bash", {"command": "rm -rf $TMP/x && git push"}), "command: git push")

    def test_browser_changes_are_gated(self):
        # Found on 2026-10-25: Play/Cloud/RevenueCat changes made in Chrome were never checked.
        click = "mcp__claude-in-chrome__computer"
        risky = [(click, {"action": "left_click", "coordinate": [1, 2],
                          "action_summary": "Submits the one closed-testing change for Google review"}),
                 (click, {"action": "left_click", "action_summary": "Confirms deleting service account x"}),
                 ("mcp__claude-in-chrome__browser_batch", {"actions": [
                     {"name": "computer", "input": {"action": "screenshot"}},
                     {"name": "computer", "input": {"action": "left_click",
                                                    "action_summary": "Saves the account-level permission changes"}}]}),
                 ("mcp__claude-in-chrome__file_upload", {"paths": ["key.json"], "ref": "ref_1"}),
                 ("mcp__claude-in-chrome__javascript_tool", {"text": "document.querySelector('#save').click()"})]
        for tool, args in risky:
            self.assertTrue(selfcheck.risky_reason(tool, args), args)
        safe = [(click, {"action": "screenshot"}),
                (click, {"action": "left_click", "action_summary": "Opens the payments-account issue page (view only)"}),
                (click, {"action": "left_click", "action_summary": "Cancels the grant-access form without saving"}),
                (click, {"action": "type", "action_summary": "Types the service account name"}),
                ("mcp__claude-in-chrome__javascript_tool", {"text": "document.title"})]
        for tool, args in safe:
            self.assertEqual(selfcheck.risky_reason(tool, args), "", args)
        self.answer.write_text('{"ok": false, "question": "Is the reference app set up the same?"}', encoding="utf-8")
        out = self.pre(*risky[0])
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("browser: Submits the one closed-testing change", self.checks()[0]["tool"])

    def test_browser_change_counts_for_the_reply(self):
        self.write_transcript([prompt_entry("fix the permissions"), assistant(
            tool="mcp__claude-in-chrome__computer",
            args={"action": "left_click", "action_summary": "Saves the account-level permission changes"})])
        self.stop(LONG + "\n" + GOOD_LINE.replace("(high,", "(low,"))
        check = self.checks()[0]
        self.assertEqual(check["verdict"], "sent back")
        self.assertIn("labelled low stakes", check["free_problems"][0])

    def test_the_owners_own_order_is_not_gated(self):
        # Owner, 2026-10-25: "with a very clear instruction like commit and push … just execute my instructions".
        self.answer.write_text('{"ok": false, "question": "Did you check the remote?"}', encoding="utf-8")
        self.write_transcript([prompt_entry("commit and push all to private repo's main")])
        for command in ("git commit -qm x", "git -C core push origin main"):
            self.assertIsNone(self.pre("Bash", {"command": command}), command)
        self.assertEqual(self.checks(), [])
        self.assertIsNotNone(self.pre("Bash", {"command": "rm -rf lib"}))  # not what was ordered

    def test_no_order_in_a_question_or_after_dont(self):
        for prompt in ("fix the typo but don't push", "did you push it?", "did you commit and push it?","never commit without asking. fix it",
                       "push to the private repo now.\ndon't push to the public repo",
                       'go <pasted_content id="1">\npush now\n</pasted_content id="1">'):
            self.assertFalse(selfcheck.ordered(prompt, "command: git push"), prompt)
        self.assertTrue(selfcheck.ordered("Tests pass? Then push.", "command: git push"))
        self.assertTrue(selfcheck.ordered("build the release", "command: flutter build"))
        # Found replaying real chats: nouns and reports aren't orders; a polite question is one.
        for prompt in ("add sync to the build plan", "build failed again: see log", "test it with a release build",
                       "add push notifications to the app"):
            self.assertFalse(selfcheck.ordered(prompt, "command: flutter build" if "build" in prompt else
                                               "command: git push"), prompt)
        for prompt in ("now build the app on my phone", "done, ok commit only the workflow and push",
                       "can you commit and push?", "yes to 1 and 2, commit and push everything."):
            self.assertTrue(selfcheck.ordered(prompt, "command: flutter build" if "build" in prompt else
                                              "command: git push"), prompt)

    def test_background_task_notices_are_not_the_owners_words(self):
        entries = [prompt_entry("looks good"), {"type": "attachment", "attachment": {
            "type": "queued_command", "prompt": "<task-notification> flutter build apk completed</task-notification>"}}]
        self.assertNotIn("task-notification", selfcheck.exchanges(entries)[-1]["prompt"])
        self.assertEqual(selfcheck.classify("<task-notification> are you sure </task-notification>")[0], [])
        for prompt in ("delete the build folder", "rm -rf the build folder", "ok, now rm -rf build"):  # even named
            self.assertFalse(selfcheck.ordered(prompt, "command: rm -rf"), prompt)
        self.assertFalse(selfcheck.ordered("push it", "file: CLAUDE.md"))

    def test_reply_after_the_owners_order_is_not_checked(self):
        self.write_transcript([prompt_entry("commit and push"), assistant("Done.", "Bash", {"command": "git push"})])
        self.assertIsNone(self.stop(LONG + "\n" + GOOD_LINE))  # high-stakes line, but the owner ordered it
        self.assertIsNone(self.stop(LONG))  # no 🟣 line needed either
        self.assertFalse(self.fake_log.exists())
        # Something risky that wasn't ordered is still checked.
        self.write_transcript([prompt_entry("commit and push", "p2"), assistant("Done.", "Bash", {"command": "git push"}),
                               assistant("Also cleaned.", "Bash", {"command": "rm -rf lib"})], mode="a")
        self.assertIn("sent back", self.stop(LONG)["systemMessage"])

    def test_helper_agents_not_gated(self):
        self.assertIsNone(self.pre("Bash", {"command": "git push"}, agent_id="a1"))

    def test_plan_is_checked_before_the_dialog(self):
        self.answer.write_text('{"ok": false, "question": "Which cheaper way did you compare?"}', encoding="utf-8")
        out = self.pre("ExitPlanMode", {"plan": "Build X with Decisions: y · alt: z"})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    # Case 24 (repeated 11-01, 11-03): a code plan without the critical second pass goes back, every time.
    CODE_PLAN = "## Fixes\n1. Fix the drag in `lib/ui/map_screen.dart:546`.\n2. Add a test.\n"

    def test_code_plan_without_critical_pass_is_sent_back(self):
        out = self.pre("ExitPlanMode", {"plan": self.CODE_PLAN})
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("Problems found in my draft", reason)
        self.assertIn("edge cases", reason)
        self.assertEqual(self.checks()[-1]["stage"], "plan-sections")
        # Shown again unchanged in the same reply: still sent back (not once-per-prompt).
        self.assertEqual(self.pre("ExitPlanMode", {"plan": self.CODE_PLAN})["hookSpecificOutput"]["permissionDecision"],
                         "deny")

    def test_code_plan_with_critical_pass_goes_on_to_the_normal_check(self):
        plan = self.CODE_PLAN + "\n## Problems found in my draft\n- The first version missed overnight rules.\n"
        out = self.pre("ExitPlanMode", {"plan": plan})  # fake answer: ok -> passes
        self.assertNotIn("deny", json.dumps(out or {}))
        self.assertNotIn("plan-sections", [c.get("stage") for c in self.checks()])

    def test_plan_without_code_is_not_held_to_it(self):
        out = self.pre("ExitPlanMode", {"plan": "Publish the store listing text and ask the owner about pricing."})
        self.assertNotIn("plan-sections", [c.get("stage") for c in self.checks()])
        self.assertNotIn("deny", json.dumps(out or {}))

    def test_plan_read_from_the_newest_plan_file_when_the_tool_input_is_empty(self):
        (self.kb / "plans").mkdir()
        (self.kb / "plans" / "p.md").write_text(self.CODE_PLAN, encoding="utf-8")
        out = self.pre("ExitPlanMode", {})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_no_plan_text_anywhere_fails_open(self):
        out = self.pre("ExitPlanMode", {})
        self.assertNotIn("plan-sections", [c.get("stage") for c in self.checks()])
        self.assertNotIn("Problems found in my draft", json.dumps(out or {}))

    def test_old_plan_file_is_ignored(self):
        (self.kb / "plans").mkdir()
        old = self.kb / "plans" / "old.md"
        old.write_text(self.CODE_PLAN, encoding="utf-8")
        t = time.time() - 7 * 3600
        os.utime(old, (t, t))
        self.pre("ExitPlanMode", {})
        self.assertNotIn("plan-sections", [c.get("stage") for c in self.checks()])

    def test_send_back_off_only_logs(self):
        (self.kb / "selfcheck-config.json").write_text('{"send_back": false}', encoding="utf-8")
        out = self.pre("ExitPlanMode", {"plan": self.CODE_PLAN})
        self.assertNotIn("Problems found in my draft", json.dumps(out or {}))
        self.assertEqual(self.checks()[0]["verdict"], "flagged (log only)")


class PlanCheckUnit(unittest.TestCase):
    def test_broken_check_never_blocks(self):
        with mock.patch.object(selfcheck, "plan_text", side_effect=RuntimeError("boom")):
            self.assertFalse(selfcheck.plan_lacks_critical_pass({"plan": "x"}))

    def test_section_wordings_accepted(self):
        for heading in ("## Problems found in my draft", "Critical pass: found 4 problems",
                        "problems in the first draft (now fixed)", "## Critical second pass"):
            self.assertFalse(selfcheck.plan_lacks_critical_pass({"plan": "edit lib/a.dart\n" + heading}), heading)
        self.assertTrue(selfcheck.plan_lacks_critical_pass({"plan": "edit lib/a.dart\n## Risks\n- low"}))


class PromptHook(Base):
    def prompt(self, text, pid="p2"):
        return self.hook({"hook_event_name": "UserPromptSubmit", "prompt": text, "prompt_id": pid})

    def test_doubt_gets_a_note_and_is_counted(self):
        out = self.prompt("are you sure this works?")
        self.assertIn("not the owner's words", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.queue()[0]["kinds"], ["doubt"])

    def test_check_request_counted_without_note(self):
        self.assertIsNone(self.prompt("please double check everything"))
        self.assertEqual(self.queue()[0]["kinds"], ["check-request"])

    def test_same_message_counted_once(self):
        self.prompt("are you sure?", "a")
        self.prompt("are you sure?", "b")
        self.assertEqual(len(self.queue()), 1)

    def test_doubt_after_independent_pass_marks_possible_false_pass(self):
        self.stop(LONG + "\n" + GOOD_LINE)
        self.prompt("did you check the edge cases?")
        ratings = [c for c in self.checks() if c["type"] == "rating"]
        self.assertEqual(ratings[0]["rating"], "possible false pass")


class Report(Base):
    def test_trend_report_shows_the_checks(self):
        self.stop(LONG)  # one check, sent back
        log = self.kb / "self-review-log.md"
        log.write_text(log.read_text(encoding="utf-8") + "\n## Miss log\n\n| Date | Type |\n|---|---|\n"
                       "| 2026-10-24 | lapse |\n", encoding="utf-8")
        env = dict(os.environ, SELFCHECK_KB=str(self.kb))
        run = subprocess.run([sys.executable, "-I", str(TOOLS / "benchmark_summary.py"), str(log)],
                             capture_output=True, env=env, timeout=60)
        self.assertIn("Self-check (14 days): 1 checks, 1 sent back", run.stdout.decode("utf-8"))
        html_text = (self.kb / "self-review-trend.html").read_text(encoding="utf-8")
        self.assertIn("Self-check hooks", html_text)
        self.assertIn("Not running for 2+ days", html_text)  # only Stop has run here
        self.assertIn("Recent checks", html_text)
        self.assertIn("no 🟣 Self-check line", html_text)  # the check's own details are readable


class CoreChangeLog(unittest.TestCase):
    def test_change_day_without_entry_is_reported(self):
        import benchmark_summary
        with tempfile.TemporaryDirectory() as tmp:
            kb = pathlib.Path(tmp)
            work = kb / "core"
            work.mkdir()
            git = ["git", f"--git-dir={kb / '.core-backup.git'}", f"--work-tree={work}"]
            subprocess.run(git[:2] + ["init", "-q"], check=True)
            env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                       GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
            for day in ("2026-01-01", "2026-01-02", "2026-01-03"):
                (work / "f.txt").write_text(day, encoding="utf-8")
                subprocess.run(git + ["add", "-A"], check=True)
                subprocess.run(git + ["commit", "-q", "-m", day], check=True,
                               env=dict(env, GIT_AUTHOR_DATE=day + "T12:00:00", GIT_COMMITTER_DATE=day + "T12:00:00"))
            (kb / "core-changes.md").write_text("### 2026-01-02 — something\n", encoding="utf-8")
            # Day 1 is the first backup (everything existed already); day 2 has an entry.
            self.assertEqual(benchmark_summary.core_change_gaps(kb), ["2026-01-03"])

    def test_no_private_history_means_no_warning(self):
        import benchmark_summary
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(benchmark_summary.core_change_gaps(pathlib.Path(tmp)), [])


class Manual(Base):
    def test_rate_with_a_bad_id_shows_usage(self):
        run = subprocess.run([sys.executable, "-I", "-S", str(SCRIPT), "rate", "abc", "right"], capture_output=True,
                             env=dict(os.environ, SELFCHECK_KB=str(self.kb)), timeout=30)
        self.assertEqual(run.returncode, 2)
        self.assertIn("usage", run.stdout.decode("utf-8"))
        self.assertEqual(self.checks(), [])

    def rate(self, *args):
        return subprocess.run([sys.executable, "-I", "-S", str(SCRIPT), "rate", *args], capture_output=True,
                              env=dict(os.environ, SELFCHECK_KB=str(self.kb)), timeout=30).returncode

    def test_rate_only_a_check_that_exists(self):
        self.assertEqual(self.rate("99", "right"), 1)  # a typo is not recorded
        self.assertEqual(self.checks(), [])
        self.stop(LONG)  # check #1
        self.assertEqual(self.rate("#1", "wrong", "too", "strict"), 0)
        self.assertEqual(self.checks()[-1], dict(self.checks()[-1], type="rating", id=1, rating="wrong"))

    def test_unreadable_counter_continues_after_the_log(self):
        self.stop(LONG)  # #1
        (self.kb / "selfcheck" / "counter.txt").write_text("", encoding="utf-8")  # e.g. read mid-write
        self.assertTrue(self.stop(LONG)["systemMessage"].startswith("🔵 #2 "))


class Concurrency(unittest.TestCase):
    """Hooks run at the same time (parallel tool calls, several sessions); on Windows a file being
    read or replaced by one can't be replaced or read by another for a moment."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_replace_is_retried_and_uses_its_own_temp_file(self):
        real, names = os.replace, []

        def busy_twice(src, dst):
            names.append(pathlib.Path(src).name)
            if len(names) < 3:
                raise PermissionError("in use")
            real(src, dst)
        with mock.patch.object(selfcheck.os, "replace", busy_twice):
            selfcheck.save_json(self.path, {"a": 1})
        self.assertEqual(selfcheck.load_json(self.path, None), {"a": 1})
        self.assertIn(str(os.getpid()), names[0])
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_failed_save_leaves_no_temp_file(self):
        with mock.patch.object(selfcheck.os, "replace", side_effect=PermissionError("in use")):
            with self.assertRaises(PermissionError):
                selfcheck.save_json(self.path, {"a": 1})
        self.assertEqual(list(self.path.parent.glob("*")), [])

    def test_read_is_retried(self):
        self.path.write_text('{"x": 1}', encoding="utf-8")
        real, calls = pathlib.Path.read_text, []

        def busy_once(p, *a, **k):
            calls.append(p)
            if len(calls) == 1:
                raise PermissionError("in use")
            return real(p, *a, **k)
        with mock.patch.object(pathlib.Path, "read_text", busy_once):
            self.assertEqual(selfcheck.load_json(self.path, {}), {"x": 1})  # not {} (state kept)


class Heartbeat(Base):
    def test_written_at_most_every_10_minutes(self):
        beat = self.kb / "selfcheck" / "heartbeat.json"
        beat.parent.mkdir(parents=True)
        t = lambda minutes: (datetime.datetime.now() + datetime.timedelta(minutes=minutes)).isoformat(timespec="seconds")
        beats = {"Stop": t(-1), "UserPromptSubmit": t(-11), "PreToolUse": t(60 * 24)}  # recent, old, future
        beat.write_text(json.dumps(beats), encoding="utf-8")
        self.stop("Done.")
        self.hook({"hook_event_name": "UserPromptSubmit", "prompt": "hi", "prompt_id": "p"})
        self.hook({"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}, "prompt_id": "p"})
        now = json.loads(beat.read_text(encoding="utf-8"))
        self.assertEqual(now["Stop"], beats["Stop"])
        self.assertNotEqual(now["UserPromptSubmit"], beats["UserPromptSubmit"])
        self.assertNotEqual(now["PreToolUse"], beats["PreToolUse"])

    def test_a_heartbeat_failure_never_stops_the_check(self):
        (self.kb / "selfcheck" / "heartbeat.json").mkdir(parents=True)  # can be neither read nor replaced
        self.assertIn("sent back", self.stop(LONG)["systemMessage"])
        self.assertFalse((self.kb / "selfcheck" / "errors.jsonl").exists())


class PersonalDataGuard(unittest.TestCase):
    """check_no_personal_data.py in a throwaway repo laid out like core/ (tools/ inside it)."""
    NOREPLY = "1+t@users.noreply.github.com"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name) / "core"
        (self.repo / "tools").mkdir(parents=True)
        shutil.copy(TOOLS / "check_no_personal_data.py", self.repo / "tools")
        terms = pathlib.Path(self.tmp.name) / "private-terms.txt"
        terms.write_text("# test terms\nsecret-word\nQ:\\Private\n", encoding="utf-8")
        self.env = dict(os.environ, PRIVATE_TERMS=str(terms), GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL=self.NOREPLY,
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL=self.NOREPLY)
        self.git("init", "-q", "-b", "main")
        self.commit("README.md", "hello\n")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, **env):
        return subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, check=True,
                              env=dict(self.env, **env)).stdout.decode().strip()

    def commit(self, name, text, **env):
        (self.repo / name).write_text(text, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"change {name}", **env)
        return self.git("rev-parse", "HEAD")

    def guard(self, *args, **env):
        run = subprocess.run([sys.executable, "-I", str(self.repo / "tools" / "check_no_personal_data.py"), *args],
                             capture_output=True, env=dict(self.env, **env), timeout=60)
        return run.returncode, run.stdout.decode("utf-8", "replace") + run.stderr.decode("utf-8", "replace")

    def test_clean_repo_passes(self):
        self.assertEqual(self.guard("--all")[0], 0)
        self.assertEqual(self.guard("--push", "HEAD")[0], 0)

    def test_word_added_then_deleted_is_still_caught(self):
        self.commit("notes.md", "call secret-word\n")
        self.commit("notes.md", "call nobody\n")  # gone from the files, still in the history
        code, out = self.guard("--push", "HEAD")
        self.assertEqual(code, 1, out)
        self.assertIn("added lines", out)

    def test_backslash_and_slash_count_the_same(self):
        (self.repo / "a.txt").write_text("path q:/private/x\n", encoding="utf-8")
        (self.repo / "b.txt").write_text('json "Q:\\\\Private\\\\x"\n', encoding="utf-8")
        code, out = self.guard("--all")
        self.assertEqual(code, 1)
        self.assertIn("a.txt", out)
        self.assertIn("b.txt", out)

    def test_committer_email_is_checked(self):
        self.commit("x.txt", "fine\n", GIT_COMMITTER_EMAIL="me@example.com")
        code, out = self.guard("--push", "HEAD")
        self.assertEqual(code, 1)
        self.assertIn("committer", out)

    def test_file_names_are_checked(self):
        (self.repo / "secret-word.txt").write_text("fine\n", encoding="utf-8")
        self.git("add", "-A")
        code, out = self.guard("--staged")
        self.assertEqual(code, 1)
        self.assertIn("file name", out)

    def test_staged_identity_is_what_git_will_record(self):
        # The no-reply address set for this commit (environment) counts, not the global user.email.
        (self.repo / "y.txt").write_text("fine\n", encoding="utf-8")
        self.git("add", "-A")
        self.assertEqual(self.guard("--staged")[0], 0)
        self.assertEqual(self.guard("--staged", GIT_AUTHOR_EMAIL="me@example.com")[0], 1)

    def test_files_of_the_pushed_commit_not_the_checked_out_one(self):
        self.git("checkout", "-q", "-b", "feature")
        added = self.commit("s.txt", "secret-word\n")  # already on the remote (outside the range)
        self.commit("t.txt", "fine\n")
        self.git("checkout", "-q", "main")
        code, out = self.guard("--push", f"{added}..feature")
        self.assertEqual(code, 1, out)
        self.assertIn("s.txt", out)

    def test_git_failure_blocks_with_a_reason(self):
        code, out = self.guard("--push", "0123456789abcdef0123456789abcdef01234567..HEAD")
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED: git", out)


class Safety(Base):
    def test_off_switch(self):
        (self.kb / "selfcheck-off").write_text("", encoding="utf-8")
        self.assertIsNone(self.stop(LONG))

    def test_inside_the_check_session_hooks_do_nothing(self):
        self.assertIsNone(self.hook({"hook_event_name": "Stop", "last_assistant_message": LONG},
                                    {"SELFCHECK_CHILD": "1"}))

    def test_damaged_state_files_start_fresh(self):
        data = self.kb / "selfcheck"
        (data / "sessions").mkdir(parents=True)
        for path in (data / "sessions" / "s1.json", data / "heartbeat.json"):
            path.write_text("[1, 2]", encoding="utf-8")  # valid JSON, wrong shape
        self.assertIn("sent back", self.stop(LONG)["systemMessage"])
        self.assertFalse((data / "errors.jsonl").exists())

    def test_bad_input_never_breaks_the_session(self):
        env = dict(os.environ, SELFCHECK_KB=str(self.kb))
        run = subprocess.run([sys.executable, "-I", "-S", str(SCRIPT)], input=b"not json", capture_output=True,
                             env=env, timeout=30)
        self.assertEqual((run.returncode, run.stdout), (0, b""))


class HistoryGuard(Base):
    """2026-11-12: a session copied the template over the real miss log (found 2026-11-22)."""
    pre, denied = Gate.pre, Gate.denied

    def test_writing_over_the_log_is_sent_back_once(self):
        log = str(self.kb / "self-review-log.md")
        out = self.pre("Write", {"file_path": log, "content": "x"})
        self.assertTrue(self.denied(out))
        self.assertIn("history guard", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.pre("Write", {"file_path": log, "content": "x"}))  # a real restore: retry passes

    def test_the_2026_11_12_command_is_sent_back(self):
        cmd = ("cd ~/kb && python - <<'EOF'\nt=open('core/templates/self-review-log.md').read()\n"
               "open('self-review-log.md','w',encoding='utf8').write(t)\nEOF")
        self.assertTrue(self.denied(self.pre("Bash", {"command": cmd})))

    def test_other_overwrites_are_sent_back(self):
        for cmd in ("cat t.md > self-review-log.md", "cp core/templates/self-review-log.md self-review-log.md",
                    "Set-Content -Path C:\\kb\\core-changes.md -Value x",
                    "python -c \"(KB / 'self-review-log.md').write_text('')\""):
            self.assertTrue(self.denied(self.pre("PowerShell", {"command": cmd})), cmd)

    def test_appending_editing_reading_and_copying_from_pass(self):
        (self.kb / "core-changes.md").write_text("x", encoding="utf-8")
        for tool, args in (("Bash", {"command": "cat >> self-review-log.md <<'EOF'\n| 2026 | lapse |\nEOF"}),
                           ("Bash", {"command": "printf '%s\\n' '| row |' >> self-review-log.md"}),
                           ("PowerShell", {"command": "Add-Content self-review-log.md 'x'"}),
                           ("PowerShell", {"command": "Out-File -Append -FilePath core-changes.md -InputObject x"}),
                           ("Bash", {"command": "cp self-review-log.md /tmp/backup.md; tail -5 self-review-log.md"}),
                           ("Bash", {"command": "python -c \"open('self-review-log.md','a').write('x')\""}),
                           ("Edit", {"file_path": str(self.kb / "core-changes.md"), "old_string": "x",
                                     "new_string": "y"}),
                           ("Write", {"file_path": str(self.kb / "other.md"), "content": "x"}),
                           ("Write", {"file_path": str(self.kb / "new" / "self-review-log.md"), "content": "x"}),
                           # 2026-11-22 false alarm: a template copied into a new temp folder.
                           ("Bash", {"command": 'SIM="$TEMP/kbsim-1"; mkdir -p "$SIM"; cd "$SIM" && '
                                                "cp core/templates/self-review-log.md self-review-log.md"}),
                           ("Bash", {"command": "cp t.md /tmp/x/self-review-log.md"})):
            self.assertFalse(self.denied(self.pre(tool, args)), (tool, args))

    def test_a_temp_folder_elsewhere_in_the_command_does_not_excuse_the_real_log(self):
        cmd = 'cd /tmp && ls; cd ~/kb && cp core/templates/self-review-log.md self-review-log.md'
        self.assertTrue(self.denied(self.pre("Bash", {"command": cmd})))


class ReviewReminder(Base):
    """Owner 2026-11-22: the loop should improve itself, but tasks start only when the owner says so."""
    prompt = PromptHook.prompt

    def log(self, misses, review_after=None):
        rows = ["| 2026-11-01 | review |"] + [f"| 2026-11-1{i % 9} | lapse |" for i in range(misses)]
        (self.kb / "self-review-log.md").write_text(
            "## Miss log\n\n| Date | Type |\n|---|---|\n" + "\n".join(rows) + "\n", encoding="utf-8")

    def test_due_review_is_suggested_once_a_day_never_started(self):
        self.log(5)
        ctx = self.prompt("fix the map pins")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("self-review is due (5 misses", ctx)
        self.assertIn("Don't start it yourself", ctx)
        self.assertIsNone(self.prompt("next thing", "p3"))  # once a day

    def test_not_due_or_switched_off_says_nothing(self):
        self.log(4)
        self.assertIsNone(self.prompt("fix the map pins"))
        self.log(6)
        (self.kb / "selfcheck-config.json").write_text('{"review_reminder": false}', encoding="utf-8")
        self.assertIsNone(self.prompt("fix the map pins", "p4"))

    def test_with_a_miss_note_both_arrive_together(self):
        self.log(5)
        ctx = self.prompt("are you sure this works?")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("may show a self-review miss", ctx)
        self.assertIn("self-review is due", ctx)


class QuestionCheck(Base):
    """Case 29 (repeat 2026-11-20): A/B questions with "My recommendation" sat above the ending the offer
    check reads, so nothing asked whether the goal already answered them."""
    REPLY = ("Fix plan ready.\n\n## Questions\n\n**A (#5):** Should reports that went on the map by themselves "
             "count toward the top badge? **My recommendation: no.**\n\nThe other fixes follow as planned.")

    def test_a_question_anywhere_gets_the_independent_check(self):
        self.answer.write_text('{"ok": false, "question": "The goal (accurate data) answers this: why not decide it?"}',
                               encoding="utf-8")
        out = self.stop(self.REPLY)
        self.assertIn("why not decide it", out["hookSpecificOutput"]["additionalContext"])
        check = self.checks()[0]
        self.assertTrue(any(r.startswith("asks the owner: **A (#5):** Should reports") for r in check["high_stakes_reasons"]))

    def test_a_question_the_checker_passes_is_not_sent_back(self):
        out = self.stop("Two Chrome windows are connected. Which one has your profile?")
        self.assertNotIn("hookSpecificOutput", out or {})
        self.assertTrue(self.fake_log.exists())  # judged by the checker, not by a word list

    def test_owner_calls_quotes_code_and_tables_get_no_check(self):
        for reply in ("Built and tested. Should I deploy it to production now?",
                      'Logged your question "is it still failing?" as a miss.',
                      "Done.\n```\nif ok? then x\n```",
                      "| Q | why? |\n|---|---|",
                      "## Why did it fail?\nThe key had expired.",
                      "So why does the pin move? Because the map re-centres after a search."):
            self.assertIsNone(self.stop(reply), reply)
        self.assertFalse(self.fake_log.exists())

    def test_switch_off(self):
        (self.kb / "selfcheck-config.json").write_text('{"question_check": false}', encoding="utf-8")
        self.assertIsNone(self.stop(self.REPLY))
        self.assertFalse(self.fake_log.exists())

    def test_offer_check_suggests_new_tasks_instead_of_starting_them(self):
        # Owner rule 2026-11-22: never start a task the owner didn't ask for (session limits).
        self.assertIn("never start it", selfcheck.offer_problem("If you want, I can also refresh the other regions."))


class PlaybookTriggers(Base):
    """Case 27: a new kind of sub-task started without its playbook (11-17 Chrome, 11-17 keys, 11-18 flutter run)."""
    pre, denied = Gate.pre, Gate.denied
    RUN = ("Bash", {"command": "cd app && flutter run -d emulator-5554 --release"})

    def setUp(self):
        super().setUp()
        (self.kb / "phone-test.md").write_text(
            "keywords: phone\n# Test on the owner's phone\nUse when: x\n"
            "triggers: \\bflutter(?:\\.bat)?\\s+(?:run|install)\\b|\\badb\\b[^\\n]*\\binstall\\b\nverified: x\n\n## Quick steps\n",
            encoding="utf-8")
        (self.kb / "browser.md").write_text("keywords: chrome\n# Drive Chrome by text\ntriggers: ^mcp__claude-in-chrome__\n",
                                            encoding="utf-8")

    def test_first_matching_call_is_sent_back_once_naming_the_playbook(self):
        out = self.pre(*self.RUN)
        self.assertTrue(self.denied(out))
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("phone-test.md", reason)
        self.assertIn("Test on the owner's phone", reason)
        self.assertIsNone(self.pre(*self.RUN))  # the retry passes
        self.assertIsNone(self.pre("Bash", {"command": "adb install -r app.apk"}))  # same playbook: once per session

    def test_an_mcp_call_matches_by_its_name(self):
        self.assertTrue(self.denied(self.pre("mcp__claude-in-chrome__computer", {"action": "left_click", "ref": "r1"})))

    def test_a_playbook_the_session_already_read_passes(self):
        self.write_transcript([assistant(None, "Read", {"file_path": str(self.kb / "phone-test.md")})], mode="a")
        self.assertIsNone(self.pre(*self.RUN))

    def test_the_global_rules_naming_it_do_not_count_as_read(self):
        self.write_transcript([{"type": "user", "message": {"role": "user", "content": "<system-reminder>see phone-test.md"}}],
                              mode="a")
        self.assertTrue(self.denied(self.pre(*self.RUN)))

    def test_writing_text_that_mentions_the_step_passes(self):
        # Replay 2026-11-22: plans, docs and memory notes naming `flutter run` were sent back.
        self.assertIsNone(self.pre("Write", {"file_path": str(self.kb / "plan.md"), "content": "then flutter run on the phone"}))
        self.assertIsNone(self.pre("Edit", {"file_path": "x.md", "old_string": "a", "new_string": "flutter run"}))
        self.assertIsNone(self.pre("Bash", {"command": "cat >> docs/plan.md <<'EOF'\nflutter run on the phone\nEOF"}))

    def test_other_calls_a_broken_trigger_and_the_off_switch_pass(self):
        (self.kb / "broken.md").write_text("# B\ntriggers: (unclosed\n", encoding="utf-8")
        self.assertIsNone(self.pre("Bash", {"command": "flutter test"}))
        self.assertIsNone(self.pre("Bash", {"command": "adb shell dumpsys package x | grep installerPackageName"}))
        (self.kb / "selfcheck-config.json").write_text('{"playbook_triggers": false}', encoding="utf-8")
        self.assertIsNone(self.pre(*self.RUN))


class LogShrink(unittest.TestCase):
    def test_a_log_that_lost_rows_is_reported(self):
        import benchmark_summary
        note = benchmark_summary.shrink_note([{"date": "2026-11-11", "misses_total": "57", "cases": "25"}],
                                             {"date": "2026-11-12", "misses_total": 3, "cases": 2})
        self.assertIn("shrank since 2026-11-11 (misses 57 -> 3, cases 25 -> 2)", note)

    def test_growth_or_no_history_is_quiet(self):
        import benchmark_summary
        self.assertEqual(benchmark_summary.shrink_note([], {"misses_total": 1, "cases": 1}), "")
        self.assertEqual(benchmark_summary.shrink_note([{"date": "d", "misses_total": "3", "cases": "2"}],
                                                       {"misses_total": 4, "cases": 2}), "")

    def test_the_summary_prints_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = pathlib.Path(tmp) / "self-review-log.md"
            log.write_text("## Miss log\n\n| Date | Type |\n|---|---|\n| 2026-10-24 | lapse |\n", encoding="utf-8")
            (pathlib.Path(tmp) / "self-review-history.csv").write_text(
                "date,misses_total,gap,lapse,repeat,misses_last_7_days,cases,global_words,budget_words\n"
                "2026-01-01,9,0,9,0,0,0,0,700\n", encoding="utf-8")
            run = subprocess.run([sys.executable, "-I", str(TOOLS / "benchmark_summary.py"), str(log)],
                                 capture_output=True, env=dict(os.environ, SELFCHECK_KB=tmp), timeout=60)
            self.assertIn("WARNING: the miss log shrank", run.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
