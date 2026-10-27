"""Render report.json + report.html. Everything user-derived is HTML-escaped.

Layout follows the published reports: one narrow text column, a fanned deck of stat cards,
then prose sections separated by a short centered tick. The page is fully self-contained:
no web fonts, images or scripts, so opening it makes no network requests.
"""
import json
import os
from html import escape as e

PENDING = [
    ("Your narrative", "A one-paragraph read on how you build, and a one-line tagline."),
    ("What You Built", "Projects, domains and stack, named from per-session summaries."),
    ("Decision Patterns", "Decision exchanges with type, domain and outcome, plus the named patterns they match."),
    ("Strengths & Growth Areas", "Evidence-cited strengths and specific next steps."),
    ("How you use AI", "Dances with Robots, Frame Breaker, Cognitive Breadth, Architect's Veto, with evidence counts."),
    ("The five axes", "execution_leverage, steering, engineering_quality, product_thinking, planning, "
                      "scored 0–10 per episode."),
]
TYPE_LABEL = {"strategic_redirect": "strategic redirects", "technical_catch": "technical catches",
              "product_insight": "product insights", "option_selection": "option selections"}
AXIS_LABEL = {"execution_leverage": "Execution leverage", "steering": "Steering",
              "engineering_quality": "Engineering quality", "product_thinking": "Product thinking",
              "planning": "Planning"}
DECK_ROW = 5

