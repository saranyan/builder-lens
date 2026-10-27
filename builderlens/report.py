"""Render report.json + report.html. Everything user-derived is HTML-escaped.

Layout follows the published reports: one narrow text column, a fanned deck of stat cards,
then prose sections separated by a short centered tick. The page is fully self-contained:
no web fonts, images or scripts, so opening it makes no network requests.
"""
import json
import os
from html import escape as e

from . import skillfile

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
:root{--tint:rgba(47,111,94,.07);--display:"Iowan Old Style","Palatino Linotype",Palatino,Charter,"Book Antiqua",Georgia,serif;--bg:#fff;--ink:#111;--muted:#6b6b6b;--line:#2f6f5e;--hair:rgba(17,17,17,.10);--card:#fff;
--shadow:rgba(0,0,0,.18);--font:"Space Grotesk",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--tint:rgba(111,195,168,.09);--bg:#111312;--ink:#ecebe7;--muted:#9a9f9c;
--line:#6fc3a8;--hair:rgba(255,255,255,.12);--card:#181b1a;--shadow:rgba(0,0,0,.6)}}
:root[data-theme=dark]{--tint:rgba(111,195,168,.09);--bg:#111312;--ink:#ecebe7;--muted:#9a9f9c;--line:#6fc3a8;--hair:rgba(255,255,255,.12);
--card:#181b1a;--shadow:rgba(0,0,0,.6)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:400 16.5px/1.65 var(--font);overflow-x:clip;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
html{scroll-behavior:smooth}
.frame{max-width:1200px;margin:0 auto;min-height:100dvh;border-left:1px solid var(--line);border-right:1px solid var(--line);padding:48px 32px 64px}
@media (max-width:720px){.frame{padding:32px 16px 48px;border:0}}
.wrap{max-width:640px;margin:0 auto}
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
@media (max-width:600px){.why [role=tooltip]{position:fixed;left:16px;right:16px;bottom:16px;width:auto;transform:none}}
.why .wh{display:block;font-weight:600;margin-bottom:4px}.why .wi{display:block;padding-left:10px;text-indent:-10px;margin:0 0 4px}
.why .wi::before{content:"· "}
.meta{font-size:13px;margin:6px 0 0}
.verdict{margin:20px 0 0;max-width:600px;font:400 20px/1.5 var(--display)}
/* sections: hairline + numbered kicker + serif heading */
.sec{margin-top:72px;padding-top:28px;border-top:1px solid var(--hair);scroll-margin-top:64px}
.sec-k{font:500 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--line);margin:0 0 10px}
.sec-h{font:600 30px/1.15 var(--display);letter-spacing:-.015em;margin:0 0 8px}
.sec-d{color:var(--muted);font-size:15px;margin:0 0 24px;max-width:62ch}
.prose{max-width:64ch}.prose p{margin:0 0 16px}.prose p:last-child{margin-bottom:0}
.lead{font:400 20px/1.55 var(--display);margin:0 0 28px}
h3.sub-h{font:600 19px/1.3 var(--display);letter-spacing:-.01em;margin:36px 0 12px}
.try{color:var(--muted)}
.small{font-size:13px;color:var(--muted)}
.stack{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 0}
.chip{font-size:12.5px;border:1px solid var(--hair);border-radius:99px;padding:2px 10px;color:var(--muted)}
/* card lists (projects, strengths, growth, insights) */
.cards2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}
@media (max-width:600px){.cards2{grid-template-columns:1fr}}
.pc{border:1px solid var(--hair);border-radius:6px;padding:14px 16px;background:var(--card)}
.pc b{display:block;font:600 16px/1.3 var(--display);margin:0 0 4px}.pc span{font-size:14px;color:var(--muted);line-height:1.5}
.items{list-style:none;padding:0;margin:0;counter-reset:it}
.items li{position:relative;counter-increment:it;padding:0 0 0 44px;margin:0 0 22px}
.items li::before{content:counter(it,decimal-leading-zero);position:absolute;left:0;top:2px;font:500 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--line);letter-spacing:.06em}
.items .it-t{display:block;font:600 18px/1.3 var(--display);margin:0 0 4px}
.items p{margin:0}
.callout{margin:12px 0 0;padding:10px 14px;border-left:2px solid var(--line);background:var(--tint);border-radius:0 6px 6px 0;font-size:15px}
.callout b{font-weight:600;color:var(--line);margin-right:6px}
.watch{border:1px dashed var(--line);border-radius:6px;padding:16px 18px;margin:8px 0 0}
.watch .k{font:500 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--line);margin:0 0 8px}
.watch p{margin:0;font-size:15px}
/* agent skill: the rules as a list, plus copy/download */
.sk-actions{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px}
.btn{font:500 14px/1 var(--font);padding:9px 14px;border-radius:6px;border:1px solid var(--line);background:var(--line);color:var(--bg);
cursor:pointer;text-decoration:none}
.btn.ghost{background:transparent;color:var(--line)}
.btn:focus-visible{outline:2px solid var(--line);outline-offset:2px}
.sk-h{font:500 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:24px 0 10px}
.sk-list{list-style:none;padding:0;margin:0;border:1px solid var(--hair);border-radius:8px;background:var(--card)}
.sk-list li{padding:12px 16px;border-top:1px solid var(--hair);font-size:15px}
.sk-list li:first-child{border-top:0}
.sk-list li.avoid{box-shadow:inset 3px 0 0 var(--s2)}
/* section index, sticky under the deck */
.toc{position:sticky;top:0;z-index:150;margin:40px -16px 0;padding:10px 16px;display:flex;flex-wrap:wrap;gap:4px 18px;
background:color-mix(in srgb,var(--bg) 88%,transparent);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);border-bottom:1px solid var(--hair)}
.toc a{font-size:13px;color:var(--muted);text-decoration:none;white-space:nowrap}
.toc a span{font:500 11px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--line);margin-right:5px}
.toc a:hover{color:var(--ink)}
/* "How you use AI": a 2x2 quadrant */
.quad{display:grid;grid-template-columns:28px minmax(0,1fr) minmax(0,1fr);grid-template-rows:auto 1fr 1fr;gap:8px}
.qx{font:500 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);text-align:center;padding:4px 0}
.qy{writing-mode:vertical-rl;transform:rotate(180deg);font:500 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);text-align:center}
.qc{border:1px solid var(--hair);border-radius:8px;padding:16px 16px 14px;background:var(--card);display:flex;flex-direction:column;gap:6px;min-height:170px}
.qc.top{border-color:var(--line);box-shadow:0 0 0 1px var(--line) inset}
.qc.off{opacity:.55}
.qc .qn{font:600 18px/1.25 var(--display)}
.qc .qg{font-size:14px;line-height:1.5;color:var(--muted);flex:1}
.qc .qv{display:flex;align-items:baseline;gap:8px;font-size:13px;color:var(--muted)}
.qc .qv b{font:600 28px/1 var(--display);color:var(--ink);font-variant-numeric:tabular-nums}
.qbar{height:4px;border-radius:2px;background:var(--grid);overflow:hidden}.qbar i{display:block;height:100%;background:var(--s1);border-radius:2px}
.qtag{display:none;font-size:11.5px;color:var(--line)}
@media (max-width:600px){.quad{grid-template-columns:minmax(0,1fr) minmax(0,1fr);grid-template-rows:auto}.qx,.qy,.qcorner{display:none}.qc{min-height:0}.qtag{display:block}}
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


