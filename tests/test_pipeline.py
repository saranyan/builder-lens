"""End-to-end tests on synthetic transcripts + a throwaway git repo. Stdlib only:
`python3 -m unittest discover -s tests`. Never touches the developer's real ~/.claude or ~/.codex."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from builderlens import analyze, gitdata, llm, metrics, redact, report, sources  # noqa: E402

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def iso(minutes):
    return (T0 + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("\n".join(json.dumps(r) for r in rows) + "\n")


def claude_user(m, text, cwd, **kw):
    return dict({"type": "user", "timestamp": iso(m), "cwd": cwd, "entrypoint": "cli",
                 "message": {"role": "user", "content": text}}, **kw)


def claude_tool(m, tid, name, inp, cwd):
    return {"type": "assistant", "timestamp": iso(m), "cwd": cwd,
            "message": {"role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def claude_result(m, tid, error, cwd):
    return {"type": "user", "timestamp": iso(m), "cwd": cwd, "entrypoint": "cli",
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "is_error": error}]}}


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="blens-test-")
        cls.repo = os.path.join(cls.tmp, "demo-repo")
        os.makedirs(cls.repo)
        g = lambda *a, **env: subprocess.run(["git", "-C", cls.repo, *a], check=True, capture_output=True,
                                             env=dict(os.environ, **env))
        g("init", "-q")
        g("config", "user.email", "me@example.com")
        g("config", "user.name", "Me")
        for i, (msg, m) in enumerate([("feat: add parser", 30), ("fix: handle empty input", 60),
                                      ("feat: report page", 150)]):
            with open(os.path.join(cls.repo, f"f{i}.py"), "w") as fh:
                fh.write("x = 1\n" * (10 + i))
            g("add", ".")
            g("commit", "-qm", msg, GIT_AUTHOR_DATE=iso(m), GIT_COMMITTER_DATE=iso(m))
        cls.repo = gitdata.toplevel(cls.repo)          # resolve /private symlinks on macOS

        cl = os.path.join(cls.tmp, "claude", "proj")
        r = cls.repo
        write_jsonl(os.path.join(cl, "s1.jsonl"), [
            claude_user(0, "write the plan to docs/plan.md then build it", r, permissionMode="plan"),
            claude_tool(1, "t1", "Write", {"file_path": f"{r}/docs/plan.md"}, r),
            claude_tool(5, "t2", "Edit", {"file_path": f"{r}/f0.py"}, r),
            claude_tool(6, "t3", "Bash", {"command": "pytest -q"}, r),
            claude_result(7, "t3", True, r),
            claude_user(20, "thanks! continue", r),
            claude_tool(25, "t4", "Bash", {"command": "pytest -q"}, r),
            claude_result(26, "t4", False, r),
            claude_user(40, "continue", r),
            claude_user(45, "why is it STILL BROKEN AGAIN??", r),
            claude_user(50, "[Request interrupted by user]", r),
            claude_user(140, "continue", r),
            claude_tool(141, "t5", "Edit", {"file_path": f"{r}/f2.py"}, r),
        ])
        write_jsonl(os.path.join(cl, "auto.jsonl"), [
            claude_user(0, "Reply with OK", r, entrypoint="sdk-cli", promptSource="sdk"),
        ])
        cx = os.path.join(cls.tmp, "codex", "2026", "10", "01")
        write_jsonl(os.path.join(cx, "rollout-a.jsonl"), [
            {"type": "session_meta", "timestamp": iso(200), "payload": {"id": "cx1", "cwd": r, "originator": "codex-tui", "source": "cli"}},
            {"type": "response_item", "timestamp": iso(201), "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context>x</environment_context>"}]}},
            {"type": "response_item", "timestamp": iso(202), "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "continue"}]}},
            {"type": "response_item", "timestamp": iso(203), "payload": {"type": "custom_tool_call", "name": "exec", "call_id": "c1",
                                                                         "input": 'text(await tools.apply_patch("*** Begin Patch\\n*** Update File: f1.py\\n"))'}},
            {"type": "response_item", "timestamp": iso(204), "payload": {"type": "custom_tool_call_output", "call_id": "c1", "output": "Script failed\n"}},
            {"type": "event_msg", "timestamp": iso(205), "payload": {"type": "turn_aborted", "reason": "interrupted"}},
        ])
        write_jsonl(os.path.join(cx, "rollout-b.jsonl"), [
            {"type": "session_meta", "timestamp": iso(300), "payload": {"id": "cx2", "cwd": r, "originator": "codex_exec", "source": "exec"}},
            {"type": "response_item", "timestamp": iso(301), "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "summarize"}]}},
        ])
        cls.claude_root, cls.codex_root = os.path.join(cls.tmp, "claude"), os.path.join(cls.tmp, "codex")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def load(self, **kw):
        ss, st = sources.discover_all(claude_root=self.claude_root, codex_root=self.codex_root, **kw)
        for s in ss:
            s.repo = gitdata.toplevel(s.cwd)
        return ss, st


class TestParsing(Fixture):
    def test_automated_excluded_by_default(self):
        ss, st = self.load()
        self.assertEqual(st["automated"], 2)
        self.assertEqual({s.tool for s in ss}, {"claude_code", "codex_cli"})
        ss2, _ = self.load(include_automated=True)
        self.assertEqual(len(ss2), len(ss) + 2)

    def test_claude_session_fields(self):
        s = next(s for s in self.load()[0] if s.tool == "claude_code")
        self.assertEqual(len(s.prompts), 5)                       # interrupt marker isn't a prompt
        self.assertEqual(s.interrupts, 1)
        self.assertTrue(s.plan_mode)
        self.assertEqual(len(s.edits), 3)                         # Write + 2 Edit
        self.assertEqual([c.error for c in s.calls if c.kind == "shell"], [True, False])

    def test_codex_session_fields(self):
        s = next(s for s in self.load()[0] if s.tool == "codex_cli")
        self.assertEqual([p.text for p in s.prompts], ["continue"])   # injected context dropped
        self.assertEqual(s.edits[0].paths, ["f1.py"])
        self.assertTrue(s.edits[0].error)
        self.assertEqual(s.interrupts, 1)


class TestMetrics(Fixture):
    def compute(self):
        ss, st = self.load()
        commits = gitdata.author_commits(self.repo, {"me@example.com"}, ss[0].start, max(s.end for s in ss))
        hdr = {"scope": "demo-repo", "sessions": len(ss), "date": "Oct 1, 2026", "excluded": st}
        return metrics.compute(ss, commits, [], hdr), commits

    def test_tiles(self):
        d, commits = self.compute()
        self.assertEqual(len(commits), 3)
        t = {x["key"]: x for x in d["tiles"]}
        self.assertEqual(d["tiles"][0]["key"], "archetype")
        self.assertEqual(t["ship"]["value"], f"{sum(c.added + c.deleted for c in commits):,} lines")
        self.assertEqual(t["goto"]["value"], "“continue”")
        self.assertIn("3 times across 2 sessions", t["goto"]["caption"])   # "thanks! continue" is a different prompt
        self.assertEqual(t["mix"]["caption"] if "mix" in t else None, None)    # < 5 classified commits: hidden
        self.assertIn("3 commits", t["bigday"]["caption"])                     # all on Oct 1
        self.assertTrue(t["crash"]["value"].startswith("“why is it STILL"))
        self.assertEqual(t["plan"]["value"], "100% of build sessions")         # codex one inherits the earlier plan
        self.assertEqual(t["longest"]["value"], "2h 21m")

    def test_unresolved_errors(self):
        d, _ = self.compute()
        w = d["watchpoint"]
        # claude: pytest error at m6 resolved by passing pytest at m25 → 0; codex: patch error, no fix → 1
        self.assertEqual((w["planned_sessions"], w["planned_unresolved_per_session"]), (2, 0.5))
        self.assertFalse(w["conclusive"])

    def test_longest_session_capped_at_16h(self):
        s = sources.Session(id="x", tool="claude_code", path="")
        s.times = [T0, T0 + timedelta(days=3)]
        self.assertEqual(metrics.session_timing(s)["span"], timedelta(hours=16))

    def test_report_escapes_user_text(self):
        d, _ = self.compute()
        d["tiles"].append({"key": "x", "question": "q", "value": "<script>alert(1)</script>", "caption": "", "conf": "K"})
        out = tempfile.mkdtemp(dir=self.tmp)
        with open(report.render(d, out), encoding="utf-8") as fh:
            html = fh.read()
        self.assertNotIn("<script>alert(1)", html)
        self.assertIn("&lt;script&gt;", html)


FAKE_SEGMENT = {
    "title": "Parser and report", "summary": "Built a parser.", "project": "demo", "domain": "dev tool",
    "stack": ["Python", 7, ""],
    "decisions": [
        {"turn": 3, "type": "technical_catch", "domains": ["debugging", "bogus"], "pattern": "Full Stop and Investigate",
         "agent_recognized": True, "outcome": "positive", "outcome_evidence": "pytest passed after",
         "evidence": "stopped to find the root cause"},
        {"turn": 4, "type": "option_selection", "domains": ["scope"], "outcome": "positive", "evidence": "no proof"},
        {"turn": 1, "type": "made_up", "domains": [], "outcome": "positive"},
        {"turn": 2, "type": "product_insight", "domains": ["product"], "pattern": "Not A Real Pattern",
         "agent_recognized": False, "outcome": "weird", "evidence": "users need a summary first"},
    ],
    "usage": {"dances_with_robots": 3, "frame_breaker": "2", "architects_veto": None, "cognitive_breadth": True},
    "scores": {"execution_leverage": {"score": 14, "note": "lots shipped"}, "steering": 6, "planning": {"score": "x"}},
}
FAKE_SYNTH = {"tagline": {"text": "You ship fast; next, add tests.", "why": ["card.ship", "made.up"]},
              "narrative": {"text": "Strong <b>loop</b>.", "why": ["not.an.id"]},
              "built": {"projects": [{"name": "demo", "what": "a parser"}], "stack": ["Python"]},
              "strengths": [{"title": "Fast", "evidence": "a fast loop", "why": ["card.streak"]}] * 4
                           + [{"title": "Misquoted", "evidence": "99 commits", "why": ["card.streak"]}]
                           + [{"title": "Unbacked", "evidence": "trust me", "why": []}],
              "growth": [{"title": "Plan", "evidence": "planned sessions are rare", "try": "write plan.md", "why": "watchpoint"}],
              "insights": []}


class TestLLMStage(Fixture):
    def fake(self, calls):
        def run(prompt):
            calls.append(prompt)
            body = FAKE_SYNTH if prompt.lstrip().startswith("You are writing") else FAKE_SEGMENT
            return "Sure! ```json\n" + json.dumps(body) + "\n```"
        return run

    def test_redaction(self):
        r = redact.redact("key sk-ant-abcdefghijklmnopqrstuv mail me@x.io token=hunter2abc ok "
                          + os.path.expanduser("~") + "/code")
        for leak in ("sk-ant-abc", "me@x.io", "hunter2abc", os.path.expanduser("~") + "/"):
            self.assertNotIn(leak, r)
        self.assertIn("~/code", r)

    def test_segments_cap_and_redact(self):
        s = sources.Session(id="big", tool="claude_code", path="", repo=self.repo)
        s.prompts = [sources.Prompt(T0 + timedelta(minutes=i), f"step {i} " + "x" * 2000 + " a@b.co",
                                    context="agent said hi")
                     for i in range(400)]
        s.times = [p.ts for p in s.prompts]
        segs = analyze.segments(s)
        self.assertEqual(len(segs), analyze.MAX_SEGMENTS)
        thin = [({"session": "x", "prompts": 1}, {"decisions": [], "usage": {"dances_with_robots": 0, "frame_breaker": 0,
                  "architects_veto": 0, "cognitive_breadth": False}, "scores": {"planning": {"score": 0, "note": "exit"}}})]
        self.assertEqual(analyze.aggregate(thin)["scores"], {})          # too thin to score
        self.assertTrue(all(len(g["text"]) < analyze.SEG_CHARS + 2000 for g in segs))
        self.assertIn("evenly spaced", segs[0]["text"])
        self.assertNotIn("a@b.co", segs[0]["text"])
        self.assertIn("[0] AGENT: …agent said hi", segs[0]["text"])

    def test_stage_cleans_aggregates_and_caches(self):
        ss, st = self.load()
        commits = gitdata.author_commits(self.repo, {"me@example.com"}, ss[0].start, max(s.end for s in ss))
        hdr = {"scope": "demo-repo", "sessions": len(ss), "date": "Oct 1, 2026", "excluded": st}
        data = metrics.compute(ss, commits, [], hdr)
        calls, cache = [], tempfile.mkdtemp(dir=self.tmp)
        L = analyze.run(llm.LLM("claude", cache_dir=cache, run=self.fake(calls)), ss, data, workers=2, log=lambda *_: None)
        self.assertEqual(L["calls"]["ok"], 2)
        self.assertEqual(len(calls), 3)                               # 2 segments + synthesis
        d = L["decisions"]
        self.assertEqual(d["total"], 6)                               # invalid type dropped, 3 per segment
        self.assertEqual(d["positive"], 2)                            # unproven "positive" and "weird" → unknown
        self.assertEqual(d["domains"], {"debugging": 2, "product": 2, "scope": 2})
        self.assertEqual([p["name"] for p in d["patterns"]], ["Full Stop and Investigate"])
        self.assertEqual({u["name"]: u["count"] for u in L["usage"]},
                         {"Dances with Robots": 6, "Frame Breaker": 4, "Cognitive Breadth": 2})   # per session
        self.assertEqual(L["scores"]["execution_leverage"]["median"], 10)   # clamped
        self.assertEqual(L["scores"]["steering"]["median"], 6)               # bare number accepted
        self.assertNotIn("planning", L["scores"])
        syn = L["synthesis"]
        self.assertEqual(len(syn["strengths"]), 3)                     # capped; the unbacked one is dropped
        self.assertNotIn("Unbacked", [x["title"] for x in syn["strengths"]])
        self.assertEqual(len(syn["tagline"]["why"]), 1)                # invented id dropped, real one kept
        self.assertIn("How much did you ship?", syn["tagline"]["why"][0])
        self.assertIn("Unresolved errors per session", syn["growth"][0]["why"][0])
        L2 = analyze.run(llm.LLM("claude", cache_dir=cache, run=self.fake(calls)), ss, data, workers=2, log=lambda *_: None)
        self.assertEqual((len(calls), L2["calls"]["cached"]), (3, 3))       # all from cache
        data["llm"] = L
        out = tempfile.mkdtemp(dir=self.tmp)
        with open(report.render(data, out), encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn("You ship fast; next, add tests.", html)
        self.assertIn('role="tooltip"', html)
        self.assertIn("How it's measured", html)                  # every card has a back
        self.assertIsNone(L["synthesis"]["narrative"])            # cites a number not in the input → dropped
        self.assertNotIn("Strong", html)
        self.assertIn("Full Stop and Investigate", html)
        self.assertNotIn("Not run: the LLM stage", html)

    def test_claims_need_real_evidence_ids(self):
        cat = {"card.ship": "How much did you ship? 10 lines."}
        self.assertEqual(analyze.verified_claim({"text": "t", "why": ["card.ship", "x"]}, cat)["why"],
                         ["How much did you ship? 10 lines."])
        self.assertIsNone(analyze.verified_claim({"text": "t", "why": ["x"]}, cat))
        self.assertIsNone(analyze.verified_claim({"text": "t", "why": "you seem careful"}, cat))
        self.assertIsNone(analyze.verified_claim("plain string", cat))
        self.assertIsNone(analyze.verified_claim({"text": "you shipped 11 lines", "why": ["card.ship"]}, cat))
        self.assertIsNotNone(analyze.verified_claim({"text": "10 lines; next, a 3-line plan", "why": ["card.ship"]}, cat))

    def test_product_thinker(self):
        agg = {"decisions": {"total": 20, "by_type": {"product_insight": {"total": 9}}, "domains": {"product": 18}}}
        self.assertAlmostEqual(analyze.product_thinker(agg), 0.45)
        agg["decisions"]["by_type"]["product_insight"]["total"] = 6     # product *domain* share doesn't count
        self.assertIsNone(analyze.product_thinker(agg))

    def test_breadth_counted_over_fixed_session_sample(self):
        res = [({"session": f"s{i // 2}"}, {"decisions": [], "scores": {},
                 "usage": {"dances_with_robots": 0, "frame_breaker": 0, "architects_veto": 0, "cognitive_breadth": True}})
               for i in range(60)]                                    # 30 sessions, 2 segments each
        u = {x["name"]: x["count"] for x in analyze.aggregate(res)["usage"]}
        self.assertEqual(u["Cognitive Breadth"], analyze.BREADTH_SAMPLE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