CSS = """
:root{--display:"Iowan Old Style","Palatino Linotype",Palatino,Charter,"Book Antiqua",Georgia,serif;--bg:#fff;--ink:#111;--muted:#6b6b6b;--line:#2f6f5e;--hair:rgba(17,17,17,.10);--card:#fff;
--shadow:rgba(0,0,0,.18);--font:"Space Grotesk",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111312;--ink:#ecebe7;--muted:#9a9f9c;
--line:#6fc3a8;--hair:rgba(255,255,255,.12);--card:#181b1a;--shadow:rgba(0,0,0,.6)}}
:root[data-theme=dark]{--bg:#111312;--ink:#ecebe7;--muted:#9a9f9c;--line:#6fc3a8;--hair:rgba(255,255,255,.12);
--card:#181b1a;--shadow:rgba(0,0,0,.6)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:400 16px/1.6 var(--font);overflow-x:clip}
.frame{max-width:1200px;margin:0 auto;min-height:100dvh;border-left:1px solid var(--line);border-right:1px solid var(--line);padding:48px 32px 64px}
@media (max-width:720px){.frame{padding:32px 16px 48px;border:0}}
.wrap{max-width:600px;margin:0 auto}
h1{font:600 40px/1.05 var(--display);letter-spacing:-.02em;margin:0}
.sub{display:block;font:italic 400 17px/1.4 var(--display);letter-spacing:0;color:var(--muted);margin-top:8px}
@media (max-width:600px){h1{font-size:32px}}
.meta{margin-top:14px}
/* "why" hover: the evidence behind a synthesized claim */
.why{position:relative;display:inline-block;margin-left:4px;font-size:12px;line-height:1;color:var(--line);
border:1px solid var(--line);border-radius:99px;padding:2px 6px;cursor:help;vertical-align:2px}
.why:focus{outline:2px solid var(--line);outline-offset:2px}
.why [role=tooltip]{position:absolute;left:50%;bottom:calc(100% + 8px);transform:translateX(-50%);width:min(320px,80vw);
padding:10px 12px;background:var(--card);color:var(--ink);border:1px solid var(--line);box-shadow:0 14px 34px -16px var(--shadow);
font-size:13px;line-height:1.5;text-align:left;opacity:0;pointer-events:none;transition:opacity .15s;z-index:300}
.why:hover [role=tooltip],.why:focus [role=tooltip]{opacity:1}
.why .wh{display:block;font-weight:600;margin-bottom:4px}.why .wi{display:block;padding-left:10px;text-indent:-10px;margin:0 0 4px}
.why .wi::before{content:"· "}
.meta{font-size:13px;margin:6px 0 0}
.verdict{margin:16px 0 0;max-width:560px}
/* sections: a 28px centered tick, then a heading at body size */
.sec::before{content:"";display:block;width:28px;height:1px;background:var(--line);margin:40px auto}
.sec-h{font-size:16px;font-weight:600;letter-spacing:-.01em;line-height:1.3;margin:0 0 12px}
.prose p{margin:0 0 16px}.prose p:last-child{margin-bottom:0}
.prose h2{font-size:16px;font-weight:600;letter-spacing:-.01em;line-height:1.3;margin:24px 0 12px}
.prose ul{margin:0 0 16px;padding-left:20px}.prose li{margin:0 0 6px}
.prose .try{color:var(--muted)}
.small{font-size:13px;color:var(--muted)}
/* "How you use AI": borderless two-column list */
.badges{display:grid;grid-template-columns:1fr 1fr;gap:20px 24px}
@media (max-width:600px){.badges{grid-template-columns:1fr}}
.badges p{margin:0 0 4px}.b-name{font-weight:600}.b-ev{font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;vertical-align:top;padding:8px 8px 8px 0;border-bottom:1px solid var(--hair)}
th{font-weight:600}.scroll{overflow-x:auto}.num{font-variant-numeric:tabular-nums}
/* the deck: breaks out of the text column, fanned rows that tuck under each other */
.deck{width:min(960px,calc(100vw - 48px));margin:28px 0 8px 50%;transform:translateX(-50%);
display:flex;flex-direction:column;align-items:center}
.row{display:flex;justify-content:center;align-items:flex-end}
.row+.row{margin-top:-40px}
.card{--rot:0deg;--w:clamp(150px,18.5vw,220px);flex:none;width:var(--w);aspect-ratio:11/16;
margin-left:calc(var(--w) * -.1);position:relative;z-index:1;overflow:hidden;perspective:900px;
background:var(--card);border:1px solid var(--line);box-shadow:0 6px 16px -8px var(--shadow);
transform:rotate(var(--rot));transform-origin:50% 100%;transition:transform .6s cubic-bezier(.32,.72,0,1),box-shadow .6s cubic-bezier(.32,.72,0,1);
-webkit-mask:radial-gradient(circle calc(var(--w) * .03) at 50% calc(var(--w) * .07),#0000 96%,#000);
mask:radial-gradient(circle calc(var(--w) * .03) at 50% calc(var(--w) * .07),#0000 96%,#000)}
.card::after{content:"";position:absolute;inset:calc(var(--w) * .027);border:1px dashed var(--line);pointer-events:none;opacity:.7;z-index:3}
/* click (or Enter/Space) flips a card to "how it's measured" */
.flip{position:absolute;inset:0;cursor:pointer;transform-style:preserve-3d;transition:transform .6s cubic-bezier(.32,.72,0,1)}
.flip:focus-visible{outline:2px solid var(--line);outline-offset:-6px}
.card.flipped .flip{transform:rotateY(180deg)}
.face{position:absolute;inset:0;display:flex;flex-direction:column;background:var(--card);-webkit-backface-visibility:hidden;backface-visibility:hidden}
.back{transform:rotateY(180deg)}
.back .body{padding-top:calc(var(--w) * .16);overflow:auto}
.back .how{font-size:calc(var(--w) * .056);line-height:1.45;margin:0}
.back .num-l{font-size:calc(var(--w) * .056);line-height:1.45;margin:0;color:var(--muted)}
.hint{text-align:center;font-size:13px;color:var(--muted);margin:4px 0 0}
.row .card:first-child{margin-left:0}
.row .card:nth-child(1){--rot:-3deg}.row .card:nth-child(2){--rot:-1.5deg}
.row .card:nth-child(4){--rot:1.5deg}.row .card:nth-child(5){--rot:3deg}
.card:hover{z-index:100;transform:rotate(0) translateY(-12px) scale(1.03);box-shadow:0 30px 50px -18px var(--shadow)}
.row .card:hover~.card{transform:rotate(var(--rot)) translateX(32px)}
.row .card:has(~.card:hover){transform:rotate(var(--rot)) translateX(-32px)}
@media (prefers-reduced-motion:reduce){.flip{transition:none}.card,.card:hover,.row .card:hover~.card,.row .card:has(~.card:hover){transition:none;transform:rotate(var(--rot))}}
@media (max-width:760px){.deck{width:auto;margin:28px 0 8px;transform:none}
.row{flex-direction:column;gap:14px}.row+.row{margin-top:14px}
.card{--w:min(70vw,240px);--rot:0deg;margin-left:0}
.card:hover,.row .card:hover~.card,.row .card:has(~.card:hover){transform:none}}
/* art strip: a dot screen faded along a per-card angle, a stand-in for dithered artwork */
.art{flex:none;aspect-ratio:220/138;position:relative;overflow:hidden}
.art::before,.art::after{content:"";position:absolute;inset:0;background-image:radial-gradient(circle,var(--line) .9px,transparent 1.2px)}
.art::before{background-size:4px 4px;-webkit-mask-image:linear-gradient(var(--a),#000,transparent 75%);mask-image:linear-gradient(var(--a),#000,transparent 75%)}
.art{opacity:.75}
.art::after{background-size:7px 7px;background-position:2px 3px;opacity:.55;
-webkit-mask-image:radial-gradient(circle at var(--x) var(--y),#000 0,transparent 55%);mask-image:radial-gradient(circle at var(--x) var(--y),#000 0,transparent 55%)}
.body{flex:1;min-height:0;display:flex;flex-direction:column;gap:calc(var(--w) * .027);overflow:hidden;
padding:calc(var(--w) * .064) calc(var(--w) * .13) calc(var(--w) * .073) calc(var(--w) * .073)}
.row .card:last-child .body{padding-right:calc(var(--w) * .073)}
.front .body p,.front .body h3{margin:0;letter-spacing:-.01em;display:-webkit-box;-webkit-box-orient:vertical;overflow:hidden}
.back .q{margin:0}
.q{font-size:calc(var(--w) * .05);line-height:1.3;color:var(--line);-webkit-line-clamp:2}
.t{font-size:calc(var(--w) * .068);font-weight:600;line-height:1.25;-webkit-line-clamp:2;overflow-wrap:anywhere}
.d{font-size:calc(var(--w) * .059);line-height:1.45;-webkit-line-clamp:3}
.est{color:var(--muted)}
/* charts: HTML bars. Colors are validated chart slots (CVD-safe, >=3:1 on both surfaces), separate from
   the UI accent. Marks carry color; text stays in ink tokens. */
:root{--s1:#2a78d6;--s2:#eb6834;--grid:rgba(17,17,17,.08)}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--s1:#3987e5;--s2:#d95926;--grid:rgba(255,255,255,.10)}}
:root[data-theme=dark]{--s1:#3987e5;--s2:#d95926;--grid:rgba(255,255,255,.10)}
.chart{margin:4px 0 20px}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:13px;color:var(--muted);margin:0 0 8px}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.hrow{position:relative;display:grid;grid-template-columns:minmax(110px,34%) 1fr auto;align-items:center;gap:10px;
font-size:13px;padding:4px 0}
.hrow .lab{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hrow .val{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.track{display:flex;gap:2px;height:14px}
.seg{height:100%;min-width:2px}.seg:last-child{border-radius:0 4px 4px 0}
.hrow:hover{background:var(--grid)}
.hrow[data-tip]:hover::after,.hrow[data-tip]:focus::after{content:attr(data-tip);position:absolute;left:34%;bottom:calc(100% + 4px);z-index:50;
width:min(340px,70vw);padding:8px 10px;background:var(--card);color:var(--ink);border:1px solid var(--hair);
box-shadow:0 14px 34px -16px var(--shadow);font-size:13px;line-height:1.45;white-space:normal}
.scale{position:relative;height:14px;background:linear-gradient(90deg,var(--grid) 1px,transparent 1px) 0 0/10% 100%}
.scale::after{content:"";position:absolute;right:0;top:0;bottom:0;width:1px;background:var(--grid)}
.band{position:absolute;top:2px;bottom:2px;background:var(--s1);opacity:.28;border-radius:4px}
.dot{position:absolute;top:50%;width:10px;height:10px;margin:-5px 0 0 -5px;border-radius:50%;background:var(--s1);box-shadow:0 0 0 2px var(--bg)}
.ticks{display:grid;grid-template-columns:minmax(110px,34%) 1fr auto;gap:10px;font-size:12px;color:var(--muted)}
.ticks div:nth-child(2){display:flex;justify-content:space-between}
details.tbl summary{cursor:pointer;font-size:13px;color:var(--muted);margin:8px 0}
.pending li{color:var(--muted)}.pending b{color:var(--ink);font-weight:600}
footer{margin:56px auto 0;font-size:13px;color:var(--muted);max-width:600px}
code{font-size:12px}
"""


