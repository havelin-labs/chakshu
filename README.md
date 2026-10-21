<p align="center"><img src="brand/logo.svg" alt="Chakshu" width="260"></p>

# Chakshu

Chakshu (चक्षु, Sanskrit for "the eye") is a self-hosted pull request reviewer for GitHub.

Each team in your organization keeps its own reviewer: a folder with skills, rules and settings in one repo. Anyone on that team comments `@your-org/chakshu` on a pull request, and Chakshu runs the reviewers that belong to them and fit the change. Each one posts its own review and check. Reviews run on the Claude Agent SDK with read-only tools.

Docs: https://chakshu.havelin.in/docs

## Run it

You need Docker with Compose, admin rights in a GitHub organization, and an Anthropic API key.

```bash
git clone https://github.com/havelin-labs/chakshu.git && cd chakshu
cp .env.example .env
# set CHAKSHU_SECRET_KEY, POSTGRES_PASSWORD and CHAKSHU_BASE_URL in .env
docker compose up -d --build --wait
docker compose logs web | grep "Setup code"
```

Then open `CHAKSHU_BASE_URL` in a browser:

1. Enter the setup code from the logs.
2. Name the GitHub App, pick your organization and click **Create on GitHub**.
3. Install the app on the repos you want reviewed, plus your reviewers repo.
4. Sign in with GitHub as an org owner and add your Anthropic API key under **Settings**.
5. Create `<org>/chakshu-reviewers` from [`templates/chakshu-reviewers`](templates/chakshu-reviewers) and press **Sync from GitHub** on the Reviewers page.
6. Create an empty team called `chakshu` in your organization, with read access to the repos.

Comment `@<org>/chakshu` on a pull request, or press **Review** on its page in the portal.

GitHub has to reach `CHAKSHU_BASE_URL` (or `CHAKSHU_WEBHOOK_URL`) for mentions and automatic reviews to work. On a laptop, point `CHAKSHU_WEBHOOK_URL` at a smee.io channel before step 2. Reviews started from the portal work without webhooks.

## What runs

| Service | Does |
|---|---|
| `db` | Postgres 17 |
| `migrate` | Applies migrations, then exits |
| `web` | Portal, API and the GitHub webhook endpoint on port 8000 |
| `worker` | Claims queued reviews and runs them (`CHAKSHU_WORKER_CONCURRENCY` at a time) |

## Develop

See [CONTRIBUTING.md](CONTRIBUTING.md). The design system is in [DESIGN.md](DESIGN.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