SECTIONS = []      # (id, number, title) in page order, filled as sections render, read by the index


def _section(title, inner, sid, desc=""):
    n = f"{len(SECTIONS) + 1:02d}"
    SECTIONS.append((sid, n, title))
    d = f'<p class="sec-d">{desc}</p>' if desc else ""
    return (f'<section class="sec" id="{sid}"><p class="sec-k">{n}</p><h2 class="sec-h">{e(title)}</h2>{d}{inner}</section>')


def _toc():
    return '<nav class="toc" aria-label="Sections">' + "".join(
        f'<a href="#{sid}"><span>{n}</span>{e(t)}</a>' for sid, n, t in SECTIONS) + "</nav>"


def _watchpoint(w):
    if not (w["planned_sessions"] or w["unplanned_sessions"]):
        body = "No sessions changed code, so there's nothing to compare yet."
    else:
        f = lambda x: "—" if x is None else f"{x:.2f}"
        n = w["clean_planned_ships"]
        tail = ("Planned work may have been harder, so this doesn't show that planning caused the difference."
                if w["conclusive"] else
                f"With {n} clean planned ship{'s' if n != 1 else ''} (planned, committed, zero unresolved errors), "
                "it's too early to say whether planning gives you cleaner finishes; you need at least 2 to compare.")
        body = (f"Unresolved errors per session, meaning errors not followed by a passing test or commit in that "
                f"session. Your {w['planned_sessions']} planned build sessions averaged "
                f"<b>{f(w['planned_unresolved_per_session'])}</b>, against "
                f"<b>{f(w['unplanned_unresolved_per_session'])}</b> across {w['unplanned_sessions']} without a plan. "
                f"{e(tail)}")
    return f'<div class="watch"><p class="k">Planning watchpoint</p><p>{body}</p></div>'