ARCHETYPE_HOW = ("Commits grouped into 2-hour work blocks. Deep Worker: 75%+ of blocks run 90+ min. "
                 "Burst Builder: 60%+ are short. Velocity Machine: 5+ commits an active hour. "
                 "Product Thinker: 40%+ product decisions. Otherwise Generalist.")
# What each card measures, shown on its back.
HOW = {
    "archetype": ARCHETYPE_HOW,
    "secondary": ARCHETYPE_HOW,
    "ship": "Lines added plus deleted in commits authored by your git email, in the repos your sessions worked in, "
            "between your first and last session. At most 1,000 commits per repo.",
    "when": "The local hour you send the most prompts. You're a night owl instead if 25%+ of your commits land "
            "between 10 PM and 3 AM.",
    "plan": "A build session (one that edited code or landed a commit) counts as planned if it used plan mode, "
            "touched a plan file, or a plan was written in one of the two sessions before it.",
    "style": "From your average prompt length: 500+ words is a thinking partner, under 20 is quick-fire, "
             "anything between is a back-and-forth.",
    "longest": "First to last event in one session, capped at 16 hours like Paxel's report.",
    "agents": "The most main sessions active at the same moment. A session counts as active while its events are "
              "under 30 minutes apart. Sub-agents and headless runs are excluded.",
    "polite": "Prompts that thank the agent.",
    "goto": "Your most repeated prompt after ignoring case and trailing punctuation.",
    "streak": "The longest run of consecutive days, in your time zone, with at least one commit.",
    "course": "Interrupts plus prompts you typed while the agent was still working, as a share of all your prompts.",
    "crash": "A heuristic pick of your most heated prompt: capitals, repeated punctuation, \u201cwhy is it\u2026\u201d, "
             "swearing.",
    "bigday": "The weekday of the single date with the most commits.",
    "length": "Mean words per prompt you typed. Context the tools inject, like file contents, is excluded.",
    "deep": "Sessions whose longest uninterrupted stretch (no gap over 30 minutes) ran past 90 minutes.",
    "time": "The sum of active stretches: time between events with no gap over 30 minutes. It includes time the "
            "agent spends working on its own.",
    "cryptic": "A short prompt with the most rare lowercase words (likely typos), other than your go-to prompt.",
    "talk": "Prompts you typed, divided by sessions that had at least one prompt.",
    "mix": "Commit subjects that read as fixes (fix, bug, …) versus features (feat, add, implement, …).",
}


