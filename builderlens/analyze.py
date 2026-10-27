"""The LLM stage: per-segment analysis, then one synthesis call.

A *segment* is a whole session, or a contiguous time-slice of a long one, sized to fit one
prompt. Segments are the unit Paxel calls an episode: each gets a summary, its decision
exchanges, "How you use AI" evidence and the five hidden axis scores. Very long sessions are
sampled down to MAX_SEGMENTS evenly spaced slices, so one months-long session can't dominate
the cost or the report.
"""
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

from .redact import redact

SEG_CHARS = 24_000
MAX_SEGMENTS = 8            # per session
AGENT_CLIP, DEV_CLIP = 300, 900
SYNTH_SEGMENTS = 120        # summaries passed to the synthesis call
SCORE_MIN_PROMPTS = 3       # segments thinner than this ("exit", one probe) aren't scored

TYPES = ("strategic_redirect", "technical_catch", "product_insight", "option_selection")
DOMAINS = ("architecture", "debugging", "product", "scope", "quality")
OUTCOMES = ("positive", "mixed", "negative", "unknown")
AXES = ("execution_leverage", "steering", "engineering_quality", "product_thinking", "planning")
PATTERNS = (
    "Workflow from User Backwards", "Enforce Safety Rails", "Challenge the Constraint", "Audit Completeness",
    "Catch the State Bug", "Full Stop and Investigate", "Scope Unbundling", "Demand Full Observability",
    "Resist False Simplicity", "Kill Dead Complexity", "Codify the Lesson", "Reference the Working Version",
    "Instant Feedback or Broken", "Reject Lazy Workaround", "Trace the Stale Data", "Follow the Reference Product",
    "Demand Actionable Diagnostics", "Collapse Unnecessary Steps", "Trace the Input", "Name the Copy",
    "Respect the Persona", "Correct the Tool Choice",
)
USAGE = {
    "dances_with_robots": ("Dances with Robots", "Riffs with the AI like a jam session. Ideas bounce back and forth."),
    "frame_breaker": ("Frame Breaker", "Refuses the menu. Rewrites the question before answering it."),
    "cognitive_breadth": ("Cognitive Breadth", "Thinks across product, code, scope, and process in a single session."),
    "architects_veto": ("Architect's Veto", "Kills clever solutions that won't survive next quarter."),
}
USAGE_MIN = 2
# [I] Cognitive Breadth reads 5–7 on every Paxel report regardless of corpus size (12 to 4,741
# sessions), so it's counted over a fixed sample of sessions rather than the whole corpus.
BREADTH_SAMPLE = 10
PRODUCT_SHARE, PRODUCT_MIN = 0.40, 10        # [G] Product Thinker: share of decisions typed product_insight

