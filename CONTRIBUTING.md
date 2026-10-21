# Contributing

Thanks for taking a look. A few notes to make your first change go smoothly.

## Local setup

You need Python 3.12+ and Docker.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env                 # then fill in the two required values
docker compose up -d db              # Postgres for local runs and tests
pytest
```

Run the app with `chakshu web`, or the whole stack with `docker compose up --build`.

## Code layout

```
src/chakshu/
  api/        HTTP routes. Thin: parse the request, call a service, render.
  handlers/   One module per GitHub webhook event.
  services/   Business logic that talks to the database, GitHub or the model.
  helpers/    Pure functions with no I/O. Easy to unit test.
  db/         Models, session and migrations.
  core/       Settings, logging, IDs, crypto.
  web/        Templates and static assets for the portal.
```

If you find yourself writing the same thing twice, it probably belongs in `helpers/` or a service.

## Before opening a pull request

- `ruff check . && ruff format .`
- `pytest`
- Write commit messages in the imperative ("Add webhook retry", not "Added..."), with a body that says why when it isn't obvious.
- Keep pull requests to one concern. Smaller ones get reviewed faster.
