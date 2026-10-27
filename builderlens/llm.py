"""Run fixed prompt templates through the user's own headless agent CLI, with a local cache.

Both CLIs run with no tools and no session persistence, from a stable empty directory, so
they can't touch the filesystem and don't write transcripts that a later run would ingest.
Every result is cached under a key that covers the backend, model, template and input, so a
re-run only pays for what changed.
"""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
from collections import Counter

BACKENDS = {"claude": "Anthropic", "codex": "OpenAI"}
DEFAULT_MODEL = {"claude": "haiku", "codex": None}     # codex: whatever the user's config picks
TIMEOUT_S = 300


class LLMUnavailable(RuntimeError):
    pass


def cache_root():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "builder-lens")


def parse_json(text):
    """The outermost JSON object in a reply, tolerating code fences and chatter around it."""
    text = (text or "").strip()
    lo, hi = text.find("{"), text.rfind("}")
    if lo == -1 or hi <= lo:
        return None
    try:
        d = json.loads(text[lo:hi + 1])
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


class LLM:
    def __init__(self, backend="claude", model=None, cache_dir=None, run=None):
        """`run(prompt) -> str` overrides the subprocess call (tests use a fake)."""
        if backend not in BACKENDS:
            raise LLMUnavailable(f"unknown backend {backend!r}; use one of {', '.join(BACKENDS)}")
        self.backend = backend
        self.model = model if model is not None else DEFAULT_MODEL[backend]
        self.cache_dir = cache_dir or cache_root()
        self.stats = Counter()
        self.last_error = ""
        self._lock = threading.Lock()
        if run:
            self._run = run
        else:
            self.exe = shutil.which(backend)
            if not self.exe:
                raise LLMUnavailable(f"`{backend}` CLI not found on PATH")
            self.work = os.path.join(tempfile.gettempdir(), "builder-lens-llm")
            os.makedirs(self.work, exist_ok=True)
            self._run = self._subprocess

    @property
    def label(self):
        return f"{self.backend}" + (f" ({self.model})" if self.model else "")

    def _cmd(self, out_file):
        if self.backend == "claude":
            cmd = [self.exe, "-p", "--output-format", "text", "--tools", "", "--no-session-persistence"]
            return cmd + (["--model", self.model] if self.model else [])
        cmd = [self.exe, "exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
               "--color", "never", "-o", out_file]
        return cmd + (["-m", self.model] if self.model else []) + ["-"]

    def _subprocess(self, prompt):
        with tempfile.TemporaryDirectory(prefix="builder-lens-out-") as tmp:
            out_file = os.path.join(tmp, "last.txt")
            p = subprocess.run(self._cmd(out_file), input=prompt, capture_output=True, text=True,
                               timeout=TIMEOUT_S, cwd=self.work)
            if self.backend == "codex" and os.path.exists(out_file):
                with open(out_file, encoding="utf-8", errors="replace") as fh:
                    return fh.read()
            if p.returncode != 0:
                raise RuntimeError((p.stderr or p.stdout or "").strip()[:300])
            return p.stdout

    def _key(self, step, prompt):
        h = hashlib.sha256(f"{self.backend}\0{self.model}\0{step}\0{prompt}".encode()).hexdigest()
        return os.path.join(self.cache_dir, step, h[:2], h + ".json")

    def ask(self, step, template, payload):
        """Return the reply's JSON object, or None if the call or the parse failed (never raises)."""
        prompt = f"{template.strip()}\n\n--- INPUT ---\n{payload}"
        path = self._key(step, prompt)
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
            with self._lock:
                self.stats["cached"] += 1
            return d
        except (OSError, ValueError):
            pass
        d, err = None, ""
        for _ in range(2):                         # one retry: malformed JSON is usually a fluke
            try:
                d = parse_json(self._run(prompt))
            except subprocess.TimeoutExpired:
                err = f"timed out after {TIMEOUT_S}s"
            except Exception as ex:                # noqa: BLE001 — any CLI failure just skips this item
                err = str(ex) or type(ex).__name__
            if d is not None:
                break
        with self._lock:
            self.stats["called"] += 1
            if d is None:
                self.stats["failed"] += 1
                self.last_error = err or "reply wasn't JSON"
        if d is not None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + f".{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(d, fh)
            os.replace(tmp, path)
        return d
