<p align="center"><img src="brand/logo.svg" alt="Chakshu" width="260"></p>

# Chakshu

Chakshu (चक्षु, Sanskrit for "the eye") is a self-hosted pull request reviewer for GitHub.

Each team in your organization keeps its own reviewer: a folder with skills, rules and settings in one repo. Anyone with write access comments `@your-org/chakshu` on a pull request, and Chakshu runs the reviewers that cover the changed files, or `@your-org/chakshu security` to run one by name. Each one posts its own review and check. Reviews run in GitHub Actions in the pull request's own repository, so the logs are in its Actions tab, on the Claude Agent SDK with read-only tools.

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
4. Sign in with GitHub as an org owner and add an Anthropic API key or a Claude subscription token under **Settings**. Chakshu copies it into each repository's Actions secrets.
5. Create `<org>/chakshu-reviewers` from the [reviewers template](https://github.com/havelin-labs/chakshu-reviewers-template) (or copy [`templates/chakshu-reviewers`](templates/chakshu-reviewers)), then press **Sync from GitHub** on the Reviewers page.
6. Create an empty team called `chakshu` in your organization, with read access to the repos.
7. On each repository's page in the portal, press **Set up GitHub Actions** and merge the pull request it opens. It adds `.github/workflows/chakshu.yml`, the workflow reviews run in.

Comment `@<org>/chakshu` on a pull request, or press **Review** on its page in the portal.

GitHub has to reach `CHAKSHU_BASE_URL` (or `CHAKSHU_WEBHOOK_URL`) for mentions and automatic reviews to work, and Actions runners have to reach `CHAKSHU_RUNNER_URL` (or `CHAKSHU_BASE_URL`) for any review to finish. Reviews started from the portal work without webhooks.

On a laptop, neither is reachable from the internet, so Compose has two optional helpers. For webhooks, point `CHAKSHU_WEBHOOK_URL` at a smee.io channel before step 2 and start `docker compose --profile smee up -d`. For runners, start `docker compose --profile tunnel up -d`, which opens a Cloudflare quick tunnel to the portal. Copy the `https://<random>.trycloudflare.com` address from `docker compose logs tunnel` into `CHAKSHU_RUNNER_URL` and run `docker compose up -d web worker` so they pick it up. Quick tunnels get a new address each time they start, so repeat this after a restart.

## What runs

| Service | Does |
|---|---|
| `db` | Postgres 17 |
| `migrate` | Applies migrations, then exits |
| `web` | Portal, API and the GitHub webhook endpoint on port 8000 |
| `worker` | Handles webhooks and starts each queued review as a GitHub Actions run |

The review itself runs on a GitHub Actions runner in the reviewed repository. It signs in to Chakshu with the run's OIDC token, fetches the job, runs Claude and sends the findings back; Chakshu posts them. Runners must be able to reach `CHAKSHU_RUNNER_URL` (which defaults to `CHAKSHU_BASE_URL`).

## Develop

See [CONTRIBUTING.md](CONTRIBUTING.md). The design system is in [DESIGN.md](DESIGN.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