SEGMENT_PROMPT = """
You are analyzing one segment of a developer's session with an AI coding agent. The input has a
header of measured facts, then numbered turns: AGENT is the tail of the agent's previous message,
DEV is what the developer typed next. You have no tools; use only this text.

1. Summarize what was worked on and how the developer steered.
2. Find DECISION EXCHANGES: developer turns that make a real call about the work — redirect the
   approach (strategic_redirect), catch an agent mistake or bad assumption (technical_catch), add a
   product/user requirement (product_insight), or pick between options the agent offered
   (option_selection). Plain "continue", "yes", "go ahead" are not decisions unless they choose
   among options. Tag each with 1-2 domains. If it matches one of the named patterns below, give
   that name, else null.
   Outcome defaults to "unknown". Use "positive" ONLY when the text shows proof that the decision
   worked: a later turn where tests or a check visibly pass, a commit in the header that matches
   it, or the developer saying it works. Put that proof in outcome_evidence. A plausible or
   agreed-with decision with no such proof is "unknown". "negative" if it visibly failed or was
   reverted; "mixed" if both. Most decisions should be "unknown".
   agent_recognized = true ONLY if a later AGENT excerpt explicitly names the decision and changes
   course because of it; agreeing ("Sure", "Got it") is not enough, and if no later AGENT text
   covers it, use false.
3. Count "How you use AI" evidence: dances_with_robots = turns that riff on or build on the
   agent's ideas; frame_breaker = turns that reject the options offered and reframe the problem;
   architects_veto = turns that kill a clever but fragile solution for long-term reasons;
   cognitive_breadth = true if the developer moves across product, code, scope AND process here.
4. Score five axes 0-10 (5 = typical competent builder, 8+ = rare, clear evidence), each with a
   one-sentence note citing the evidence:
   execution_leverage (how much working output the developer gets per unit of steering),
   steering (quality of direction and corrections), engineering_quality (testing, verification,
   code health), product_thinking (user/product reasoning), planning (thinking before building).

Named patterns: {patterns}

Never quote secrets, names of people, or emails. Reply with ONLY this JSON object:
{{"title": "<=8 words",
 "summary": "2-4 sentences",
 "project": "product or project name as it appears, else the repo name",
 "domain": "what kind of product, e.g. 'fintech API' or 'browser extension'",
 "stack": ["languages, frameworks, services actually seen"],
 "decisions": [{{"turn": 0, "type": "strategic_redirect|technical_catch|product_insight|option_selection",
   "domains": ["architecture|debugging|product|scope|quality"], "pattern": null,
   "agent_recognized": false, "outcome": "unknown|positive|mixed|negative", "outcome_evidence": "",
   "evidence": "<=20 words: what the developer decided"}}],
 "usage": {{"dances_with_robots": 0, "frame_breaker": 0, "architects_veto": 0, "cognitive_breadth": false}},
 "scores": {{"execution_leverage": {{"score": 5, "note": "..."}}, "steering": {{"score": 5, "note": "..."}},
   "engineering_quality": {{"score": 5, "note": "..."}}, "product_thinking": {{"score": 5, "note": "..."}},
   "planning": {{"score": 5, "note": "..."}}}}}}
""".format(patterns="; ".join(PATTERNS))

SYNTH_PROMPT = """
You are writing the qualitative half of a builder profile: how one developer builds software with
AI coding agents. The input is JSON: measured stats, the planning watchpoint, repo health,
per-segment summaries, aggregated decision exchanges, "How you use AI" counts and five axis scores.
You have no tools; ground every claim in the input and cite numbers. Be specific and honest:
name real weaknesses, not just strengths. Second person. Plain text, no markdown. Never name
people or quote secrets.

Rules:
- tagline.text: one sentence, "You <specific strength>; next, <one concrete action for the next session>."
  The action must be something they can do tomorrow (e.g. "write a 3-line plan file before
  multi-repo builds"), never a trait like "plan more" or "verify claims".
- narrative.text: 1-2 sentences on where they're strongest and the same kind of concrete action.
- Every number you write in text, evidence or detail must appear in the facts you cite in "why";
  claims that quote a number their cited facts don't contain are discarded.
- "why" is a list of 1-4 ids from the input's "evidence" object: the measured facts that support
  the claim. Use only ids that exist there, and only facts that actually support that claim. The
  reader sees the facts verbatim on hover, so a claim the cited facts don't support will look
  wrong. If no evidence id supports a claim, leave that claim out.
- built.projects: the distinct products/projects they worked on (merge duplicates, at most 8),
  each with one line on what it is. built.stack: languages, frameworks and services seen.
- strengths: up to 3, each with evidence (examples from the segments) and "why" evidence ids.
- growth: 2-3, each with evidence, "why" evidence ids, and a concrete rule or checkpoint to try.
  If the planning watchpoint is inconclusive, say so rather than claiming planning helps or hurts.
- insights: 0-2 observations about their decision patterns not covered above, each with "why"
  evidence ids and a concrete thing to try. No speculation about causes the evidence can't show.

Reply with ONLY this JSON object:
{"tagline": {"text": "...", "why": ["evidence id", "..."]},
 "narrative": {"text": "...", "why": ["evidence id"]},
 "built": {"projects": [{"name": "...", "what": "..."}], "stack": ["..."]},
 "strengths": [{"title": "<=6 words", "evidence": "1-2 sentences", "why": ["evidence id"]}],
 "growth": [{"title": "<=6 words", "evidence": "1-2 sentences", "try": "one concrete rule", "why": ["evidence id"]}],
 "insights": [{"title": "<=6 words", "detail": "1 sentence", "try": "one concrete action", "why": ["evidence id"]}]}
"""


