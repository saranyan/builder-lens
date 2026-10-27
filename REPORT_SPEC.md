# builder-lens — report spec (reverse-engineered)

A local-first builder profile that parallels YC's Paxel report, worked **backwards from real
Paxel reports**. This file is the contract: every field the report shows, what we believe it
means, how we'll compute it, and how sure we are. It gets refined as more sample reports come in.

**Confidence tags:** **[K] known**: stated verbatim on a report or in Paxel's own `upload.sh` /
data-handling page. **[I] inferred**: strongly implied by sample values or captions. **[G] guess**:
our best design choice until a sample proves otherwise.

## Evidence base

Ten public reports shared by their owners, cited here only as R1–R10 (report IDs and project
names left out).

| id | scope · sessions · date | archetype | notes |
|---|---|---|---|
| R1 | one project · 9 · Aug 24 2026 | Burst Builder (65%) | 98 commits, 3 PRs |
| R2 | one project · 330 · Jul 14 2026 | Generalist | no git tiles; has thank-yous |
| R3 | All projects (4 repos) · 4,741 · Oct 9 2026 | Deep Worker (91%) | + "And what else? Velocity Machine" |
| R4 | one project · 537 · Sep 30 2026 | Deep Worker (89%) | Night owl, Biggest day |
| R5 | one project · 18 · Jun 15 2026 | Product Thinker (50%) | no git tiles |
| R6 | All projects (8 repos) · 671 · Sep 29 2026 | Generalist | Night owl, Biggest day, 4 tools |
| R7 | one project · 12 · Jun 11 2026 | Generalist | 18 tiles; "Most alive at 8 PM"; crash-out tile; old-style plan tile; domain-tagged decisions |
| R8 | one project · 45 · Jun 30 2026 | Generalist | no git tiles; **header 45 but tiles say 43 sessions**; old-style plan tile |
| R9 | one project · 854 · Oct 14 2026 | Product Thinker (46%) | 18 tiles; 4 usage patterns; pattern counts |
| R10 | one project · 29 · Oct 5 2026 | Generalist | new-style plan tile; only 1 usage pattern |

Other sources: **U** `paxel.ycombinator.com/upload.sh` (read only, never run): the 17-step
pipeline, git commands, LLM cost notes. **D** `/data-handling`: uploaded fields and vendors.
**O** obaid.wtf "How I got into YC by hacking it" (Jul 18): episode grouping, 5 axis field names.
**O2** obaid.wtf "YC Startup School '26 application: I hacked Paxel" (Jul 11): proxy and nonce
architecture, the per-episode payload, 0–10 clamping.

## Constraints for builder-lens

- **Python 3, stdlib only.** One command: `python3 builder_lens.py`.
- **The LLM step is required** (the decision made for this project). It runs through the user's own
  headless agent CLI: `claude -p --model haiku` by default (Paxel uses cloud Haiku [K/U]), with
  `codex exec` as the alternative. Both run **with no tools and no session persistence**, from
  a stable empty cwd, so they don't create transcripts that get re-ingested.
- **Local cache** of every LLM result, keyed on input hash. A re-run should be mostly cache
  hits, as Paxel's is (it reports 95%+ [K/U]).
- **Nothing is uploaded** to anyone except the user's own LLM provider, and nothing goes to us.
- **No Paxel/YC branding.** We parallel the report's *information*, not its look or name.

## Pipeline (mirrors Paxel's steps, minus auth, Docker and upload)