def _try(x):
    return f'<p class="callout"><b>Try</b>{e(x["try"])}</p>' if x.get("try") else ""


def _items(xs, prefix):
    return '<ol class="items">' + "".join(
        f'<li><span class="it-t">{e(x["title"])}</span><p>{e(x.get("evidence") or x.get("detail") or "")}'
        f'{_why(x.get("why"), f"{prefix}{i}")}</p>{_try(x)}</li>' for i, x in enumerate(xs)) + "</ol>"


def _narrative(L):
    syn = (L or {}).get("synthesis")
    if not syn:
        return ""
    P = []
    if syn["narrative"]:
        P.append(f'<p class="lead">{e(syn["narrative"]["text"])}{_why(syn["narrative"]["why"], "n")}</p>')
    if syn["built"]["projects"]:
        P.append('<h3 class="sub-h">What you built</h3><div class="cards2">' + "".join(
            f'<div class="pc"><b>{e(p["name"])}</b><span>{e(p["what"])}</span></div>' for p in syn["built"]["projects"])
            + "</div>")
    if syn["built"]["stack"]:
        P.append('<div class="stack">' + "".join(f'<span class="chip">{e(x)}</span>' for x in syn["built"]["stack"]) + "</div>")
    return _section("Your narrative", '<div class="prose">' + "".join(P) + "</div>", "narrative") if P else ""


def _decisions(L):
    d = L["decisions"]
    if not d["total"]:
        return ""
    P = []
    kinds = sorted(((t, v) for t, v in d["by_type"].items() if v["total"]), key=lambda x: -x[1]["total"])
    P.append('<h3 class="sub-h" style="margin-top:0">By kind</h3>')
    P.append(_bars([(TYPE_LABEL[t].capitalize(), [(v["positive"], "var(--s1)"), (v["total"] - v["positive"], "var(--s2)")],
                     f"{v['positive']} of {v['total']}", f"{v['positive']} proven, {v['total'] - v['positive']} unproven")
                    for t, v in kinds], legend=[("proven to work", "var(--s1)"), ("unproven", "var(--s2)")]))
    if d["domains"]:
        P.append('<h3 class="sub-h">By area</h3><p class="small" style="margin:-6px 0 8px">A decision can carry two areas.</p>')
        P.append(_bars([(k.capitalize(), [(v, "var(--s1)")], f"{v}", "") for k, v in d["domains"].items()]))
    if d["patterns"]:
        P.append('<h3 class="sub-h">Named patterns</h3><p class="small" style="margin:-6px 0 8px">Hover a row for an example.</p>')
        P.append(_bars([(x["name"], [(x["count"], "var(--s1)")], f"{x['count']}",
                         f"e.g. {x['examples'][0]}" if x["examples"] else "") for x in d["patterns"][:8]]))
    ins = (L.get("synthesis") or {}).get("insights") or []
    if ins:
        P.append('<h3 class="sub-h">What stands out</h3>' + _items(ins, "i"))
    desc = (f"{d['total']} moments where you made a real call about the work. {d['positive']} have proof they worked "
            "(a passing check, a matching commit, or you confirming it); the rest are unproven, not failed.")
    return _section("Decision patterns", "".join(P), "decisions", e(desc))