SKILL_PROMPT = """
You are writing a working-style guide for AI coding agents (Claude Code, Codex) that will work
with one developer. The input is JSON: an "evidence" object of measured facts about how this
developer actually works, plus the strengths, growth areas and decision patterns already found.
You have no tools; use only the input.

Write instructions TO THE AGENT, in the imperative ("Before X, do Y"). Each must name a concrete
trigger and a concrete action the agent can take inside a session. Prefer rules that support the
developer's growth areas (e.g. prompt for the plan they tend to skip, show verification output
before claiming done) and that fit how they already steer (their decision patterns). No generic
advice that would apply to anyone ("write clean code", "be helpful").

Rules:
- rules: 5-8 things the agent should do.
- avoid: 2-4 things the agent should not do with this developer.
- communication: 2-4 notes on how to talk with them (prompt length, how they approve, how often
  they redirect), each grounded in the evidence.
- Every item has "why": 1-3 ids from the input's "evidence" object that justify it. Every number
  you write must appear in the facts you cite. Items without real evidence are discarded.
- Plain text, no markdown, no names of people, no secrets.

Reply with ONLY this JSON object:
{"rules": [{"text": "...", "why": ["evidence id"]}],
 "avoid": [{"text": "...", "why": ["evidence id"]}],
 "communication": [{"text": "...", "why": ["evidence id"]}]}
"""


def _skill_input(agg, synth, catalog):
    syn = synth or {}
    return redact(json.dumps({
        "evidence": catalog,
        "strengths": [{"title": x["title"], "evidence": x["evidence"]} for x in syn.get("strengths") or []],
        "growth_areas": [{"title": x["title"], "evidence": x["evidence"], "try": x["try"]} for x in syn.get("growth") or []],
        "decision_patterns": [{"name": p["name"], "count": p["count"], "examples": p["examples"]}
                              for p in agg["decisions"]["patterns"][:10]],
    }, indent=1))


def clean_skill(r, catalog):
    """Keep only agent instructions that cite real evidence and quote no number they can't back."""
    if not r:
        return None
    out = {}
    for k, n in (("rules", 8), ("avoid", 4), ("communication", 4)):
        items = []
        for x in r.get(k) or [] if isinstance(r.get(k), list) else []:
            if not isinstance(x, dict):
                continue
            text, why = _str(x.get("text"), 400), cited(x.get("why"), catalog)
            if text and why and numbers_backed(text, why):
                items.append({"text": text, "why": why})
        out[k] = items[:n]
    return out if out["rules"] else None


# ============================================================================== segmenting

def _clip(text, n):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _local(ts):
    return ts.astimezone().strftime("%Y-%m-%d %H:%M")