| # | Paxel step [K/U] | builder-lens |
|---|---|---|
| 4 | Discover projects and sessions. Tools seen on reports: `claude_code`, `codex_cli`, `cursor`, `vscode_copilot` [K/R6]; D adds opencode, Gemini CLI, Antigravity | `discover`: Claude Code, Codex, Cursor first, then the others |
| 5 | Read git history | `git`: author-filtered `log --numstat`, anchored `--author=<email>`, cap 1000 commits, window = oldest→newest session [K/U]. R4 shows "1,000 commits", so **the cap is visible in the output** |
| 6 | Parse transcripts | `parse` → normalized `Event` stream |
| 7 | Summarize each session (LLM) | `llm.summarize` (cached) |
| 8 | Group git commits by session | `link`: commit ↔ session by time window + repo |
| 9 | Group sessions into multi-day **work streams** | `streams` |
| 10 | Extract **steering traces** | `steering`: user turns that redirect, interrupt, approve or reject |
| 11 | Extract **decision exchanges** (LLM) | `llm.decisions` |
| 12 | Redact | `redact` before any LLM call |
| 13 | Link decisions to **outcomes** | `outcomes` |
| 14 | Code quality **L1 deterministic** | `repo_quality` |
| 15 | Score **episodes** across 5 axes (LLM) | `llm.score_episode` |
| 16 | Assemble report | `report.html` + `report.json` |
| — | Server side: cohort anomaly detection, embeddings, **narrative synthesis**, profile after 3+ uploads [K/U] | `llm.synthesize`, run locally. No cohort, so no percentiles. |

**Session counts** [I]: the header counts **all** discovered sessions, but tiles use a filtered
set (R8: header 45, tiles "21 of 43 sessions", "Across 43 sessions"). Two sessions were probably
dropped as empty or trivial. builder-lens shows both: header = discovered, tiles = analyzed.

**Scope** [K]: a report covers one project (shown by its folder or repo name)
or **"All projects (N repos)"** (R6). builder-lens takes `--project <name>` and defaults to all.

**Episode / work block** [K/O]: all commits in a PR → otherwise commits inside a **2-hour burst
window** → otherwise a single chat session.

**Automated sessions** [G]: exclude headless/programmatic sessions (`claude -p`, `codex exec`, SDK)
from every metric. R3's "3 prompts a session" across 4,741 sessions, and R6's go-to prompt
`@agent Continue: "Continue to iterate?"`, suggest **Paxel does *not* filter these.** We'll
filter by default and offer `--include-automated` for exact parity.

## Report layout [K, page order]

1. **Header**: `<scope> · <N> sessions · <date>`
2. **Tagline**: one second-person sentence, usually "You <core strength>, but need <growth>." (R5,
   R6). It can also be strength-only: "You turn AI velocity into shipped commerce systems, cutting
   shortcuts when they threaten product coherence." (R7)
3. **Stat tiles**: conditional, order varies (see below)
4. **Your narrative**: one or two sentences
5. **What You Built**: projects and domains, plus the tools used
6. **Decision Patterns**
7. **Strengths** (3)
8. **Growth Areas** (2–3)
9. **How you use AI**

No 1–10 scores appear on **any** of the 6 reports. See **Hidden scores**.

## Stat tiles

Tiles are **conditional** (9 to 18 per report). Git-derived tiles disappear when there's no repo
access (R2, R5). Labels and captions are reproduced exactly, so outputs compare side by side.