def _numbers(key, sig):
    pct = lambda x: f"{round(x * 100)}%"
    if key in ("archetype", "secondary"):
        return (f"Yours: {sig['work_blocks']} work blocks, {pct(sig['deep_share'])} deep, {pct(sig['burst_share'])} "
                f"bursts, {sig['commits_per_active_hour']} commits per active hour.")
    if key == "when":
        return f"Yours: {pct(sig['night_commit_share'])} of commits land late at night."
    if key in ("course",):
        return f"Yours: {sig['redirects']} redirects in {sig['prompts']:,} prompts."
    if key in ("time", "talk", "length"):
        return f"Yours: {sig['prompts']:,} prompts, {sig['active_hours']:,} active hours."
    return ""


def _card(t, i, sig):
    # deterministic per-card variation of the art strip
    a, x, y = (35 + i * 47) % 360, 20 + (i * 37) % 60, 25 + (i * 53) % 50
    est = '<span class="est"> · estimate</span>' if t["conf"] == "G" else ""
    cap = f'<p class="d">{e(t["caption"])}</p>' if t["caption"] else ""
    how = HOW.get(t["key"], "")
    if t["conf"] == "G":
        how += " The threshold is a calibrated guess from published reports."
    nums = _numbers(t["key"], sig)
    back = (f'<div class="body"><p class="q">How it\'s measured</p><p class="how">{e(how)}</p>'
            + (f'<p class="num-l">{e(nums)}</p>' if nums else "") + "</div>")
    return (f'<div class="card" role="listitem"><div class="flip" role="button" tabindex="0" aria-pressed="false" '
            f'aria-label="{e(t["question"])} {e(t["value"])}. Flip to see how it\'s measured.">'
            f'<div class="face front"><div class="art" style="--a:{a}deg;--x:{x}%;--y:{y}%" aria-hidden="true"></div>'
            f'<div class="body"><p class="q">{e(t["question"])}{est}</p><h3 class="t">{e(t["value"])}</h3>{cap}</div></div>'
            f'<div class="face back">{back}</div></div></div>')


