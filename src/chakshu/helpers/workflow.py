"""The GitHub Actions workflow Chakshu adds to each repository, and the names it relies on."""

import re
from importlib import resources

from chakshu import __version__

WORKFLOW_FILE = "chakshu.yml"
WORKFLOW_PATH = f".github/workflows/{WORKFLOW_FILE}"
ACTION_REPO = "havelin-labs/chakshu"


def default_action(version: str = __version__) -> str:
    """The action the workflow runs: this repository's action.yml, at a ref matching the server.

    A released server pins its own minor version (v0.1), a tag each release moves forward, so
    patch releases reach every repo without a new pull request and the runner always speaks
    the server's protocol. Development builds track main.
    """
    release = re.fullmatch(r"(\d+)\.(\d+)\.\d+", version)
    return f"{ACTION_REPO}@v{release[1]}.{release[2]}" if release else f"{ACTION_REPO}@main"


DEFAULT_ACTION = default_action()
# Repository secrets the workflow hands to the runner. Prefixed so they never clash with the repo's own.
API_KEY_SECRET = "CHAKSHU_ANTHROPIC_API_KEY"
TOKEN_SECRET = "CHAKSHU_CLAUDE_CODE_OAUTH_TOKEN"
ACTION_PLACEHOLDER = "__CHAKSHU_ACTION__"
RUNNER_PLACEHOLDER = "__CHAKSHU_RUNS_ON__"
# GitHub-hosted by default. Self-hosted runners are picked by labels, e.g. "self-hosted, linux, x64".
DEFAULT_RUNNER = ("ubuntu-latest",)
MAX_LABELS = 10
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def parse_runner(text: str | None) -> tuple[str, ...]:
    """Runner labels from a comma- or space-separated string. Empty means the default.

    Raises ValueError for a label GitHub wouldn't accept or a list that's too long.
    """
    labels = tuple(dict.fromkeys(part for part in re.split(r"[\s,]+", text or "") if part))
    if not labels:
        return DEFAULT_RUNNER
    if len(labels) > MAX_LABELS:
        raise ValueError(f"Use at most {MAX_LABELS} runner labels.")
    bad = [label for label in labels if not LABEL_RE.match(label)]
    if bad:
        raise ValueError(f"Not a valid runner label: {', '.join(bad)}")
    return labels


def runs_on(labels: tuple[str, ...]) -> str:
    """The YAML value for `runs-on`: a bare label, or a flow list when there are several."""
    return labels[0] if len(labels) == 1 else "[" + ", ".join(labels) + "]"


def render(action: str = DEFAULT_ACTION, runner: tuple[str, ...] = DEFAULT_RUNNER) -> str:
    template = (resources.files("chakshu") / "templates" / WORKFLOW_FILE).read_text(encoding="utf-8")
    return template.replace(ACTION_PLACEHOLDER, action).replace(RUNNER_PLACEHOLDER, runs_on(runner))


def dispatch_inputs(*, run_id: str, pr: int, head_sha: str, reviewer: str, server: str) -> dict[str, str]:
    """The workflow_dispatch inputs the template declares. Actions passes them all as strings."""
    return {"run_id": run_id, "pr": str(pr), "head_sha": head_sha, "reviewer": reviewer, "server": server}


def is_chakshu_workflow(workflow_ref: str, full_name: str) -> bool:
    """True if an OIDC `workflow_ref` (owner/repo/.github/workflows/x.yml@ref) is this repo's workflow."""
    return workflow_ref.lower().startswith(f"{full_name}/{WORKFLOW_PATH}@".lower())
