# Contributing

Thanks for taking a look. A few notes to make your first change go smoothly.

## Local setup

You need Python 3.12+, Node 22 and Docker.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env                 # then fill in the two required values
# Postgres on localhost:5433 for local runs and tests:
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db
pytest
```

Tip: add `COMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml` to your `.env` (use `;` on Windows) so plain `docker compose` commands keep the dev port.

Run the API with `chakshu web` and the portal with `cd frontend && npm install && npm run dev` (Vite proxies API calls to port 8000). Or run everything with `docker compose up --build`.

## Code layout

```
src/chakshu/
  api/        HTTP routes. Thin: parse the request, call a service, return JSON.
  handlers/   One module per GitHub webhook event.
  services/   Business logic that talks to the database, GitHub or the model.
  helpers/    Pure functions with no I/O. Easy to unit test.
  db/         Models, session and migrations.
  core/       Settings, logging, IDs, crypto.
frontend/     React + TypeScript portal (Vite, Tailwind, shadcn/ui).
  src/pages/       One file per screen.
  src/components/  Shared layout; ui/ holds shadcn components.
  src/lib/         API client and small utilities.
```

If you find yourself writing the same thing twice, it probably belongs in `helpers/` or a service.

## Before opening a pull request

- `ruff check . && ruff format .`
- `pytest`
- `cd frontend && npm run lint && npm test && npm run build`
- Write commit messages in the imperative ("Add webhook retry", not "Added..."), with a body that says why when it isn't obvious.
- Keep pull requests to one concern. Smaller ones get reviewed faster.