FLIP_JS = """<script>
document.querySelectorAll('.flip').forEach(function (f) {
  function toggle() { f.setAttribute('aria-pressed', f.parentNode.classList.toggle('flipped')); }
  f.addEventListener('click', toggle);
  f.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); toggle(); }
  });
});
</script>"""


def _deck(tiles, sig):
    rows = [tiles[i:i + DECK_ROW] for i in range(0, len(tiles), DECK_ROW)]
    return ('<div class="deck" role="list" aria-label="What this report found">'
            + "".join('<div class="row">' + "".join(_card(t, r * DECK_ROW + i, sig) for i, t in enumerate(row)) + "</div>"
                      for r, row in enumerate(rows)) + '</div><p class="hint">Click a card to see how it\'s measured.</p>')


def _why(facts, n):
    """A small "why" badge whose hover/focus tooltip lists the measured facts behind a claim."""
    if not facts:
        return ""
    return (f'<span class="why" tabindex="0" aria-describedby="why{n}">why<span role="tooltip" id="why{n}">'
            f'<span class="wh">Measured</span>' + "".join(f'<span class="wi">{e(x)}</span>' for x in facts)
            + "</span></span>")


def _bars(rows, legend=None):
    """rows: [(label, [(value, css_color), ...], value_text, tooltip)]. Horizontal bars on one shared scale."""
    top = max((sum(v for v, _ in segs) for _, segs, _, _ in rows), default=0) or 1
    out = ['<div class="chart">']
    if legend:
        out.append('<div class="legend">' + "".join(f'<span><span class="sw" style="background:{c}"></span>{e(n)}</span>'
                                                    for n, c in legend) + "</div>")
    for label, segs, val, tip in rows:
        bars = "".join(f'<span class="seg" style="width:{100 * v / top:.2f}%;background:{c}"></span>' for v, c in segs if v)
        tip_attr = f' data-tip="{e(tip)}" tabindex="0"' if tip else ""
        out.append(f'<div class="hrow"{tip_attr}><span class="lab" title="{e(label)}">{e(label)}</span>'
                   f'<span class="track">{bars}</span><span class="val">{e(val)}</span></div>')
    return "".join(out) + "</div>"


def _section(title, inner):
    return f'<section class="sec"><p class="sec-h">{e(title)}</p>{inner}</section>'


