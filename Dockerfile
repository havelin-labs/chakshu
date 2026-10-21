# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS portal
WORKDIR /portal
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# git is needed to clone pull requests for review.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 chakshu
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install .

FROM base AS dev
COPY tests ./tests
RUN pip install ".[dev]"
USER chakshu

FROM base AS runtime
COPY --from=portal /portal/dist /app/portal
ENV CHAKSHU_FRONTEND_DIR=/app/portal
USER chakshu
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
ENTRYPOINT ["chakshu"]
CMD ["web"]
