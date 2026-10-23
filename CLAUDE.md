# Working on Chakshu

Notes for anyone (person or coding agent) changing this repository. CONTRIBUTING.md covers local setup; DESIGN.md covers the portal's look.

## How we work

- One issue, one branch, one pull request. Never commit to `main`.
- Commit messages: `type: short summary` (feat, fix, refactor, test, docs, ci, chore), lowercase, imperative, no scope, with a body that says why when it isn't obvious. Split unrelated changes into separate commits.
- PR descriptions, README and docs are plain prose: no em dashes, no filler, no promotional tone. End the PR body with `Closes #N`.
- No AI attribution anywhere: no Co-Authored-By trailers and no "Generated with" lines in commits, PRs, issues or docs.
- Before pushing: `ruff check .`, `ruff format --check .`, `pytest -q` (needs Postgres), and in `frontend/` `npm run lint`, `npm test` and `npx tsc -b`. Merge with `gh pr merge --rebase --delete-branch` only after CI is green.
- When a PR merges, comment on its issue with what changed, any new app permissions, events or migrations, and how to test it by hand. End-to-end testing against a real GitHub org is done by the maintainers, not in CI.

## Architecture

- Python 3.12, FastAPI, SQLAlchemy 2 async with asyncpg, Alembic, Postgres 17, githubkit (REST API 2026-03-10), Claude Agent SDK. Portal: React, TypeScript, Vite, Tailwind and shadcn/ui in `frontend/`.
- Layers: `api/` routes stay thin, `services/` does I/O (GitHub, database), `helpers/` holds pure functions with no I/O, `handlers/` are webhook handlers. Keep new code in the same shape and reuse what's there.
- Docker Compose runs `db`, `migrate`, `web` and `worker`, plus optional `smee` (webhooks) and `tunnel` (runner callbacks) profiles for laptops.
- Webhooks are stored in `webhook_events` by `web` and handled by the worker. Runs are queued in `runs`; both tables are Postgres queues (`services/queue.py`).
- Reviews run in GitHub Actions in the pull request's repository:
  1. The worker dispatches `.github/workflows/chakshu.yml` (template in `src/chakshu/templates/`, helpers in `helpers/workflow.py`) and stores the Actions run ID. The run is `dispatched`.
  2. The runner (`chakshu action`, `src/chakshu/runner/`, wrapped by the root `action.yml`) signs in with the Actions OIDC token (`services/oidc.py`, `api/runner.py`), fetches the job built by `services/jobs.py`, runs the agent and posts the result or failure back. The protocol is in `runner/protocol.py`.
  3. Connector tools (Jira) run on the server; the runner only forwards calls (`connectors/bridge.py`).
  4. The server publishes as the GitHub App (`services/review_results.py`, `services/publisher.py`). The `workflow_run` webhook and a 45 minute sweep fail runs that never report back.
- Repository setup (`services/repo_setup.py`) proposes the workflow as a PR and keeps the Claude credential in repository Actions secrets (`services/actions_secrets.py`). Chakshu never pushes to a default branch: every change to a repository goes through `services/proposals.py`.
- The app's required permissions and events are `services/setup.APP_PERMISSIONS` and `APP_EVENTS`; `services/app_permissions.py` reports what an existing app or installation lacks. A feature that needs a new permission adds it there.
- Reviewers live in `<org>/chakshu-reviewers` (`reviewers/<folder>/reviewer.yaml`, `RULES.md`, `skills/<skill>/SKILL.md`, `shared/skills/`), parsed by `helpers/catalog.py` and mirrored into the `reviewers` table. The portal edits them through pull requests (`services/reviewer_editor.py`).
- IDs are deterministic UUIDv5 values from `core/ids.py`.

## Gotchas

- githubkit namespaces hold the client weakly: keep it in a variable (`client = github.app_client(creds)`) before calling `client.rest...`.
- Pass `client.rest.paginate(...)` request arguments by keyword; positional ones land in `map_func`.
- After `session.rollback()`, don't touch expired ORM objects (MissingGreenlet). Read what you need first, or re-`get` with `populate_existing=True`.
- In docker-compose.yml use `${VAR:-}`, never `${VAR:?}`: Compose interpolates every service, even ones whose profile is off.
- Ruff's line length is 110.
