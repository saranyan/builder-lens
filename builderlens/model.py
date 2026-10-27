"""Normalized session model. Every source parser emits these; nothing downstream
knows which agent CLI a session came from."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Prompt:
    ts: datetime
    text: str
    queued: bool = False        # typed while the agent was still mid-turn (a redirect)
    context: str = ""           # tail of the agent's last message before this prompt


@dataclass
class ToolCall:
    ts: datetime
    kind: str                   # edit | shell | read | plan | agent | other
    name: str
    paths: list = field(default_factory=list)
    command: str = ""
    error: bool = False


@dataclass
class Commit:
    sha: str
    ts: datetime
    email: str
    subject: str
    added: int = 0
    deleted: int = 0
    repo: str = ""


@dataclass
class Session:
    id: str
    tool: str                   # claude_code | codex_cli
    path: str
    cwd: str = ""
    automated: bool = False     # headless / SDK / exec runs — excluded by default
    subagent: bool = False
    times: list = field(default_factory=list)      # every event timestamp, sorted at finalize
    prompts: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    interrupts: int = 0
    plan_mode: bool = False
    pr_urls: set = field(default_factory=set)
    # filled in by the pipeline
    repo: str = ""
    commits: list = field(default_factory=list)

    def finalize(self):
        self.times.sort()
        self.prompts.sort(key=lambda p: p.ts)
        self.calls.sort(key=lambda c: c.ts)
        return self

    @property
    def start(self):
        return self.times[0] if self.times else None

    @property
    def end(self):
        return self.times[-1] if self.times else None

    @property
    def edits(self):
        return [c for c in self.calls if c.kind == "edit"]