def segments(s):
    """Split one session into prompt-sized segments: [{session, index, of, start, end, text}]."""
    turns = []
    for i, p in enumerate(s.prompts):
        t = f"[{i}] DEV{' (typed mid-turn)' if p.queued else ''}: {_clip(p.text, DEV_CLIP)}"
        if p.context:
            t = f"[{i}] AGENT: …{_clip(p.context, AGENT_CLIP)}\n" + t
        turns.append((p.ts, t))
    if not turns:
        return []
    chunks, cur, size = [], [], 0
    for ts, t in turns:
        if cur and size + len(t) > SEG_CHARS:
            chunks.append(cur)
            cur, size = [], 0
        cur.append((ts, t))
        size += len(t) + 1
    chunks.append(cur)
    total = len(chunks)
    if total > MAX_SEGMENTS:
        picks = sorted({round(k * (total - 1) / (MAX_SEGMENTS - 1)) for k in range(MAX_SEGMENTS)})
        chunks = [chunks[k] for k in picks]
    else:
        picks = list(range(total))

    repo = os.path.basename(s.repo or s.cwd) or "unknown"
    out = []
    for n, (k, chunk) in enumerate(zip(picks, chunks)):
        start = chunk[0][0]
        nxt = chunks[n + 1][0][0] if n + 1 < len(chunks) else None
        end = s.end if nxt is None else nxt
        inside = lambda ts: start <= ts < end or (nxt is None and ts == end)
        files = Counter(os.path.relpath(p, s.repo) if s.repo and os.path.isabs(p) else p
                        for c in s.calls if c.kind == "edit" and inside(c.ts) for p in c.paths)
        errs = sum(1 for c in s.calls if c.error and inside(c.ts))
        commits = [c for c in s.commits if inside(c.ts)]
        head = [
            f"Agent: {s.tool} · repo: {repo} · segment {k + 1} of {total}"
            + (f" (only {len(chunks)} evenly spaced segments of this long session are analyzed)" if total > len(chunks) else ""),
            f"Window: {_local(start)} → {_local(end)} (developer's local time)",
            f"Developer prompts in this segment: {len(chunk)} · session interrupts: {s.interrupts}"
            f" · plan mode used in session: {'yes' if s.plan_mode else 'no'}",
            f"Tool/shell errors in this window: {errs}",
            "Files edited (most-touched first): " + (", ".join(f for f, _ in files.most_common(15)) or "none"),
            f"Commits landed in this window: {len(commits)}",
        ] + [f"  - {_clip(c.subject, 120)} (+{c.added}/-{c.deleted})" for c in commits[:25]]
        text = "\n".join(head) + "\n\nTURNS:\n" + "\n".join(t for _, t in chunk)
        out.append({"session": s.id, "tool": s.tool, "repo": repo, "index": k, "of": total,
                    "start": start.isoformat(), "end": end.isoformat(), "commits": len(commits), "prompts": len(chunk),
                    "text": redact(text)})
    return out


# ============================================================================== normalizing

def _num(x, lo=0, hi=10):
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return None


def _str(x, n=400):
    return _clip(str(x), n) if isinstance(x, (str, int, float)) and str(x).strip() else ""


def clean_segment(r):
    """Coerce one segment reply into the schema; drop anything malformed rather than failing."""
    decisions = []
    for d in r.get("decisions") or []:
        if not isinstance(d, dict) or d.get("type") not in TYPES:
            continue
        doms = [x for x in (d.get("domains") or []) if x in DOMAINS] if isinstance(d.get("domains"), list) else []
        decisions.append({
            "type": d["type"], "domains": doms[:2],
            "pattern": d.get("pattern") if d.get("pattern") in PATTERNS else None,
            "agent_recognized": bool(d.get("agent_recognized")),
            "outcome": (d.get("outcome") if d.get("outcome") in OUTCOMES else "unknown")
            if d.get("outcome") != "positive" or _str(d.get("outcome_evidence")) else "unknown",
            "outcome_evidence": _str(d.get("outcome_evidence"), 200),
            "evidence": _str(d.get("evidence"), 200),
        })
    u = r.get("usage") if isinstance(r.get("usage"), dict) else {}
    usage = {k: int(_num(u.get(k), 0, 500) or 0) for k in ("dances_with_robots", "frame_breaker", "architects_veto")}
    usage["cognitive_breadth"] = u.get("cognitive_breadth") is True
    scores = {}
    sc = r.get("scores") if isinstance(r.get("scores"), dict) else {}
    for a in AXES:
        v = sc.get(a)
        v = v if isinstance(v, dict) else {"score": v}
        n = _num(v.get("score"))
        if n is not None:
            scores[a] = {"score": n, "note": _str(v.get("note"), 300)}
    stack = [_str(x, 40) for x in r.get("stack") or [] if _str(x, 40)] if isinstance(r.get("stack"), list) else []
    return {"title": _str(r.get("title"), 80), "summary": _str(r.get("summary"), 700),
            "project": _str(r.get("project"), 60), "domain": _str(r.get("domain"), 80), "stack": stack[:15],
            "decisions": decisions, "usage": usage, "scores": scores}


# ============================================================================== aggregating