def _watchpoint(w):
    if not (w["planned_sessions"] or w["unplanned_sessions"]):
        return "<p><b>Watchpoint:</b> no sessions changed code, so there's nothing to compare yet.</p>"
    f = lambda x: "—" if x is None else f"{x:.2f}"
    n = w["clean_planned_ships"]
    tail = ("Planned work may have been harder, so this doesn't show that planning caused the difference."
            if w["conclusive"] else
            f"With {n} clean planned ship{'s' if n != 1 else ''} (planned, committed, zero unresolved errors), "
            "it's too early to say whether planning gives you cleaner finishes; you need at least 2 to compare.")
    return (f"<p><b>Watchpoint:</b> unresolved errors per session, meaning errors not followed by a passing test "
            f"or commit in that session. Your {w['planned_sessions']} planned build sessions averaged "
            f"{f(w['planned_unresolved_per_session'])}, against {f(w['unplanned_unresolved_per_session'])} across "
            f"{w['unplanned_sessions']} without a plan. {e(tail)}</p>")


def _decisions(L):
    d = L["decisions"]
    if not d["total"]:
        return ""
    P = ["<h2>Decision Patterns</h2>"]
    top = next(iter(d["domains"].items()), None)
    lead = f"{e(top[0].capitalize())} accounts for {top[1]} of {d['total']} detected decisions. " if top else ""
    types = ", ".join(f"{v['total']} {TYPE_LABEL[t]}"
                      for t, v in sorted(d["by_type"].items(), key=lambda x: -x[1]["total"]) if v["total"])
    P.append(f"<p>{lead}By kind: {types}. {d['positive']} of {d['total']} have explicit proof they worked "
             f"(a passing check, a matching commit, or you confirming it); the rest are unproven, not failed.</p>")
    kinds = sorted(((t, v) for t, v in d["by_type"].items() if v["total"]), key=lambda x: -x[1]["total"])
    P.append(_bars([(TYPE_LABEL[t].capitalize(), [(v["positive"], "var(--s1)"), (v["total"] - v["positive"], "var(--s2)")],
                     f"{v['positive']} of {v['total']}", f"{v['positive']} proven, {v['total'] - v['positive']} unproven")
                    for t, v in kinds], legend=[("proven to work", "var(--s1)"), ("unproven", "var(--s2)")]))
    if d["domains"]:
        P.append('<p class="small" style="margin:0 0 4px">Decisions by area (a decision can carry two areas)</p>')
        P.append(_bars([(k.capitalize(), [(v, "var(--s1)")], f"{v}", "") for k, v in d["domains"].items()]))
    if d["patterns"]:
        P.append('<p class="small" style="margin:0 0 4px">Named patterns · hover for an example</p>')
        P.append(_bars([(x["name"], [(x["count"], "var(--s1)")], f"{x['count']}",
                         f"e.g. {x['examples'][0]}" if x["examples"] else "") for x in d["patterns"][:8]]))
    for i, x in enumerate((L.get("synthesis") or {}).get("insights") or []):
        tr = f' <span class="try">Try: {e(x["try"])}</span>' if x.get("try") else ""
        P.append(f"<p><b>{e(x['title'])}.</b> {e(x['detail'])}{_why(x.get('why'), f'i{i}')}{tr}</p>")
    return "".join(P)


def _narrative(data, L):
    syn = (L or {}).get("synthesis")
    P = []
    if syn and syn["narrative"]:
        P.append(f"<p>{e(syn['narrative']['text'])}{_why(syn['narrative']['why'], 'n')}</p>")
    if syn and (syn["built"]["projects"] or syn["built"]["stack"]):
        P.append("<h2>What You Built</h2>")
        if syn["built"]["projects"]:
            P.append("<ul>" + "".join(f"<li><b>{e(p['name'])}</b>: {e(p['what'])}</li>"
                                      for p in syn["built"]["projects"]) + "</ul>")
        if syn["built"]["stack"]:
            P.append(f'<p class="small">Stack: {e(", ".join(syn["built"]["stack"]))}</p>')
    if L:
        P.append(_decisions(L))
    if syn and syn["strengths"]:
        P.append("<h2>Strengths</h2><ul>" + "".join(f"<li><b>{e(x['title'])}.</b> {e(x['evidence'])}{_why(x['why'], f's{i}')}</li>"
                                                     for i, x in enumerate(syn["strengths"])) + "</ul>")
    P.append("<h2>Growth Areas</h2>")
    for i, x in enumerate((syn or {}).get("growth") or []):
        tr = f' <span class="try">Try: {e(x["try"])}</span>' if x["try"] else ""
        P.append(f"<p><b>{e(x['title'])}.</b> {e(x['evidence'])}{_why(x['why'], f'g{i}')}{tr}</p>")
    P.append(_watchpoint(data["watchpoint"]))
    return _section("Your narrative", '<div class="prose">' + "".join(P) + "</div>")


