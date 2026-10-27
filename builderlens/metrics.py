"""Deterministic metrics: everything on the report that doesn't need an LLM.

Thresholds tagged [G] in REPORT_SPEC.md are guesses awaiting calibration; they're
named constants here so calibration is a one-line change.
"""
import re
from collections import Counter, defaultdict
from datetime import timedelta

from .sources import PLAN_PATH_RE

# --- timing ------------------------------------------------------------------ [G] unless noted
ACTIVE_GAP = timedelta(minutes=30)      # a gap longer than this ends an uninterrupted stretch
LONGEST_CAP = timedelta(hours=16)       # [K] every Paxel report shows exactly "16h 0m"
DEEP_MIN = 90                           # [K] Deep Worker caption: "ran over 90 minutes"
BURST_MIN = 15                          # [K] "under 15 min or ≤2 commits"
BURST_COMMITS = 2
EPISODE_GAP = timedelta(hours=2)        # [K] commits inside a 2-hour burst window = one episode

# --- archetype thresholds ---------------------------------------------------- [G]
DEEP_SHARE = 0.75
BURST_SHARE = 0.60
VELOCITY_CPH = 5.0                      # commits per active hour

# --- tile thresholds ---------------------------------------------------------- [G]
NIGHT_HOURS = {22, 23, 0, 1, 2, 3}
NIGHT_SHARE = 0.25
THANKS_MIN = 5
SUBSTANTIVE_WORDS = 500                 # [I] 81–322 → conversational, 810+ → substantive
TERSE_WORDS = 20
GOTO_TRUNC = 39                         # [K] observed truncation lengths
CRASH_TRUNC = 46

TEST_CMD_RE = re.compile(r"\b(pytest|unittest|go test|cargo test|npm (run )?test|yarn test|pnpm test|"
                         r"bun test|jest|vitest|mocha|rspec|phpunit|mix test|swift test|gradle test|"
                         r"mvn test|ctest|tox|make test)\b")
THANKS_RE = re.compile(r"\b(thank(s| you| u)?|thx|ty|tysm|appreciate (it|that)|cheers)\b", re.I)
FIX_RE = re.compile(r"^(fix|bugfix|hotfix)(\(|:|!)|\b(fix(es|ed)?|bug|repair|resolve[sd]?|patch(ed)?|"
                    r"broken|regression|crash)\b", re.I)
FEAT_RE = re.compile(r"^feat(\(|:|!)|\b(add(s|ed)?|implement(s|ed)?|introduce[sd]?|create[sd]?|support|"
                     r"new|feature|build|enable[sd]?)\b", re.I)
ACKS = {"ok", "okay", "yes", "y", "no", "n", "continue", "go", "go ahead", "proceed", "next", "done",
        "thanks", "thank you", "ty", "k", "sure", "yep", "yup", "nope", "exit", "quit", "hi", "hello"}
CRASH_RE = re.compile(r"\b(why (is|does|did|are|isn'?t|won'?t|can'?t)|wtf|what the|still (not|broken|"
                      r"failing|wrong)|not working|doesn'?t work|isn'?t working|broken|again|stop|seriously|"
                      r"come on|ugh|ffs)\b", re.I)
PROFANITY_RE = re.compile(r"\b(fuck\w*|shit\w*|damn\w*|crap|bullshit|hell)\b", re.I)


# =========================================================================== timing helpers

def stretches(times):
    """Uninterrupted (start, end) runs — consecutive events no more than ACTIVE_GAP apart."""
    out = []
    for t in times:
        if out and t - out[-1][1] <= ACTIVE_GAP:
            out[-1][1] = t
        else:
            out.append([t, t])
    return [(a, b) for a, b in out]


def minutes(td):
    return td.total_seconds() / 60


def session_timing(s):
    st = stretches(s.times)
    return {
        "active_min": sum(minutes(b - a) for a, b in st),
        "longest_stretch_min": max((minutes(b - a) for a, b in st), default=0),
        "span": min((s.end - s.start) if s.times else timedelta(0), LONGEST_CAP),
        "stretches": st,
    }