def aggregate(results):
    """results: [(segment_meta, cleaned_reply)] → decision/usage/score rollups."""
    decs = [d for _, r in results for d in r["decisions"]]
    by_type = {t: {"total": 0, "positive": 0} for t in TYPES}
    for d in decs:
        by_type[d["type"]]["total"] += 1
        by_type[d["type"]]["positive"] += d["outcome"] == "positive"
    domains = Counter(x for d in decs for x in d["domains"])
    patterns = Counter(d["pattern"] for d in decs if d["pattern"])
    examples = defaultdict(list)
    for d in decs:
        if d["pattern"] and d["evidence"] and len(examples[d["pattern"]]) < 2:
            examples[d["pattern"]].append(d["evidence"])
    usage = Counter()
    broad = defaultdict(bool)
    for m, r in results:
        for k in ("dances_with_robots", "frame_breaker", "architects_veto"):
            usage[k] += r["usage"][k]
        broad[m["session"]] |= r["usage"]["cognitive_breadth"]
    sess = list(broad)                                     # results are in session start order
    if len(sess) > BREADTH_SAMPLE:
        sess = [sess[round(k * (len(sess) - 1) / (BREADTH_SAMPLE - 1))] for k in range(BREADTH_SAMPLE)]
    usage["cognitive_breadth"] = sum(broad[x] for x in sess)
    scores = {}
    for a in AXES:
        rows = [(r["scores"][a]["score"], r["scores"][a]["note"], m) for m, r in results
                if a in r["scores"] and m.get("prompts", SCORE_MIN_PROMPTS) >= SCORE_MIN_PROMPTS]
        if not rows:
            continue
        vals = sorted(v for v, _, _ in rows)
        q = statistics.quantiles(vals, n=4) if len(vals) >= 4 else [vals[0], statistics.median(vals), vals[-1]]
        lo_note = min(rows, key=lambda x: x[0])
        hi_note = max(rows, key=lambda x: x[0])
        scores[a] = {"median": round(statistics.median(vals), 1), "p25": round(q[0], 1), "p75": round(q[-1], 1),
                     "n": len(vals), "high": {"score": hi_note[0], "note": hi_note[1]},
                     "low": {"score": lo_note[0], "note": lo_note[1]}}
    return {
        "decisions": {"total": len(decs), "positive": sum(d["outcome"] == "positive" for d in decs),
                      "agent_recognized": sum(d["agent_recognized"] for d in decs),
                      "by_type": by_type, "domains": dict(domains.most_common()),
                      "patterns": [{"name": n, "count": c, "examples": examples[n]} for n, c in patterns.most_common()]},
        "usage": [{"key": k, "name": USAGE[k][0], "gloss": USAGE[k][1], "count": usage[k]}
                  for k in USAGE if usage[k] >= USAGE_MIN],
        # all four, for the quadrant: below USAGE_MIN they show as "not seen yet"
        "usage_all": [{"key": k, "name": USAGE[k][0], "gloss": USAGE[k][1], "count": usage[k],
                       "shown": usage[k] >= USAGE_MIN} for k in USAGE],
        "breadth_sample": min(len(broad), BREADTH_SAMPLE),
        "scores": scores,
    }


def product_thinker(agg):
    """[G] Share of decisions typed product_insight. Not the product *domain*: a decision can carry
    two domains, so that share runs high."""
    decs = agg["decisions"]
    if decs["total"] < PRODUCT_MIN:
        return None
    share = decs["by_type"]["product_insight"]["total"] / decs["total"]
    return share if share >= PRODUCT_SHARE else None


# ============================================================================== driver

AXIS_NAME = {"execution_leverage": "Execution leverage", "steering": "Steering",
             "engineering_quality": "Engineering quality", "product_thinking": "Product thinking",
             "planning": "Planning"}


