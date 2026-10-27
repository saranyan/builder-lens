"""A made-up builder, for `builder_lens.py --demo`: shows every part of the report without
reading anyone's transcripts. Nothing here comes from a real person or project."""
from .analyze import AXES, USAGE, USAGE_MIN, evidence_catalog


def _t(key, q, value, caption="", conf="K"):
    return {"key": key, "question": q, "value": value, "caption": caption, "conf": conf}


TILES = [
    _t("archetype", "Which kind of builder are you?", "Deep Worker", "81% of work blocks ran over 90 minutes", "G"),
    _t("ship", "How much did you ship?", "48,210 lines", "Across 412 commits and 9 PRs worked.", "I"),
    _t("when", "When are you most productive?", "Night owl", "31% of your commits land late at night.", "G"),
    _t("plan", "How often do you plan first?", "38% of build sessions",
       "23 of 61 sessions that changed code started from a plan — a plan file, plan mode, or a plan written a "
       "session or two earlier.", "I"),
    _t("style", "How do you work with your agent?", "A back-and-forth",
       "You work in dialogue, shaping the work as you go.", "I"),
    _t("longest", "Your longest single session?", "7h 42m", "Your deepest uninterrupted stretch with an agent.", "I"),
    _t("agents", "How many agents do you run?", "3 at once", "As many as 3 main sessions running at the same time."),
    _t("goto", "What's your go-to prompt?", "“ship it”", "You sent it 34 times across 19 sessions."),
    _t("streak", "What's your longest streak?", "12 days straight", "Consecutive days you shipped something."),
    _t("course", "How often do you change course?", "6% of the time",
       "You stop and redirect the agent mid-task rather than letting it run.", "I"),
    _t("crash", "Your biggest crash out?", "“why does the sync STILL dupl…”", "We've all been there.", "G"),
    _t("bigday", "Your biggest day?", "Sunday", "Your single busiest push — 38 commits — landed on a Sunday."),
    _t("length", "How long are your prompts?", "64 words on average", "Mostly conversational prompts.", "I"),
    _t("deep", "How do you work?", "27 deep sessions", "Averaging 148 minutes of uninterrupted focus.", "I"),
    _t("time", "How much time did you put in?", "212 hours", "Across 74 sessions.", "I"),
    _t("cryptic", "Your most cryptic prompt?", "“fix teh pantyr thing”",
       "Somehow the agent knew exactly what you meant.", "G"),
    _t("talk", "How much do you talk to your agent?", "31 prompts a session"),
    _t("mix", "What kind of work is it?", "Mostly features", "96 fixes and 171 features in your commits.", "I"),
]

SIGNALS = {"work_blocks": 88, "deep_share": 0.81, "burst_share": 0.14, "commits_per_active_hour": 1.94,
           "night_commit_share": 0.31, "avg_prompt_words": 64, "prompts": 2294, "active_hours": 212.4,
           "commits": 412, "prs": 9, "redirects": 138, "tools": {"claude_code": 46, "codex_cli": 28}}

WATCH = {"planned_sessions": 23, "unplanned_sessions": 38, "planned_unresolved_per_session": 0.61,
         "unplanned_unresolved_per_session": 1.45, "clean_planned_ships": 9, "conclusive": True}


def _q(repo, ttc, tf, ci, lint, big, conv, rev, cfg):
    return {"repo": repo, "test_to_code": ttc, "test_files": tf, "source_loc": 0, "ci": ci, "docker": False,
            "lint": lint, "files_over_500": big, "conventional_pct": conv, "reverts": rev, "agent_config_words": cfg}


QUALITY = [_q("pantry-app", 0.42, 38, True, True, 4, 71, 3, 1840), _q("shipit-cli", 0.66, 21, True, True, 0, 88, 1, 620),
           _q("pantry-sync", 0.18, 6, False, True, 2, 54, 2, 310), _q("landing-site", 0.0, 0, False, False, 1, 30, 0, 0)]

DECISIONS = {
    "total": 186, "positive": 41, "agent_recognized": 97,
    "by_type": {"strategic_redirect": {"total": 52, "positive": 11}, "technical_catch": {"total": 61, "positive": 17},
                "product_insight": {"total": 44, "positive": 8}, "option_selection": {"total": 29, "positive": 5}},
    "domains": {"debugging": 71, "product": 58, "architecture": 49, "quality": 40, "scope": 22},
    "patterns": [
        {"name": "Catch the State Bug", "count": 14, "examples": ["Offline edits overwrote newer server copies; demanded a version check"]},
        {"name": "Workflow from User Backwards", "count": 11, "examples": ["Started the import flow from what a cook sees on a phone"]},
        {"name": "Full Stop and Investigate", "count": 9,
         "examples": ["Halted the migration until duplicate rows were explained"]},
        {"name": "Kill Dead Complexity", "count": 7, "examples": ["Dropped the plugin system nobody used"]},
        {"name": "Demand Actionable Diagnostics", "count": 6, "examples": ["Sync errors must say which item and why"]},
        {"name": "Codify the Lesson", "count": 4, "examples": ["Turned the dedupe fix into a regression test"]},
    ],
}

USAGE_COUNTS = {"dances_with_robots": 64, "frame_breaker": 18, "cognitive_breadth": 6, "architects_veto": 9}