# =========================================================================== git linkage

def link_commits(sessions, commits):
    """Give each commit to at most one session: same repo, inside the session's span
    (+30 min grace), preferring the most recently started session."""
    by_repo = defaultdict(list)
    for s in sessions:
        if s.repo:
            by_repo[s.repo].append(s)
    for c in commits:
        best = None
        for s in by_repo.get(c.repo, ()):
            if s.start <= c.ts <= s.end + ACTIVE_GAP and (best is None or s.start > best.start):
                best = s
        if best:
            best.commits.append(c)


def episodes(sessions, commits, timing):
    """[K] Paxel's fallback: commits in a 2-hour burst window → else one chat session.
    (PR grouping needs PR↔commit data we don't have locally; burst windows approximate it.)"""
    owner = {c.sha: s for s in sessions for c in s.commits}
    eps = []
    for repo in sorted({c.repo for c in commits}):
        cs = sorted((c for c in commits if c.repo == repo), key=lambda c: c.ts)
        group = []
        for c in cs:
            if group and c.ts - group[-1].ts > EPISODE_GAP:
                eps.append(group)
                group = []
            group.append(c)
        if group:
            eps.append(group)
    blocks, used = [], set()
    for group in eps:
        sess = {id(owner[c.sha]): owner[c.sha] for c in group if c.sha in owner}
        used.update(sess)
        active = sum(timing[id(s)]["active_min"] for s in sess.values())
        if not sess:
            active = minutes(group[-1].ts - group[0].ts)
        blocks.append({"commits": len(group), "active_min": active, "sessions": len(sess)})
    for s in sessions:
        if id(s) not in used:
            blocks.append({"commits": 0, "active_min": timing[id(s)]["active_min"], "sessions": 1})
    return blocks


# =========================================================================== planning + errors

def _plan_touch(s):
    return any(PLAN_PATH_RE.search(p) for c in s.calls for p in c.paths)


def _plan_written(s):
    return s.plan_mode or any(c.name in ("ExitPlanMode", "update_plan") for c in s.calls) or \
        any(PLAN_PATH_RE.search(p) for c in s.edits for p in c.paths)


def planned_flags(sessions):
    """[K] "started from a plan — a plan file, plan mode, or a plan written a session or two
    earlier". Earlier = the previous two sessions in the same repo."""
    flags, recent = {}, defaultdict(list)
    for s in sessions:                                      # sessions are start-sorted
        key = s.repo or s.cwd
        flags[id(s)] = s.plan_mode or _plan_touch(s) or _plan_written(s) or \
            any(_plan_written(p) for p in recent[key][-2:])
        recent[key].append(s)
    return flags


def unresolved_errors(s):
    """[K] An error is unresolved if no passing test run or commit follows it in the session."""
    fixes = sorted([c.ts for c in s.calls if c.kind == "shell" and TEST_CMD_RE.search(c.command)
                    and not c.error] + [c.ts for c in s.commits])
    return sum(1 for c in s.calls if c.error and not any(t > c.ts for t in fixes))


# =========================================================================== prompt picks

def _norm(text):
    return re.sub(r"[\s.!?,;:]+$", "", re.sub(r"\s+", " ", text.strip().lower()))


def _trunc(text, n):
    text = re.sub(r"\s+", " ", text.strip())
    return text if len(text) <= n else text[:n].rstrip() + "…"


def go_to_prompt(sessions):
    counts, where = Counter(), defaultdict(set)
    for s in sessions:
        for p in s.prompts:
            k = _norm(p.text)
            if k:
                counts[k] += 1
                where[k].add(s.id)
    for k, n in counts.most_common():
        if n >= 3 and len(where[k]) >= 2:
            first = next(p.text for s in sessions for p in s.prompts if _norm(p.text) == k)
            return {"text": _trunc(first, GOTO_TRUNC), "count": n, "sessions": len(where[k])}
    return None


_WORD_RE = re.compile(r"[^\W\d_]+", re.U)