def evidence_catalog(data, agg):
    """id → one measured fact, phrased by us (not the model). Claims cite these ids, and the report
    shows the facts verbatim, so the numbers behind a claim can't be misquoted."""
    ev = {}
    for t in data["tiles"]:
        ev[f"card.{t['key']}"] = f"{t['question']} {t['value']}." + (f" {t['caption']}" if t["caption"] else "")
    w = data["watchpoint"]
    f = lambda x: "n/a" if x is None else f"{x:.2f}"
    if w["planned_sessions"] or w["unplanned_sessions"]:
        ev["watchpoint"] = (f"Unresolved errors per session: {f(w['planned_unresolved_per_session'])} in "
                            f"{w['planned_sessions']} planned build sessions vs {f(w['unplanned_unresolved_per_session'])} "
                            f"in {w['unplanned_sessions']} unplanned; {w['clean_planned_ships']} clean planned ships"
                            + ("." if w["conclusive"] else " (too few to compare)."))
    d = agg["decisions"]
    if d["total"]:
        ev["decisions.outcomes"] = (f"{d['positive']} of {d['total']} detected decisions have explicit proof "
                                    f"they worked; the agent visibly changed course on {d['agent_recognized']}.")
        for t, v in d["by_type"].items():
            if v["total"]:
                ev[f"decisions.{t}"] = (f"{v['total']} {t.replace('_', ' ')} decisions, {v['positive']} with proof "
                                        f"they worked.")
        for k, v in d["domains"].items():
            ev[f"domain.{k}"] = f"{v} of {d['total']} decisions are tagged {k}."
        for p in d["patterns"]:
            ev[f"pattern.{p['name']}"] = f"{p['name']}: {p['count']} decision{'s' if p['count'] != 1 else ''}."
    for u in agg["usage"]:
        ev[f"usage.{u['key']}"] = f"{u['name']}: {u['count']} evidence points."
    for a, v in agg["scores"].items():
        ev[f"score.{a}"] = (f"{AXIS_NAME[a]} median {v['median']:g} of 10 (middle half {v['p25']:g}–{v['p75']:g}, "
                            f"{v['n']} segments).")
    for q in data["quality"]:
        ttc = "n/a" if q["test_to_code"] is None else q["test_to_code"]
        ev[f"repo.{q['repo']}"] = (f"{q['repo']}: test-to-code {ttc}, {q['test_files']} test files, "
                                   f"CI {'yes' if q['ci'] else 'no'}, {q['files_over_500']} files over 500 lines.")
    return ev


def _synth_input(data, results, agg):
    rs = results
    if len(rs) > SYNTH_SEGMENTS:
        rs = [rs[round(k * (len(rs) - 1) / (SYNTH_SEGMENTS - 1))] for k in range(SYNTH_SEGMENTS)]
    sig = dict(data["signals"])
    sig["mid_turn_interrupts_and_queued_prompts"] = sig.pop("redirects", 0)
    payload = {
        "evidence": evidence_catalog(data, agg),
        "notes": ("decisions.by_type counts LLM-classified decision exchanges; strategic_redirect there is "
                  "NOT the same as signals.mid_turn_interrupts_and_queued_prompts, which counts the times the "
                  "developer stopped the agent mid-run. 'positive' needs explicit proof; 'unknown' is not failure. "
                  f"Cognitive Breadth is counted over a fixed sample of {BREADTH_SAMPLE} sessions."),
        "stats": [{"q": t["question"], "a": t["value"], "detail": t["caption"]} for t in data["tiles"]],
        "signals": sig,
        "planning_watchpoint": data["watchpoint"],
        "repo_health": data["quality"],
        "segments": [{"project": r["project"], "repo": m["repo"], "title": r["title"], "summary": r["summary"],
                      "domain": r["domain"], "stack": r["stack"], "commits": m["commits"]} for m, r in rs],
        "decisions": agg["decisions"],
        "how_you_use_ai": {u["name"]: u["count"] for u in agg["usage"]},
        "axis_scores": {a: {k: v for k, v in s.items() if k in ("median", "p25", "p75", "low", "high")}
                        for a, s in agg["scores"].items()},
    }
    return redact(json.dumps(payload, indent=1, default=str))


_NUM_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w-])")     # "3-line", "v2" aren't quantities


def _nums(text):
    return {n.replace(",", "") for n in _NUM_RE.findall(text or "")}


def numbers_backed(text, facts):
    """Every quantity in `text` must appear in the facts it cites, so prose can't misquote them."""
    return _nums(text) <= _nums(" ".join(facts))