def _strengths_growth(data, L):
    syn = (L or {}).get("synthesis") or {}
    out = []
    if syn.get("strengths"):
        out.append(_section("Strengths", _items(syn["strengths"], "s"), "strengths",
                            "Each one cites the measured facts behind it. Hover <i>why</i>."))
    growth = _items(syn["growth"], "g") if syn.get("growth") else ""
    out.append(_section("Growth areas", growth + _watchpoint(data["watchpoint"]), "growth",
                        "Specific, with something to try in your next session."))
    return "".join(out)


COPY_JS = """<script>
(function () {
  var b = document.getElementById('sk-copy'), src = document.getElementById('sk-src');
  if (!b || !src) return;
  b.addEventListener('click', function () {
    function done() { b.textContent = 'Copied'; setTimeout(function () { b.textContent = 'Copy SKILL.md'; }, 1600); }
    if (navigator.clipboard) { navigator.clipboard.writeText(src.value).then(done, fallback); } else { fallback(); }
    function fallback() { src.hidden = false; src.select(); document.execCommand('copy'); src.hidden = true; done(); }
  });
})();
</script>"""


def _skill(L, header):
    sk = L.get("skill")
    if not sk:
        return ""

    def lst(items, cls=""):
        return '<ul class="sk-list">' + "".join(
            f'<li class="{cls}">{e(x["text"])}{_why(x["why"], f"k{cls}{i}")}</li>' for i, x in enumerate(items)) + "</ul>"

    inner = ['<div class="sk-actions"><button class="btn" id="sk-copy" type="button">Copy SKILL.md</button>'
             f'<a class="btn ghost" href="skill/{skillfile.SKILL_NAME}/SKILL.md" download>Download for Claude Code</a>'
             '<a class="btn ghost" href="skill/AGENTS.md" download>Download for Codex (AGENTS.md)</a></div>',
             f'<textarea id="sk-src" hidden readonly>{e(skillfile.skill_md(sk, header))}</textarea>']
    if sk["rules"]:
        inner.append('<p class="sk-h">Do</p>' + lst(sk["rules"]))
    if sk["avoid"]:
        inner.append('<p class="sk-h">Avoid</p>' + lst(sk["avoid"], "avoid"))
    if sk["communication"]:
        inner.append('<p class="sk-h">How you communicate</p>' + lst(sk["communication"]))
    return _section("Your agent skill", "".join(inner), "skill",
                    "Instructions for your coding agents, written from this report: when to ask for a plan, how to "
                    "show verification, how you steer. Every one cites the facts it's based on. Run with "
                    "<code>--install-skill</code> to add it to Claude Code.")


# The quadrant: x = expand ideas vs constrain them; y = in a single moment vs across the work.
QUAD = [("dances_with_robots", "Expand · in the moment"), ("frame_breaker", "Constrain · in the moment"),
        ("cognitive_breadth", "Expand · across the work"), ("architects_veto", "Constrain · across the work")]


