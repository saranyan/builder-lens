"""Transcript discovery + parsing for Claude Code and Codex CLI.

Each parser turns one transcript file into a model.Session. Parsing is defensive:
a malformed line is skipped, never fatal — transcripts are written by tools that
change format often.
"""
import glob
import json
import os
import re
from datetime import datetime, timezone

from .model import Prompt, Session, ToolCall

CLAUDE_DIR = os.path.expanduser("~/.claude/projects")
CODEX_DIR = os.path.expanduser("~/.codex/sessions")

PR_RE = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")
PLAN_PATH_RE = re.compile(r"(^|/)(plans?/[^/]+\.md|[^/]*\bplan\b[^/]*\.md|PLAN[^/]*\.md)$", re.I)

# Prompts that are harness/tool injections, not something the human typed.
_INJECTED = ("<", "# AGENTS.md", "[agent-relay", "Caveat:", "This session is being continued")

_CLAUDE_EDIT = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_CLAUDE_SHELL = {"Bash", "BashOutput"}
_CLAUDE_READ = {"Read", "Grep", "Glob", "LS"}
_CLAUDE_AGENT = {"Task", "Agent"}
CONTEXT_CHARS = 600             # how much of the agent's last message to keep per prompt


def parse_ts(s):
    if not s:
        return None
    try:
        if isinstance(s, (int, float)):
            return datetime.fromtimestamp(s / 1000 if s > 1e11 else s, tz=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, OSError, OverflowError):
        return None


def _human(text):
    t = (text or "").strip()
    return bool(t) and not t.startswith(_INJECTED)


def _lines(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except ValueError:
                continue


# ---------------------------------------------------------------------------- Claude Code

def discover_claude(root=None):
    root = root or CLAUDE_DIR
    # Top-level session files only; subagent transcripts live in <session>/subagents/.
    return sorted(glob.glob(os.path.join(root, "*", "*.jsonl")))


def parse_claude(path):
    s = Session(id=os.path.splitext(os.path.basename(path))[0], tool="claude_code", path=path)
    by_id, last_text = {}, ""
    for d in _lines(path):
        ts = parse_ts(d.get("timestamp"))
        t = d.get("type")
        if t not in ("user", "assistant"):
            continue
        if ts:
            s.times.append(ts)
        if d.get("isSidechain"):
            continue
        s.cwd = s.cwd or d.get("cwd") or ""
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}
        content = msg.get("content")
        if t == "user":
            if d.get("entrypoint") == "sdk-cli" or d.get("promptSource") == "sdk":
                s.automated = True
            if d.get("permissionMode") == "plan":
                s.plan_mode = True
            if isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_result" and b.get("is_error"):
                        c = by_id.get(b.get("tool_use_id"))
                        if c:
                            c.error = True
                    elif b.get("type") == "text" and "[Request interrupted" in b.get("text", ""):
                        s.interrupts += 1
                continue
            if not isinstance(content, str) or d.get("isMeta") or d.get("isCompactSummary"):
                continue
            if d.get("promptSource") == "system":
                continue
            if "[Request interrupted" in content:
                s.interrupts += 1
                continue
            if _human(content) and ts:
                s.prompts.append(Prompt(ts, content.strip(), queued=d.get("promptSource") == "queued",
                                        context=last_text))
        else:
            for b in content or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text":
                    s.pr_urls.update(PR_RE.findall(b.get("text", "")))
                    last_text = (b.get("text") or "")[-CONTEXT_CHARS:]
                if b.get("type") != "tool_use" or not ts:
                    continue
                name, inp = b.get("name", ""), b.get("input") or {}
                inp = inp if isinstance(inp, dict) else {}
                fp = inp.get("file_path") or inp.get("notebook_path") or ""
                if name in _CLAUDE_EDIT:
                    kind = "edit"
                elif name in _CLAUDE_SHELL:
                    kind = "shell"
                elif name in _CLAUDE_READ:
                    kind = "read"
                elif name in ("ExitPlanMode", "EnterPlanMode", "TodoWrite"):
                    kind = "plan"
                elif name in _CLAUDE_AGENT:
                    kind = "agent"
                else:
                    kind = "other"
                cmd = inp.get("command", "")
                c = ToolCall(ts, kind, name, [fp] if fp else [], cmd if isinstance(cmd, str) else "")
                if name == "ExitPlanMode":
                    s.plan_mode = True
                by_id[b.get("id")] = c
                s.calls.append(c)
                s.pr_urls.update(PR_RE.findall(c.command))
    return s.finalize()