SCORES = {
    "execution_leverage": (7, 6, 8, "Turned a two-line brief into a working offline mode with tests.", "Long loop on a CSS bug with no repro."),
    "steering": (8, 7, 8, "Stopped a risky migration and asked for the duplicate count first.", "Accepted a vague 'should work now'."),
    "engineering_quality": (6, 5, 7, "Required a regression test for every sync fix.", "Shipped the landing site with no checks."),
    "product_thinking": (7, 6, 8, "Rewrote the import flow around what a cook sees first.", "Built settings nobody asked for."),
    "planning": (6, 4, 7, "Wrote a plan with stop points before the sync rewrite.", "Started a schema change mid-session, unplanned."),
}

SYNTH = {
    "tagline": {"text": "You hunt down state bugs before they ship; next, end each sync change with a regression "
                        "test that reproduces the bug first.", "why": ["pattern.Catch the State Bug", "score.engineering_quality"]},
    "narrative": {"text": "Your strongest work is long, focused sessions where you catch subtle data bugs and "
                          "steer toward what the user actually sees. Next session, write the failing test before "
                          "the fix, so each catch stays caught.",
                  "why": ["card.archetype", "pattern.Catch the State Bug", "score.steering"]},
    "built": {"projects": [{"name": "Pantry", "what": "A recipe and grocery app with offline sync between phone and web."},
                           {"name": "shipit", "what": "A small CLI that tags, builds and publishes releases."},
                           {"name": "pantry-sync", "what": "The sync service that merges offline edits."},
                           {"name": "Landing site", "what": "A static marketing page with a waitlist."}],
              "stack": ["TypeScript", "React Native", "Node.js", "SQLite", "Postgres", "Go", "Vercel"]},
    "strengths": [
        {"title": "Catches state bugs early", "evidence": "You stopped offline edits from overwriting newer copies "
         "and demanded version checks before merging.", "why": ["pattern.Catch the State Bug", "score.steering"]},
        {"title": "Starts from the user", "evidence": "You reshaped the import flow around what a cook sees first.",
         "why": ["pattern.Workflow from User Backwards", "score.product_thinking"]},
        {"title": "Plans the big changes", "evidence": "Your planned sessions finish with fewer open errors.",
         "why": ["watchpoint", "card.plan"]},
    ],
    "growth": [
        {"title": "Make fixes stick", "evidence": "Few decisions end with proof they worked.",
         "try": "For every bug fix, ask the agent for a failing test first, then the fix.", "why": ["decisions.outcomes"]},
        {"title": "Bring tests to every repo", "evidence": "One repo has no tests and no CI.",
         "try": "Add a smoke test and CI to landing-site before the next launch.", "why": ["repo.landing-site"]},
    ],
    "insights": [{"title": "Debugging leads your decisions", "detail": "Debugging is the area you decide on most.",
                  "try": "Keep a short log of root causes; repeated ones point at missing tests.", "why": ["domain.debugging"]}],
}

SKILL = {
    "rules": [
        {"text": "Before any sync or schema change, write a short plan with the steps and a stop point, and wait for approval.", "why": ["watchpoint", "card.plan"]},
        {"text": "For every bug fix, write a failing test that reproduces it first, show it failing, then fix it.", "why": ["pattern.Catch the State Bug", "decisions.outcomes"]},
        {"text": "When data could be overwritten or duplicated, stop and report counts before changing anything.", "why": ["pattern.Full Stop and Investigate"]},
        {"text": "Describe UI changes from what the user sees first, not from the code.", "why": ["pattern.Workflow from User Backwards"]},
        {"text": "Make every error message say which item failed and why.", "why": ["pattern.Demand Actionable Diagnostics"]},
    ],
    "avoid": [
        {"text": "Don't say a fix works without showing the test output.", "why": ["decisions.outcomes"]},
        {"text": "Don't add options or settings that weren't asked for.", "why": ["pattern.Kill Dead Complexity"]},
    ],
    "communication": [
        {"text": "“ship it” is their usual approval: proceed with the step you just proposed.", "why": ["card.goto"]},
        {"text": "Prompts are conversational: answer inline and ask at most one question per turn.", "why": ["card.length"]},
    ],
}


def data():
    d = {"header": {"scope": "All projects (4 repos)", "sessions": 74, "sessions_analyzed": 74, "date": "Oct 27, 2026",
                    "excluded": {"automated": 212, "subagent": 40}},
         "tiles": TILES, "watchpoint": WATCH, "quality": QUALITY, "signals": SIGNALS}
    usage_all = [{"key": k, "name": USAGE[k][0], "gloss": USAGE[k][1], "count": USAGE_COUNTS[k],
                  "shown": USAGE_COUNTS[k] >= USAGE_MIN} for k in USAGE]
    scores = {a: {"median": m, "p25": lo, "p75": hi, "n": 58, "high": {"score": 9, "note": best},
                  "low": {"score": 3, "note": worst}} for a, (m, lo, hi, best, worst) in SCORES.items()}
    agg = {"decisions": DECISIONS, "usage": [u for u in usage_all if u["shown"]], "usage_all": usage_all,
           "breadth_sample": 10, "scores": {a: scores[a] for a in AXES}}
    cat = evidence_catalog(d, agg)
    facts = lambda x: dict(x, why=[cat[i] for i in x["why"] if i in cat])
    synth = dict(SYNTH, tagline=facts(SYNTH["tagline"]), narrative=facts(SYNTH["narrative"]),
                 strengths=[facts(x) for x in SYNTH["strengths"]], growth=[facts(x) for x in SYNTH["growth"]],
                 insights=[facts(x) for x in SYNTH["insights"]])
    skill = {k: [facts(x) for x in v] for k, v in SKILL.items()}
    d["llm"] = dict(agg, backend="demo data", synthesis=synth, skill=skill, segments=[],
                    calls={"segments": 58, "ok": 58, "cached": 0, "called": 0, "failed": 0, "last_error": ""})
    return d