| tile | value / caption template | definition | evidence | conf |
|---|---|---|---|---|
| Which kind of builder are you? | `<Archetype>` / archetype caption | see **Archetypes** | all | K |
| And what else? | `<secondary archetype>` / its metric caption | shown when a **second** archetype also qualifies | R3: Velocity Machine "13.1 commits per active hour" | K |
| When are you most productive? | `Night owl` / "X% of your commits land late at night." **or** `Most alive at <H> PM` / "Your busiest stretch is around <H> PM." | Night owl when the late-night share of author commits ≥ threshold, **otherwise the peak activity hour**. **[G]** window 22:00–04:00 local, threshold 25% | R4 34%, R6 26%; peak hours R7 8 PM, R9 6 AM, R10 6 PM | I/G |
| How much did you ship? | `N lines` / "Across C commits[ and P PRs worked]." | Σ(added+deleted) over **author-filtered** commits, capped at 1000 commits [U]. The PR clause only appears when PRs > 0 | R1 33,993/98/3, R3 653,944/2,335, R4 13,328/1,000, R6 1,861,873/2,661 | I |
| How often do you plan first? | `X% of build sessions` / "a of b sessions that changed code started from a plan — a plan file, plan mode, or a plan written a session or two earlier." | b = sessions with a code edit; a = those with plan mode, a plan file read/written, or a plan in the prior 1–2 sessions. **Older variant (R7 Jun 11, R8 Jun 30):** `58% of sessions` / "You started a of b sessions from a plan before writing code.", with b = **all** sessions. Reports from Aug onward use the newer one, and so do we | R1 3/5, R3 69/394, R4 37/213, R6 41/183, R10 5/10; old: R7 7/12, R8 21/43 | K |
| How do you work with your agent? | `A back-and-forth` / "You work in dialogue, shaping the work as you go." **or** `A thinking partner` / "Detailed, context-rich prompts — you bring the agent into the problem, not just the task." | **[I] driven by average prompt length:** thinking partner at 810, 1059 and 1503 words; back-and-forth at 81–322 (7 reports). **[G]** threshold 500 words. Other labels may exist | R1–R6 | I |
| Your longest single session? | `16h 0m` / "Your deepest uninterrupted stretch with an agent." | **16h cap confirmed: all 6 reports show exactly 16h 0m.** min(longest active span, 16h) | all | K |
| How many agents do you run? | `N at once` / "As many as N main sessions running at the same time." | max overlap of **main** (non-subagent) sessions | 2, 9, 65, 12, 2, 3 | K |
| What's your go-to prompt? | `"text"` / "You sent it N times across S sessions." | most-repeated normalized prompt. **Long ones are truncated to about 40 characters with "…"** (R3). Multilingual. Only needs 2 sessions (R9 41×/2) | R3 20×/20, R4 111×/48, R9 41×/2, R10 5×/3 | K |
| What's your longest streak? | `N days straight` / "Consecutive days you shipped something." | longest run of days with ≥1 author commit | 7, 9, 10, 19 | K |
| Your biggest day? | `<Weekday>` / "Your single busiest push (N commits) landed on a <Weekday>." | the date with the most author commits, shown as its weekday | R4 Wed 166, R6 Sun 299 | K |
| How often do you change course? | `X% of the time` / "You stop and redirect the agent mid-task rather than letting it run." | (interrupts + mid-turn redirects) ÷ prompts | 1, 1, 1, 4, 12, 40% | I |
| How long are your prompts? | `N words on average` / "Mostly conversational prompts." **or** "Mostly substantive prompts." | mean words per prompt. Conversational at 81–322, substantive at 810/1503. **[G]** cut at 500, same as the working-style label. A third terse bucket is likely | all | I |
| How do you work? | `N deep sessions` / "Averaging M minutes of uninterrupted focus." | sessions whose uninterrupted stretch ≥ **90 min** (the Deep Worker caption uses 90) **[I]**. The average is **not** capped at 16h (R3 averages 1068 min), so this measure differs from "longest session" | 5/148, 10/1068, 16/382, 72/190 | I |
| How much time did you put in? | `N hours` / "Across S sessions." | Σ active time | 25/9, 460/330, 3452/4741, 929/537, 77/18, 385/671 | I |
| Your biggest crash out? | `"text…"` / "We've all been there." | the most frustrated or heated prompt (caps, "why is it…", profanity, repeated punctuation), **truncated to about 45 characters with "…"**. **[G]** the LLM picks from heuristic candidates | R7 and R9, both cut at about 45 characters (one all caps) | K/G |
| Your most cryptic prompt? | `"text"` / "Somehow the agent knew exactly what you meant." | a short, ambiguous or typo'd prompt the agent still acted on. Multilingual. Includes `[Image #1]` markers. Typos weigh heavily: R9's pick is a misspelling of its own go-to prompt | 6 samples, all 1–5 words and most misspelled | I |
| How much do you talk to your agent? | `N prompts a session` (no caption) | prompts ÷ sessions | 17, 18, 3, 15, 35, 5 | K |
| How polite are you? | `N thank-yous` / "You thanked your agent in N of your messages." | messages with thanks. **[G]** shown when ≥ 5 | R2 150, R8 8, R9 37, R10 7 | K |
| What kind of work is it? | `Mostly features` / "F fixes and N features in your commits." **or** `Mostly fixes` / "F fixes and N features…" | conventional-commit and keyword classification of author commit subjects | R1 5/81, R4 242/193 | K |