def cryptic_prompt(sessions, exclude=None):
    """Short, ambiguous or typo'd prompt the agent still acted on. A 'typo' is a word the user
    almost never writes — vocab is built from their own prompts, so it works in any language."""
    vocab = Counter(w.lower() for s in sessions for p in s.prompts for w in _WORD_RE.findall(p.text))
    best = None
    for s in sessions:
        for p in s.prompts:
            words = p.text.split()
            k = _norm(p.text)
            if not 1 <= len(words) <= 7 or k in ACKS or k == exclude or "\n" in p.text.strip():
                continue
            if not any(c.ts > p.ts for c in s.calls):          # agent never acted on it
                continue
            raw = _WORD_RE.findall(p.text)
            toks = [w.lower() for w in raw]
            if not toks:
                continue
            # Typos are lowercase words the user never writes again; capitalized / CamelCase
            # tokens are names (GLaDOS, PyBugHive), not typos.
            rare = sum(1 for w in raw if w == w.lower() and vocab[w.lower()] <= 1 and len(w) >= 3)
            vague = sum(1 for w in toks if w in {"it", "that", "this", "those", "them", "stuff", "thing", "one"})
            score = rare * 2 + vague + (p.text == p.text.lower()) * 0.5 + \
                (not re.search(r"[.?!]$", p.text.strip())) * 0.3 + max(0, 4 - len(words)) * 0.3
            if score >= 2 and (best is None or score > best[0]):
                best = (score, p.text.strip())
    return best[1] if best else None


def crash_out(sessions):
    best = None
    for s in sessions:
        for p in s.prompts:
            t = p.text.strip()
            letters = [c for c in t if c.isalpha()]
            caps = len(letters) >= 10 and sum(c.isupper() for c in letters) / len(letters) >= 0.6
            score = 3 * caps + 2 * bool(PROFANITY_RE.search(t)) + len(CRASH_RE.findall(t)) + \
                bool(re.search(r"[!?]{2,}", t))
            if score >= 2 and (best is None or score > best[0]):
                best = (score, t)
    return _trunc(best[1], CRASH_TRUNC) if best else None


# =========================================================================== the report data

def _hour12(h):
    return f"{(h - 1) % 12 + 1} {'AM' if h < 12 else 'PM'}"


def _streak(dates):
    days, best, run, prev = sorted(set(dates)), 0, 0, None
    for d in days:
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best, prev = max(best, run), d
    return best