def _usage(L):
    if not L["usage"]:
        return ""
    chart = _bars([(u["name"], [(u["count"], "var(--s1)")], f'{u["count"]}', u["gloss"]) for u in L["usage"]])
    return _section("How you use AI", chart + '<div class="badges">' + "".join(
        f'<div><p class="b-name">{e(u["name"])}</p><p>{e(u["gloss"])}</p>'
        f'<p class="b-ev">{u["count"]} evidence point{"s" if u["count"] != 1 else ""}</p></div>'
        for u in L["usage"]) + "</div>")


def _axes(L):
    if not L["scores"]:
        return ""
    rows = "".join(
        f'<tr><td>{e(AXIS_LABEL[a])}</td><td class="num"><b>{v["median"]:g}</b></td>'
        f'<td class="num">{v["p25"]:g}–{v["p75"]:g}</td>'
        f'<td><span class="num">{v["high"]["score"]:g}</span> · {e(v["high"]["note"])}</td>'
        f'<td><span class="num">{v["low"]["score"]:g}</span> · {e(v["low"]["note"])}</td></tr>'
        for a, v in L["scores"].items())
    plot = ['<div class="chart"><div class="legend"><span><span class="sw" style="background:var(--s1);border-radius:50%">'
            '</span>median</span><span><span class="sw" style="background:var(--s1);opacity:.28"></span>middle half of segments'
            '</span></div>']
    for a, v in L["scores"].items():
        tip = f'Best {v["high"]["score"]:g}: {v["high"]["note"]}  ·  Weakest {v["low"]["score"]:g}: {v["low"]["note"]}'
        plot.append(f'<div class="hrow" data-tip="{e(tip)}" tabindex="0"><span class="lab">{e(AXIS_LABEL[a])}</span>'
                    f'<span class="scale"><span class="band" style="left:{v["p25"] * 10:.0f}%;width:{max(v["p75"] - v["p25"], .3) * 10:.0f}%">'
                    f'</span><span class="dot" style="left:{v["median"] * 10:.0f}%"></span></span>'
                    f'<span class="val">{v["median"]:g}</span></div>')
    plot.append('<div class="ticks"><div></div><div><span>0</span><span>5</span><span>10</span></div><div></div></div></div>')
    rows = '<details class="tbl"><summary>Table view with notes</summary><div class="scroll"><table><tr><th>axis</th>' \
           '<th>median</th><th>middle half</th><th>best segment</th><th>weakest segment</th></tr>' + rows + "</table></div></details>"
    return _section("The five axes", '<p class="small" style="margin:0 0 12px">Scored 0–10 per segment by your LLM. '
                    "Paxel computes these and sends them to YC, but doesn't show them on your report. There's no "
                    "cohort here, so no percentile. Hover a row for its best and weakest segment.</p>"
                    + "".join(plot) + rows)


