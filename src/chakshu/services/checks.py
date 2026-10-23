"""One GitHub check run per reviewer: "Chakshu · <reviewer>"."""

from githubkit import GitHub

from chakshu.core.config import get_settings
from chakshu.helpers.urls import is_public_url

TITLE_LIMIT = 250
SUMMARY_LIMIT = 60_000


def check_name(reviewer: str) -> str:
    return f"Chakshu · {reviewer}"


def details_url(run_id: str) -> str | None:
    url = f"{get_settings().base_url}/runs/{run_id}"
    return url if is_public_url(url) else None


async def start(client: GitHub, full_name: str, head_sha: str, reviewer: str, run_id: str) -> int:
    owner, repo = full_name.split("/", 1)
    extra = {"details_url": url} if (url := details_url(run_id)) else {}
    resp = await client.rest.checks.async_create(
        owner,
        repo,
        name=check_name(reviewer),
        head_sha=head_sha,
        status="in_progress",
        external_id=run_id,
        **extra,
    )
    return resp.parsed_data.id


async def link_actions_run(client: GitHub, full_name: str, check_id: int, url: str) -> None:
    """Point the check's Details link at the Actions run, where the logs are."""
    owner, repo = full_name.split("/", 1)
    await client.rest.checks.async_update(
        owner,
        repo,
        check_id,
        details_url=url,
        output={
            "title": "Reviewing in GitHub Actions",
            "summary": f"The review is running in GitHub Actions. [Open the run for its logs]({url}).",
        },
    )


async def finish(
    client: GitHub, full_name: str, check_id: int, *, conclusion: str, title: str, summary: str
) -> None:
    owner, repo = full_name.split("/", 1)
    await client.rest.checks.async_update(
        owner,
        repo,
        check_id,
        status="completed",
        conclusion=conclusion,
        output={"title": title[:TITLE_LIMIT], "summary": summary[:SUMMARY_LIMIT]},
    )