def _fmt_dur(td):
    m = int(td.total_seconds() // 60)
    return f"{m // 60}h {m % 60}m"


def compute(sessions, commits, quality, header):
    """sessions: human main sessions (already scoped). Returns the full report dict."""
    analyzed = [s for s in sessions if s.prompts]
    timing = {id(s): session_timing(s) for s in analyzed}
    link_commits(analyzed, commits)
    prompts = [p for s in analyzed for p in s.prompts]
    n_sess = len(analyzed) or 1
    words = [len(p.text.split()) for p in prompts]
    avg_words = round(sum(words) / len(words)) if words else 0
    active_h = sum(t["active_min"] for t in timing.values()) / 60
    tiles = []

    def tile(key, q, value, caption="", conf="K"):
        tiles.append({"key": key, "question": q, "value": value, "caption": caption, "conf": conf})

    # ---- archetype --------------------------------------------------------------------
    blocks = episodes(analyzed, commits, timing)
    nb = len(blocks) or 1
    deep_share = sum(b["active_min"] > DEEP_MIN for b in blocks) / nb
    burst_share = sum(b["active_min"] < BURST_MIN or 1 <= b["commits"] <= BURST_COMMITS for b in blocks) / nb
    cph = len(commits) / active_h if active_h else 0
    cands = []
    if deep_share >= DEEP_SHARE:
        cands.append((deep_share / DEEP_SHARE, "Deep Worker", f"{round(deep_share * 100)}% of work blocks ran over 90 minutes"))
    if burst_share >= BURST_SHARE:
        cands.append((burst_share / BURST_SHARE, "Burst Builder",
                      f"{round(burst_share * 100)}% of work blocks were short bursts (under 15 min or ≤2 commits)"))
    if commits and cph >= VELOCITY_CPH:
        cands.append((cph / VELOCITY_CPH, "Velocity Machine", f"{cph:.1f} commits per active hour"))
    cands.sort(reverse=True)
    if cands:
        tile("archetype", "Which kind of builder are you?", cands[0][1], cands[0][2], "G")
    else:
        tile("archetype", "Which kind of builder are you?", "Generalist",
             "No single working pattern dominates — you adapt your approach to the task")

    # ---- shipping ---------------------------------------------------------------------
    prs = set().union(*(s.pr_urls for s in analyzed)) if analyzed else set()
    if commits:
        lines = sum(c.added + c.deleted for c in commits)
        pr = f" and {len(prs)} PR{'s' if len(prs) != 1 else ''} worked" if prs else ""
        tile("ship", "How much did you ship?", f"{lines:,} lines", f"Across {len(commits):,} commits{pr}.", "I")
    if len(cands) > 1:
        tile("secondary", "And what else?", cands[1][1], cands[1][2], "G")

    local_hours = [c.ts.astimezone().hour for c in commits]
    night = sum(h in NIGHT_HOURS for h in local_hours) / len(local_hours) if local_hours else 0
    if local_hours and night >= NIGHT_SHARE:
        tile("when", "When are you most productive?", "Night owl",
             f"{round(night * 100)}% of your commits land late at night.", "G")
    elif prompts:
        peak = Counter(p.ts.astimezone().hour for p in prompts).most_common(1)[0][0]
        tile("when", "When are you most productive?", f"Most alive at {_hour12(peak)}",
             f"Your busiest stretch is around {_hour12(peak)}.", "I")

    # ---- planning ---------------------------------------------------------------------
    planned = planned_flags(analyzed)
    build = [s for s in analyzed if s.edits or s.commits]
    if build:
        a = sum(planned[id(s)] for s in build)
        tile("plan", "How often do you plan first?", f"{round(100 * a / len(build))}% of build sessions",
             f"{a} of {len(build)} sessions that changed code started from a plan — a plan file, "
             "plan mode, or a plan written a session or two earlier.", "I")

    # ---- working style ------------------------------------------------------------------
    if avg_words >= SUBSTANTIVE_WORDS:
        tile("style", "How do you work with your agent?", "A thinking partner",
             "Detailed, context-rich prompts — you bring the agent into the problem, not just the task.", "I")
    elif avg_words < TERSE_WORDS:
        tile("style", "How do you work with your agent?", "Quick-fire direction",
             "Short, pointed prompts — you steer in small, fast moves.", "G")
    else:
        tile("style", "How do you work with your agent?", "A back-and-forth",
             "You work in dialogue, shaping the work as you go.", "I")

    longest = max((t["span"] for t in timing.values()), default=timedelta(0))
    tile("longest", "Your longest single session?", _fmt_dur(longest),
         "Your deepest uninterrupted stretch with an agent.", "I")

    # ---- concurrency --------------------------------------------------------------------
    edges = sorted([(a, 1) for t in timing.values() for a, _ in t["stretches"]] +
                   [(b, -1) for t in timing.values() for _, b in t["stretches"]],
                   key=lambda e: (e[0], e[1]))
    cur = peak_c = 0
    for _, d in edges:
        cur += d
        peak_c = max(peak_c, cur)
    tile("agents", "How many agents do you run?", f"{max(peak_c, 1)} at once",
         f"As many as {max(peak_c, 1)} main sessions running at the same time.")

    # ---- prompts --------------------------------------------------------------------------
    thanks = sum(bool(THANKS_RE.search(p.text)) for p in prompts)
    if thanks >= THANKS_MIN:
        tile("polite", "How polite are you?", f"{thanks} thank-yous",
             f"You thanked your agent in {thanks} of your messages.")
    goto = go_to_prompt(analyzed)
    if goto:
        tile("goto", "What's your go-to prompt?", f"“{goto['text']}”",
             f"You sent it {goto['count']} times across {goto['sessions']} sessions.")
    if commits:
        tile("streak", "What's your longest streak?",
             f"{_streak([c.ts.astimezone().date() for c in commits])} days straight",
             "Consecutive days you shipped something.")
    redirects = sum(s.interrupts + sum(p.queued for p in s.prompts) for s in analyzed)
    if prompts:
        tile("course", "How often do you change course?", f"{round(100 * redirects / len(prompts))}% of the time",
             "You stop and redirect the agent mid-task rather than letting it run.", "I")
    crash = crash_out(analyzed)
    if crash:
        tile("crash", "Your biggest crash out?", f"“{crash}”", "We've all been there.", "G")
    if commits:
        day, n = Counter(c.ts.astimezone().date() for c in commits).most_common(1)[0]
        wd = day.strftime("%A")
        tile("bigday", "Your biggest day?", wd, f"Your single busiest push — {n} commits — landed on a {wd}.")
    if prompts:
        tag = "substantive" if avg_words >= SUBSTANTIVE_WORDS else "terse" if avg_words < TERSE_WORDS else "conversational"
        tile("length", "How long are your prompts?", f"{avg_words} words on average", f"Mostly {tag} prompts.", "I")

    deep = [t["longest_stretch_min"] for t in timing.values() if t["longest_stretch_min"] >= DEEP_MIN]
    if deep:
        tile("deep", "How do you work?", f"{len(deep)} deep sessions",
             f"Averaging {round(sum(deep) / len(deep))} minutes of uninterrupted focus.", "I")
    tile("time", "How much time did you put in?", f"{round(active_h):,} hours", f"Across {len(analyzed)} sessions.", "I")
    cryptic = cryptic_prompt(analyzed, exclude=_norm(goto["text"]) if goto else None)
    if cryptic:
        tile("cryptic", "Your most cryptic prompt?", f"“{cryptic}”", "Somehow the agent knew exactly what you meant.", "G")
    tile("talk", "How much do you talk to your agent?", f"{round(len(prompts) / n_sess)} prompts a session")
    fixes = sum(bool(FIX_RE.search(c.subject)) for c in commits)
    feats = sum(bool(FEAT_RE.search(c.subject)) and not FIX_RE.search(c.subject) for c in commits)
    if fixes + feats >= 5:
        tile("mix", "What kind of work is it?", "Mostly features" if feats >= fixes else "Mostly fixes",
             f"{fixes} fixes and {feats} features in your commits.", "I")

    # ---- planning watchpoint (Growth Areas, deterministic half) -----------------------------
    unres = {id(s): unresolved_errors(s) for s in build}
    p_set = [s for s in build if planned[id(s)]]
    u_set = [s for s in build if not planned[id(s)]]
    avg = lambda xs: round(sum(unres[id(s)] for s in xs) / len(xs), 2) if xs else None
    watch = {
        "planned_sessions": len(p_set), "unplanned_sessions": len(u_set),
        "planned_unresolved_per_session": avg(p_set), "unplanned_unresolved_per_session": avg(u_set),
        "clean_planned_ships": sum(1 for s in p_set if s.commits and unres[id(s)] == 0),
    }
    watch["conclusive"] = watch["clean_planned_ships"] >= 2

    return {
        "header": dict(header, sessions_analyzed=len(analyzed)),
        "tiles": tiles,
        "watchpoint": watch,
        "quality": quality,
        "signals": {
            "work_blocks": len(blocks), "deep_share": round(deep_share, 2), "burst_share": round(burst_share, 2),
            "commits_per_active_hour": round(cph, 2), "night_commit_share": round(night, 2),
            "avg_prompt_words": avg_words, "prompts": len(prompts), "active_hours": round(active_h, 1),
            "commits": len(commits), "prs": len(prs), "redirects": redirects,
            "tools": dict(Counter(s.tool for s in analyzed)),
        },
    }