def cited(ids, catalog):
    """The catalog facts behind `ids`, dropping ids the model invented."""
    ids = ids if isinstance(ids, list) else [ids] if isinstance(ids, str) else []
    out = []
    for i in ids:
        if isinstance(i, str) and i in catalog and catalog[i] not in out:
            out.append(catalog[i])
    return out[:4]


def verified_claim(x, catalog):
    """A {text, why} claim survives only if it cites at least one real evidence id; otherwise None,
    and the report falls back to measured facts."""
    if not isinstance(x, dict):
        return None
    text, why = _str(x.get("text"), 600), cited(x.get("why"), catalog)
    return {"text": text, "why": why} if text and why and numbers_backed(text, why) else None


def clean_synthesis(r, catalog=None):
    if not r:
        return None
    cat = catalog or {}

    def lst(k, body):
        """Items whose "why" cites real evidence and whose `body` field quotes no number it can't back."""
        xs = [x for x in (r.get(k) or []) if isinstance(x, dict)] if isinstance(r.get(k), list) else []
        return [x for x in xs if cited(x.get("why"), cat) and numbers_backed(_str(x.get(body), 400), cited(x.get("why"), cat))]
    b = r.get("built") if isinstance(r.get("built"), dict) else {}
    projects = [{"name": _str(p.get("name"), 60), "what": _str(p.get("what"), 240)}
                for p in (b.get("projects") or []) if isinstance(p, dict) and _str(p.get("name"))]
    return {
        "tagline": verified_claim(r.get("tagline"), cat),
        "narrative": verified_claim(r.get("narrative"), cat),
        "built": {"projects": projects[:8],
                  "stack": [_str(x, 40) for x in (b.get("stack") or []) if _str(x, 40)][:30]},
        "strengths": [{"title": _str(x.get("title"), 60), "evidence": _str(x.get("evidence"), 400),
                       "why": cited(x.get("why"), cat)} for x in lst("strengths", "evidence")][:3],
        "growth": [{"title": _str(x.get("title"), 60), "evidence": _str(x.get("evidence"), 400),
                    "try": _str(x.get("try"), 300), "why": cited(x.get("why"), cat)} for x in lst("growth", "evidence")][:3],
        "insights": [{"title": _str(x.get("title"), 60), "detail": _str(x.get("detail"), 300),
                      "try": _str(x.get("try"), 300), "why": cited(x.get("why"), cat)} for x in lst("insights", "detail")][:2],
    }


def run(llm, sessions, data, workers=4, log=print):
    segs = [g for s in sessions for g in segments(s)]
    log(f"  {len(segs)} segments from {len(sessions)} sessions → {llm.label}, {workers} at a time")
    done = [0]

    def one(g):
        r = llm.ask("segment", SEGMENT_PROMPT, g["text"])
        done[0] += 1
        if sys.stdout.isatty():
            print(f"\r  analyzed {done[0]}/{len(segs)}", end="", flush=True)
        return g, (clean_segment(r) if r else None)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        pairs = list(ex.map(one, segs))
    if sys.stdout.isatty():
        print()
    results = [({k: v for k, v in g.items() if k != "text"}, r) for g, r in pairs if r]
    agg = aggregate(results)
    share = product_thinker(agg)
    arche = data["tiles"][0]
    if share is not None and arche["value"] == "Generalist":
        arche.update(value="Product Thinker", conf="G",
                     caption=f"{round(share * 100)}% of your decisions are product calls — you steer by what the user needs")

    log("  writing the synthesis…")
    catalog = evidence_catalog(data, agg)
    synth = clean_synthesis(llm.ask("synthesis", SYNTH_PROMPT, _synth_input(data, results, agg)), catalog)
    log("  writing the agent skill…")
    skill = clean_skill(llm.ask("skill", SKILL_PROMPT, _skill_input(agg, synth, catalog)), catalog)

    return dict(agg, backend=llm.label, synthesis=synth, skill=skill,
                segments=[dict(m, title=r["title"], summary=r["summary"], project=r["project"],
                               scores={a: v["score"] for a, v in r["scores"].items()}) for m, r in results],
                calls={"segments": len(segs), "ok": len(results), "cached": llm.stats["cached"],
                       "called": llm.stats["called"], "failed": llm.stats["failed"], "last_error": llm.last_error})