# ---------------------------------------------------------------------------- Codex CLI

def discover_codex(root=None):
    root = root or CODEX_DIR
    return sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True))


_PATCH_FILE_RE = re.compile(r"\*\*\* (?:Add|Update|Delete) File: ([^\\\n\"]+)")
_EXEC_CMD_RE = re.compile(r"exec_command\(\{\s*cmd:\s*\"((?:[^\"\\]|\\.)*)\"")
_EXIT_RE = re.compile(r'exit_code\\?"\s*:\s*([1-9]\d*)')


def parse_codex(path):
    s = Session(id=os.path.splitext(os.path.basename(path))[0], tool="codex_cli", path=path)
    by_call, last_text = {}, ""
    for i, d in enumerate(_lines(path)):
        p = d.get("payload") or {}
        ts = parse_ts(d.get("timestamp"))
        if i == 0 and d.get("type") == "session_meta":
            s.id = p.get("id") or s.id
            s.cwd = p.get("cwd") or ""
            src = p.get("source")
            s.subagent = isinstance(src, dict)            # guardian reviews, spawned threads
            s.automated = p.get("originator") == "codex_exec" or src == "exec"
            continue
        if ts and d.get("type") in ("response_item", "event_msg"):
            s.times.append(ts)
        typ = p.get("type")
        if d.get("type") == "turn_context":
            s.cwd = s.cwd or p.get("cwd") or ""
        elif typ == "task_started" and p.get("collaboration_mode_kind") == "plan":
            s.plan_mode = True
        elif typ == "turn_aborted" and p.get("reason") == "interrupted":
            s.interrupts += 1
        elif typ == "message" and p.get("role") == "user" and ts:
            text = "".join(c.get("text", "") for c in p.get("content") or [] if isinstance(c, dict))
            if _human(text):
                s.prompts.append(Prompt(ts, text.strip(), context=last_text))
        elif typ == "message" and p.get("role") == "assistant":
            text = "".join(c.get("text", "") for c in p.get("content") or [] if isinstance(c, dict))
            s.pr_urls.update(PR_RE.findall(text))
            last_text = text[-CONTEXT_CHARS:] or last_text
        elif typ in ("custom_tool_call", "function_call") and ts:
            name = p.get("name", "")
            body = p.get("input") or p.get("arguments") or ""
            body = body if isinstance(body, str) else json.dumps(body)
            if "apply_patch" in body or name == "apply_patch":
                c = ToolCall(ts, "edit", "apply_patch", _PATCH_FILE_RE.findall(body))
            elif "exec_command" in body or name in ("shell", "exec_command", "local_shell"):
                m = _EXEC_CMD_RE.search(body)
                c = ToolCall(ts, "shell", "exec_command", command=(m.group(1) if m else body)[:500])
            elif name == "update_plan":
                c = ToolCall(ts, "plan", name)
            elif name == "spawn_agent":
                c = ToolCall(ts, "agent", name)
            else:
                c = ToolCall(ts, "other", name)
            by_call[p.get("call_id")] = c
            s.calls.append(c)
        elif typ in ("custom_tool_call_output", "function_call_output"):
            c = by_call.get(p.get("call_id"))
            out = p.get("output")
            out = out if isinstance(out, str) else json.dumps(out)
            if c and ("Script failed" in out[:200] or _EXIT_RE.search(out)):
                c.error = True
            s.pr_urls.update(PR_RE.findall(out))
    return s.finalize()


def discover_all(include_automated=False, claude_root=None, codex_root=None):
    """Return (kept, stats) — kept = main human sessions with ≥1 timestamp."""
    sessions, stats = [], {"files": 0, "automated": 0, "subagent": 0, "empty": 0, "by_tool": {}}
    for parse, files in ((parse_claude, discover_claude(claude_root)),
                         (parse_codex, discover_codex(codex_root))):
        for f in files:
            stats["files"] += 1
            try:
                s = parse(f)
            except OSError:
                continue
            if s.subagent:
                stats["subagent"] += 1
                continue
            if s.automated and not include_automated:
                stats["automated"] += 1
                continue
            if not s.times:
                stats["empty"] += 1
                continue
            stats["by_tool"][s.tool] = stats["by_tool"].get(s.tool, 0) + 1
            sessions.append(s)
    sessions.sort(key=lambda s: s.start)
    return sessions, stats
