"""The GitHub Actions workflow Chakshu adds to each repository, and the names it relies on."""

from importlib import resources

WORKFLOW_FILE = "chakshu.yml"
WORKFLOW_PATH = f".github/workflows/{WORKFLOW_FILE}"
# The action the workflow runs: this repository's action.yml.
DEFAULT_ACTION = "havelin-labs/chakshu@main"
# Repository secrets the workflow hands to the runner. Prefixed so they never clash with the repo's own.
API_KEY_SECRET = "CHAKSHU_ANTHROPIC_API_KEY"
TOKEN_SECRET = "CHAKSHU_CLAUDE_CODE_OAUTH_TOKEN"
ACTION_PLACEHOLDER = "__CHAKSHU_ACTION__"


def render(action: str = DEFAULT_ACTION) -> str:
    template = (resources.files("chakshu") / "templates" / WORKFLOW_FILE).read_text(encoding="utf-8")
    return template.replace(ACTION_PLACEHOLDER, action)


def dispatch_inputs(*, run_id: str, pr: int, head_sha: str, reviewer: str, server: str) -> dict[str, str]:
    """The workflow_dispatch inputs the template declares. Actions passes them all as strings."""
    return {"run_id": run_id, "pr": str(pr), "head_sha": head_sha, "reviewer": reviewer, "server": server}


def is_chakshu_workflow(workflow_ref: str, full_name: str) -> bool:
    """True if an OIDC `workflow_ref` (owner/repo/.github/workflows/x.yml@ref) is this repo's workflow."""
    return workflow_ref.lower().startswith(f"{full_name}/{WORKFLOW_PATH}@".lower())