def _usage(L):
    allu = {u["key"]: u for u in L.get("usage_all") or [dict(u, shown=True) for u in L["usage"]]}
    if not allu:
        return ""
    # breadth counts sessions out of a sample; the others count evidence points, so they share a scale
    top = max((u["count"] for k, u in allu.items() if k != "cognitive_breadth"), default=0) or 1
    lead = max((u for k, u in allu.items() if k != "cognitive_breadth"), key=lambda u: u["count"])["key"]

    def cell(key, tag):
        u = allu.get(key, {"name": key, "gloss": "", "count": 0, "shown": False})
        sample = L.get("breadth_sample") or 10
        breadth = key == "cognitive_breadth"
        unit = f"in {u['count']} of {sample} sampled sessions" if breadth else "evidence points"
        width = 100 * u["count"] / (sample if breadth else top)
        cls = "qc" + (" top" if key == lead and u["shown"] else "") + ("" if u["shown"] else " off")
        val = (f'<span class="qv"><b>{u["count"]}</b>{e(unit)}</span>' if u["shown"]
               else '<span class="qv">not seen yet</span>')
        return (f'<div class="{cls}"><span class="qtag">{e(tag)}</span><span class="qn">{e(u["name"])}</span>'
                f'<span class="qg">{e(u["gloss"])}</span>{val}'
                f'<span class="qbar"><i style="width:{min(width, 100):.0f}%"></i></span></div>')

    grid = ('<div class="quad" role="group" aria-label="How you use AI, by expanding or constraining ideas and by '
            'moment or across the work"><span class="qcorner"></span><span class="qx">Expand ideas</span>'
            '<span class="qx">Constrain ideas</span><span class="qy">In the moment</span>'
            + cell(*QUAD[0]) + cell(*QUAD[1]) + '<span class="qy">Across the work</span>' + cell(*QUAD[2])
            + cell(*QUAD[3]) + "</div>")
    return _section("How you use AI", grid, "ai",
                    "Four ways builders work with agents, placed by whether they open ideas up or narrow them down, "
                    "and whether it happens turn by turn or across a whole project.")


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
    return _section("The five axes", "".join(plot) + rows, "axes",
                    "Scored 0–10 per segment by your LLM. Paxel computes these and sends them to YC, but doesn't "
                    "show them on your report. There's no cohort here, so no percentile. Hover a row for its best "
                    "and weakest segment.")


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
    chart = (_bars([(q["repo"], [(q["test_to_code"] or 0, "var(--s1)")],
                       "—" if q["test_to_code"] is None else f'{q["test_to_code"]:g}',
                       f'{q["test_files"]} test files · CI {yn(q["ci"])} · lint {yn(q["lint"])} · Docker {yn(q["docker"])} · '
                       f'{q["files_over_500"]} files over 500 lines · {q["reverts"]} reverts') for q in ranked]))
    return _section("Repo health", chart + '<details class="tbl"><summary>Table view</summary>'
                    '<div class="scroll"><table><tr><th>repo</th><th>test:code</th><th>test files</th>'
                    "<th>CI</th><th>Docker</th><th>lint</th><th>files &gt;500 lines</th><th>conventional</th>"
                    f"<th>reverts</th><th>agent config words</th></tr>{rows}</table></div></details>", "health",
                    "Test-to-code ratio: lines of test per line of source. Hover a repo for CI, lint and large files.")


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
         _deck(tiles, sig)]
    SECTIONS.clear()
    body = []
    if L:
        body += [_narrative(L), _decisions(L), _strengths_growth(data, L), _usage(L), _axes(L), _skill(L, h)]
    else:
        body.append(_section("Not run: the LLM stage", '<ul class="pending prose">' + "".join(
            f"<li><b>{e(t)}</b>: {e(d)}</li>" for t, d in PENDING) + "</ul>", "pending"))
        body.append(_strengths_growth(data, None))
    body.append(_health(data["quality"]))
    P += [_toc()] + body

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
    P.append(f"</div><footer>{foot}</footer></div>{FLIP_JS}{COPY_JS}</body></html>")
    path = os.path.join(out_dir, "report.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(P))
    return path