## Archetypes [K captions]

The primary archetype is a **dominance test over work blocks or sessions**, with Generalist as the
fallback. A second archetype that qualifies shows up as "And what else?".

| archetype | caption template | evidence | threshold |
|---|---|---|---|
| **Deep Worker** | "X% of work blocks ran over 90 minutes" | R3 91%, R4 89% | **[G]** ≥ 75% (R6 had 72 deep sessions out of 671 and is **not** Deep Worker) |
| **Burst Builder** | "X% of work blocks were short bursts (under 15 min or ≤2 commits)" | R1 65% | **[G]** ≥ 60% |
| **Product Thinker** | "X% of sessions reference product decisions" | R5 50%, R9 46% | **[G]** ≥ 40% (≤ 46% confirmed). "Reference product decisions" = sessions with ≥1 `product_insight` decision. R9 beat Deep Worker despite 26 deep sessions averaging 316 min |
| **Velocity Machine** | "X commits per active hour" | R3 13.1 (secondary) | **[G]** ≥ 5 commits/active hour |
| **Generalist** | "No single working pattern dominates — you adapt your approach to the task" | R2, R6, R7, R8, R10 | fallback; the **most common** result (5 of 10). Non-qualifiers: R7 5/12 deep sessions; R10 8/29 deep; R6 72/671 deep |
| Architect, Quality Guardian, Night Owl | — | YC marketing only. Night owl is now a separate tile | unknown; still want samples |

Priority when several qualify **[G]**: the highest share relative to its threshold is primary,
and the next one is "And what else?".

## Qualitative sections (LLM)

### Tagline + narrative + What You Built [K shape]
- Tagline: one second-person sentence, "You <X>, but need <Y>."
- Narrative: one or two sentences on where the user is strongest and their next step.
- What You Built: projects and domains named from session summaries, plus a list of tools/stack
  (agent CLIs in R6; in R7 the full tech stack and services, such as Next.js, Supabase,
  Trigger.dev and Vercel).
- R2 (the earliest report) also embedded named-pattern counts in the narrative.

### Decision Patterns [K shape]
Each decision has **two independent labels** [I]:
- **Move type**, reported as "positive of total" [K/R5, R6]: `strategic_redirect` ·
  `technical_catch` · `product_insight` · `option_selection`.
- **Domain**, reported as counts [K/R7]: `architecture` · `debugging` · `product` · `scope` ·
  `quality` (R7: 44 / 19 / 8 / 4 / 3 of 80). Reports usually show only "architecture: X of N
  decisions" (R3 88/278, R4 115/246, R5 98/121, R6 50/95). R2's `product_insight` 430 /
  `architecture` 478 out of 823 add up to more than 823, so these labels can overlap.

Overall positive rate: R1 1/2, R3 32/278, R5 9/121, R7 6/80, R8 8/40; per type, e.g. R8
strategic_redirect 5/16, product_insight 3/12; R10 option_selection 4/6. R9 reports "230 tracked
decisions, all architecture". Positive rates are low across the
board (3–34%), which suggests "positive" needs **explicit** evidence of success, e.g. a passing
test, a commit that lands, or the user confirming it works.

**Named decision patterns form a fixed taxonomy.** The same names recur across unrelated users
(sometimes with counts):

