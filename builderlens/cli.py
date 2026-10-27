import argparse
import os
import sys
import webbrowser
from datetime import date

from . import analyze, demo, gitdata, llm, metrics, quality, report, skillfile, sources


def main(argv=None):
    ap = argparse.ArgumentParser(prog="builder_lens.py",
                                 description="A local builder profile from your coding-agent transcripts.")
    ap.add_argument("--project", help="limit to one repo/project (matches the folder name)")
    ap.add_argument("--include-automated", action="store_true",
                    help="also count headless runs (claude -p, SDK, codex exec) — Paxel doesn't filter these")
    ap.add_argument("--out", default="out", help="output directory (default: ./out)")
    ap.add_argument("--no-open", action="store_true", help="don't open the report in a browser")
    ap.add_argument("--llm", choices=sorted(llm.BACKENDS), default="claude",
                    help="headless CLI for the qualitative stage (default: claude)")
    ap.add_argument("--model", help="model for --llm (default: haiku for claude, your config for codex)")
    ap.add_argument("--workers", type=int, default=4, help="parallel LLM calls (default: 4)")
    ap.add_argument("--no-llm", action="store_true", help="skip the LLM stage: deterministic stats only")
    ap.add_argument("--install-skill", action="store_true",
                    help=f"also install the generated agent skill to ~/.claude/skills/{skillfile.SKILL_NAME}/")
    ap.add_argument("--demo", action="store_true",
                    help="render a report for a made-up builder: no transcripts read, nothing sent anywhere")
    args = ap.parse_args(argv)

    if args.demo:
        data = demo.data()
        path = report.render(data, args.out)
        files = skillfile.write(data["llm"]["skill"], data["header"], args.out)
        print(f"Demo report (made-up data): {path}\nDemo agent skill: {files['skill']}")
        if not args.no_open:
            webbrowser.open("file://" + os.path.abspath(path))
        return 0

    runner = None
    if not args.no_llm:
        try:
            runner = llm.LLM(args.llm, args.model)
        except llm.LLMUnavailable as ex:
            print(f"The LLM stage needs a headless agent CLI: {ex}.\n"
                  f"Install it, pick the other one with --llm, or run with --no-llm for stats only.")
            return 2

    print("Reading transcripts…", flush=True)
    sessions, st = sources.discover_all(include_automated=args.include_automated)
    for s in sessions:
        s.repo = gitdata.toplevel(s.cwd)
    if args.project:
        want = args.project.lower()
        sessions = [s for s in sessions if want in {os.path.basename(s.repo).lower(), os.path.basename(s.cwd).lower()}]
    if not sessions:
        print("No sessions found" + (f" for project {args.project!r}" if args.project else "") + ".")
        return 1

    repos = sorted({s.repo for s in sessions if s.repo})
    emails = gitdata.user_emails(repos)
    print(f"  {len(sessions)} human sessions · {st['automated']} automated + {st['subagent']} sub-agent excluded "
          f"· {len(repos)} repos · author emails: {', '.join(sorted(emails)) or 'none found'}", flush=True)
    print("Reading git history…", flush=True)
    since, until = sessions[0].start, max(s.end for s in sessions)
    commits, qual = [], []
    for r in repos:
        cs = gitdata.author_commits(r, emails, since, until)
        commits += cs
        qual.append(quality.repo_quality(r, cs))

    header = {
        "scope": args.project or (f"All projects ({len(repos)} repos)" if len(repos) != 1 else os.path.basename(repos[0])),
        "sessions": len(sessions),
        "date": date.today().strftime("%b %-d, %Y") if sys.platform != "win32" else date.today().isoformat(),
        "excluded": {"automated": st["automated"], "subagent": st["subagent"]},
    }
    data = metrics.compute(sessions, commits, qual, header)
    if runner:
        print(f"Running the LLM stage: redacted transcript excerpts go to {llm.BACKENDS[args.llm]} via your "
              f"`{args.llm}` CLI (no tools, not persisted). Cache: {runner.cache_dir}", flush=True)
        data["llm"] = analyze.run(runner, [s for s in sessions if s.prompts], data, workers=args.workers)
        c = data["llm"]["calls"]
        print(f"  {c['ok']}/{c['segments']} segments analyzed · {c['cached']} cached · {c['called']} new calls"
              + (f" · {c['failed']} failed (last error: {c['last_error']})" if c["failed"] else ""))
    path = report.render(data, args.out)
    a = data["tiles"][0]
    print(f"\n  {a['value']} — {a['caption']}")
    for t in data["tiles"][1:]:
        print(f"  · {t['question']:<38} {t['value']}")
    print(f"\nWrote {path} and report.json")
    sk = (data.get("llm") or {}).get("skill")
    if sk:
        files = skillfile.write(sk, data["header"], args.out)
        print(f"Agent skill: {files['skill']}\n  Codex: paste {files['agents']} into AGENTS.md")
        if args.install_skill:
            print(f"  Installed for Claude Code: {skillfile.install(files['skill'])}")
        else:
            print("  Install it for Claude Code with --install-skill")
    if not args.no_open:
        webbrowser.open("file://" + os.path.abspath(path))
    return 0