def _health(quality):
    if not quality:
        return ""
    yn = lambda b: "yes" if b else "no"
    rows = "".join(
        f'<tr><td>{e(q["repo"])}</td><td class="num">{q["test_to_code"] if q["test_to_code"] is not None else "—"}</td>'
        f'<td class="num">{q["test_files"]}</td><td>{yn(q["ci"])}</td><td>{yn(q["docker"])}</td><td>{yn(q["lint"])}</td>'
        f'<td class="num">{q["files_over_500"]}</td>'
        f'<td class="num">{"—" if q["conventional_pct"] is None else str(q["conventional_pct"]) + "%"}</td>'
        f'<td class="num">{q["reverts"]}</td><td class="num">{q["agent_config_words"]:,}</td></tr>' for q in quality)
    ranked = sorted(quality, key=lambda q: -(q["test_to_code"] or 0))
    chart = ('<p class="small" style="margin:0 0 4px">Test-to-code ratio (lines of test per line of source) · '
             'hover for CI, lint and large files</p>'
             + _bars([(q["repo"], [(q["test_to_code"] or 0, "var(--s1)")],
                       "—" if q["test_to_code"] is None else f'{q["test_to_code"]:g}',
                       f'{q["test_files"]} test files · CI {yn(q["ci"])} · lint {yn(q["lint"])} · Docker {yn(q["docker"])} · '
                       f'{q["files_over_500"]} files over 500 lines · {q["reverts"]} reverts') for q in ranked]))
    return _section("Repo health", chart + '<details class="tbl"><summary>Table view</summary>'
                    '<div class="scroll"><table><tr><th>repo</th><th>test:code</th><th>test files</th>'
                    "<th>CI</th><th>Docker</th><th>lint</th><th>files &gt;500 lines</th><th>conventional</th>"
                    f"<th>reverts</th><th>agent config words</th></tr>{rows}</table></div></details>")


def render(data, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)

    h, tiles, sig = data["header"], data["tiles"], data["signals"]
    L = data.get("llm")
    syn = (L or {}).get("synthesis")
    arche = tiles[0]
    verdict = (e(syn["tagline"]["text"]) + _why(syn["tagline"]["why"], "t") if syn and syn["tagline"]
               else e(f'{arche["value"]}: {arche["caption"]}'))
    tools = " · ".join(f"{k} {v}" for k, v in sorted(sig["tools"].items()))

    P = ['<!doctype html><html lang="en"><head><meta charset="utf-8">'
         '<meta name="viewport" content="width=device-width,initial-scale=1"><title>Builder Lens</title>'
         f'<style>{CSS}</style></head><body><div class="frame"><div class="wrap">',
         f'<h1>Builder Lens <span class="sub">a local version inspired by Paxel</span></h1><p class="meta">{e(h["scope"])} · {h["sessions"]} sessions · {e(h["date"])}'
         f'{" · " + e(tools) if tools else ""}</p>',
         f'<p class="verdict">{verdict}</p>',
         _deck(tiles, sig),
         _narrative(data, L)]
    if L:
        P += [_usage(L), _axes(L)]
    else:
        P.append(_section("Not run: the LLM stage", '<ul class="pending prose">' + "".join(
            f"<li><b>{e(t)}</b>: {e(d)}</li>" for t, d in PENDING) + "</ul>"))
    P.append(_health(data["quality"]))

    x = h["excluded"]
    foot = (f'Generated locally by builder-lens. Analyzed {h["sessions_analyzed"]} of {h["sessions"]} human sessions '
            f'(the rest had no prompts). Excluded {x["automated"]} automated runs (headless <code>claude -p</code>, '
            f'SDK, <code>codex exec</code>) and {x["subagent"]} sub-agent transcripts. {sig["commits"]:,} author commits '
            f'across {len(data["quality"])} repos. Cards marked “estimate” use thresholds still being calibrated. '
            f'Raw numbers are in <code>report.json</code>.')
    if L:
        c = L["calls"]
        failed = f', {c["failed"]} failed' if c["failed"] else ""
        foot += (f' Qualitative sections by {e(L["backend"])} from redacted excerpts: {c["ok"]} of {c["segments"]} '
                 f'segments analyzed{failed}.')
    P.append(f"</div><footer>{foot}</footer></div>{FLIP_JS}</body></html>")
    path = os.path.join(out_dir, "report.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(P))
    return path