| name | seen in |
|---|---|
| Enforce Safety Rails | R3 (14), R4, R6, R9 (16) |
| Challenge the Constraint | R2 (12), R4, R6 |
| Workflow from User Backwards | R2 (36), R4, R5, R7 (12), R8, R9 (51): **the most common** |
| Audit Completeness | R3 (9), R5, R9 (16), R10 |
| Catch the State Bug | R3 (4), R6 |
| Full Stop and Investigate | R4, R7 (4), R9 (32) |
| Scope Unbundling | R8 |
| Demand Full Observability | R8 |
| Resist False Simplicity | R10 |
| Kill Dead Complexity | R10 |
| Codify the Lesson | R10 |
| Reference the Working Version | R7 (4) |
| Instant Feedback or Broken | R7 (3) |
| Reject Lazy Workaround | R7 (3) |
| Trace the Stale Data | R5 |
| Follow the Reference Product | R5 |
| Demand Actionable Diagnostics | R5, R8 |
| Collapse Unnecessary Steps | R6, R8, R10 |
| Trace the Input | R6 |
| Name the Copy | R2 (86) |
| Respect the Persona | R2 (23) |
| Correct the Tool Choice | R2 (17) |

R1 shows **free-form** LLM-titled insights instead ("Option Picks Beat Architecture Redirects",
"No Visible Agent Feedback Loop": the agent recognized 0 of 2 as decisions).
**[G]** builder-lens classifies each decision into this taxonomy (count = matches) and also lets
the synthesis add 1–2 free-form insights.

Decision record schema **[G]**:
`{id, session, ts, type, tags[], pattern, user_excerpt (redacted), agent_recognized: bool,
outcome: positive|mixed|negative|unknown, outcome_evidence}`

### Strengths (3) and Growth Areas (2–3) [K shape]
Specific and evidence-cited, often with a concrete suggested rule or checkpoint.
**The standard planning watchpoint** recurs across reports (R2, R3, R4, R5) and is deterministic:
> unresolved errors per session, where an error is unresolved if it isn't followed by a passing
> test or commit in that session [K/R3 definition], compared between **planned** and **unplanned**
> sessions, **with a caveat** that planned work may be harder, so this isn't causal.

Values seen: planned 0.5 vs unplanned 1.06 (R2), 36.61 vs 30.96 (R3), 1.0 vs 0.57 (R4), 0.6 vs
0.0 (R10, 5 vs 5 sessions). There's also a **"clean planned ship"** variant [K]: a planned
session that landed a commit with < 0.5 unresolved errors (i.e. 0). R5 "0 clean planned ships,
4 unplanned contrast sessions, 4.75"; R8 "1 planned session shipped under 0.5… at least 2 clean
shipped anchors recommended for the next upload"; R9 "0 planned sessions fall below 0.5 … too early
to claim". **[I]** Below about 2 clean planned ships the report says the evidence is
insufficient instead of drawing a conclusion. We do the same.
Other deterministic inputs used in this section: test-to-code ratio, test files, CI/Docker/lint,
files over 500 lines, conventional-commit %, reverts, agent-config words (R2), and "large batches
without landing commits: N episodes" (R5).

### How you use AI [K: fixed taxonomy with evidence counts]
| pattern | gloss (verbatim) | evidence counts seen |
|---|---|---|
| Dances with Robots | "Riffs with the AI like a jam session. Ideas bounce back and forth." | 573, 33, 48, 9, 20, 11, 16, 87, 19 (**every** report) |
| Frame Breaker | "Refuses the menu. Rewrites the question before answering it." | 14, 17, 2, 4, 35 |
| Cognitive Breadth | "Thinks across product, code, scope, and process in a single session." | 7, 5, 6, 7, 5, 5, 6 (absent in R8, R10) |
| Architect's Veto | "Kills clever solutions that won't survive next quarter." | 5, 8 |

