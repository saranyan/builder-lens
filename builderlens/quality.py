"""L1 deterministic code-quality signals per repo (the numbers Paxel cites in Growth Areas)."""
import os
import re

from .gitdata import tracked_files

EXCLUDE_DIRS = {"node_modules", "vendor", ".git", "build", "dist", "tmp", "log"}   # [data-handling]
SOURCE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".rb", ".java",
              ".kt", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".php", ".scala", ".ex",
              ".exs", ".dart", ".vue", ".svelte", ".sh", ".lua", ".m", ".sql"}
TEST_RE = re.compile(r"(^|/)(tests?|spec|__tests__)/|(^|/)test_[^/]+$|_test\.[^/]+$|\.(test|spec)\.[^/]+$", re.I)
CI_RE = re.compile(r"^(\.github/workflows/|\.gitlab-ci\.yml$|\.circleci/|azure-pipelines\.yml$|"
                   r"Jenkinsfile$|\.buildkite/|bitbucket-pipelines\.yml$)")
DOCKER_RE = re.compile(r"(^|/)(Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|compose\.ya?ml)$")
LINT_RE = re.compile(r"(^|/)(\.eslintrc[^/]*|eslint\.config\.[^/]+|\.flake8|ruff\.toml|\.ruff\.toml|"
                     r"\.pylintrc|\.golangci[^/]*|\.prettierrc[^/]*|biome\.jsonc?|\.rubocop\.yml|"
                     r"\.stylelintrc[^/]*|clippy\.toml|\.swiftlint\.yml)$")
AGENT_CFG_RE = re.compile(r"(^|/)(CLAUDE\.md|AGENTS\.md|GEMINI\.md|\.cursorrules|"
                          r"\.github/copilot-instructions\.md|\.cursor/rules/[^/]+)$")
CONVENTIONAL_RE = re.compile(r"^(feat|fix|chore|docs|refactor|test|tests|perf|build|ci|style|revert)"
                             r"(\([^)]*\))?!?:", re.I)
MAX_FILES = 20000


def _lines(path):
    try:
        if os.path.getsize(path) > 2_000_000:
            return 0
        with open(path, "rb") as fh:
            return fh.read().count(b"\n")
    except OSError:
        return 0


def _words(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return len(fh.read().split())
    except OSError:
        return 0


def repo_quality(repo, commits):
    files = [f for f in tracked_files(repo)[:MAX_FILES]
             if not EXCLUDE_DIRS.intersection(f.split("/")[:-1])]
    test_loc = src_loc = test_files = 0
    big = []
    for f in files:
        if os.path.splitext(f)[1].lower() not in SOURCE_EXT:
            continue
        n = _lines(os.path.join(repo, f))
        if TEST_RE.search(f):
            test_files += 1
            test_loc += n
        else:
            src_loc += n
            if n > 500:
                big.append(f)
    subjects = [c.subject for c in commits]
    return {
        "repo": os.path.basename(repo),
        "test_to_code": round(test_loc / src_loc, 2) if src_loc else None,
        "test_files": test_files,
        "source_loc": src_loc,
        "ci": any(CI_RE.search(f) for f in files),
        "docker": any(DOCKER_RE.search(f) for f in files),
        "lint": any(LINT_RE.search(f) for f in files) or _pyproject_lint(repo),
        "files_over_500": len(big),
        "conventional_pct": round(100 * sum(bool(CONVENTIONAL_RE.match(s)) for s in subjects) / len(subjects))
        if subjects else None,
        "reverts": sum(s.lower().startswith("revert") for s in subjects),
        "agent_config_words": sum(_words(os.path.join(repo, f)) for f in files if AGENT_CFG_RE.search(f)),
    }


def _pyproject_lint(repo):
    try:
        with open(os.path.join(repo, "pyproject.toml"), encoding="utf-8", errors="replace") as fh:
            return bool(re.search(r"^\[tool\.(ruff|pylint|flake8|black|mypy)", fh.read(), re.M))
    except OSError:
        return False