**[I]** Steering traces are classified into this taxonomy. Display threshold is low: Frame
Breaker shows with just 2 (R7), so **show any pattern with ≥2** (R9 shows all 4). R10 shows
only Dances with Robots. Only these 4 names have appeared across 10 reports, so the taxonomy may
be just these 4. Cognitive Breadth
always reads 5–7 regardless of corpus size (12 to 4,741 sessions), which suggests it's computed
over a **fixed-size sample** of sessions, not the whole corpus. Fill out the taxonomy from more
samples.

## Hidden scores
Five axes, **0–10** (clamped client-side) with free-text notes, **scored per episode** by an LLM
[K/U, O, O2, D]: `execution_leverage`, `steering`, `engineering_quality`, `product_thinking`,
`planning`. They're uploaded to YC and appear on **none** of the 10 reports. Server-side they rank
the builder **against the whole cohort**: O reports a manipulated upload briefly placing the user
in YC's "top 1%". So YC sees a percentile the user never does. **[G]** builder-lens shows the
scores, aggregated across episodes (median plus spread, with notes), so the user sees what YC
sees. We can't produce a percentile without a cohort, and we won't fake one.

Other facts about the scoring path [K/O, O2]:
- **Fixed system prompts.** The proxy is hash-guarded, so it only accepts known system prompts.
  Each LLM step is one fixed prompt template, not free-form. We do the same: versioned prompt
  files, with the prompt hash included in the cache key.
- **The per-episode payload** carries scores, axes, **vectors** (embeddings, used by the server for
  cross-session analysis [U]), a summary and a title.
- **The model is inconsistent across sources.** O/O2 say GPT-5.5 via the proxy; U says cloud Haiku
  (calibrated Apr 2026); D lists both Anthropic and OpenAI. Most likely it changed over time or
  differs per step. It doesn't matter for us: we use the user's own CLI, and model choice is a flag.
- **Upload integrity is irrelevant locally.** Paxel had to bind scores to LLM output with a nonce
  and HMAC because users could edit the upload. builder-lens has no server to deceive. Its only
  integrity need is that the report can be reproduced from the cache.

## L1 code quality (deterministic, per repo) [K list from R2 + D]
test-to-code ratio · test file count · CI config · Dockerfile · linter config · source files over
500 lines · conventional-commit % · reverts · agent-config word count (`CLAUDE.md`, `AGENTS.md`,
`.cursorrules`, …). Exclude `node_modules vendor .git build dist tmp log` [K/D].

## LLM calls (headless CLI, all cached)
1. `summarize(session)`: about 2,000 characters of behavioral summary [K/D].
2. `decisions(session excerpts)`: decision records, with type, tags, taxonomy pattern and
   agent_recognized.
3. `score_episode(episode)`: 5 axes, 1–10, plus notes.
4. `classify_usage(steering traces)`: the "How you use AI" taxonomy.
5. `synthesize(summaries + stats + decisions)`: tagline, narrative, What You Built, strengths,
   growth areas, free-form decision insights, cryptic-prompt pick.

Paxel's cost model [K/U]: about 0.85 s per session fresh with 20 parallel workers, with most time
spent in steps 1–3. **[G]** We run 4–8 parallel CLI processes and sample sessions on very large
corpora (R3 has 4,741).

## Open questions
1. The **thresholds** for each archetype, and the full list (Architect? Quality Guardian?).
2. Other working-style labels and a terse prompt-length bucket (we need a report with a short
   average prompt length).
3. The night-owl window and threshold. The thank-you tile threshold.
4. The rest of the "How you use AI" taxonomy, and its display threshold.
5. Whether course-change % uses all prompts or only mid-turn prompts (R6 has 40%).
6. The deep-session definition: why can the average (1068 min) exceed the 16h longest-session cap?

**Most useful next samples:** a report with an archetype we haven't seen; one with a **short**
average prompt length (<50 words); and **your own Paxel report** next to a builder-lens run on the
same data, for numeric calibration.
