"""Database tables.

Primary keys are deterministic UUIDs from chakshu.core.ids, computed by the
code that creates the row. Reviewer content (skills, rules) stays in GitHub;
the `reviewers` table only caches the parsed reviewer.yaml.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from chakshu.db.base import Base, TimestampMixin


class Setting(Base, TimestampMixin):
    """Key/value settings edited in the portal. Secret values are encrypted."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)


class Installation(Base, TimestampMixin):
    __tablename__ = "installations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    account_github_id: Mapped[int] = mapped_column(BigInteger)
    account_login: Mapped[str] = mapped_column(String(100))
    account_type: Mapped[str] = mapped_column(String(20))  # Organization | User
    suspended: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    login: Mapped[str] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    token_enc: Mapped[str | None] = mapped_column(Text)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Repo(Base, TimestampMixin):
    __tablename__ = "repos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    installation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("installations.id", ondelete="CASCADE"))
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    default_branch: Mapped[str] = mapped_column(String(200), default="main")
    private: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Reviewer(Base, TimestampMixin):
    """Cache of one folder in the reviewers repo."""

    __tablename__ = "reviewers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    installation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("installations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    product: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    owner_team: Mapped[str] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    repos: Mapped[list[str]] = mapped_column(JSONB, default=list)
    paths: Mapped[list[str]] = mapped_column(JSONB, default=list)
    auto: Mapped[list[str]] = mapped_column(JSONB, default=list)
    skills: Mapped[list[str]] = mapped_column(JSONB, default=list)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    connectors: Mapped[list[str]] = mapped_column(JSONB, default=list)
    rules: Mapped[str | None] = mapped_column(String(300))
    fail_check_on: Mapped[str | None] = mapped_column(String(20))
    source_path: Mapped[str] = mapped_column(String(300))
    source_sha: Mapped[str] = mapped_column(String(40))
    errors: Mapped[list[str]] = mapped_column(JSONB, default=list)

    __table_args__ = (Index("uq_reviewers_installation_name", "installation_id", "name", unique=True),)


class JobStatus(StrEnum):
    """Lifecycle shared by everything the worker processes (runs, webhook events).

    Runs have one extra step: the worker dispatches them to GitHub Actions and
    they stay `dispatched` until the runner reports back (or the Actions run ends).
    """

    QUEUED = "queued"
    RUNNING = "running"
    DISPATCHED = "dispatched"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


RunStatus = JobStatus


class JobMixin:
    """Queue columns shared by runs and webhook events (see services/queue.py)."""

    status: Mapped[JobStatus] = mapped_column(String(20), default=JobStatus.QUEUED)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Which worker holds the job, and when it last said it was still on it.
    worker_id: Mapped[str | None] = mapped_column(String(100))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Run(Base, JobMixin, TimestampMixin):
    """One reviewer reviewing one pull request at one commit. Doubles as the job queue."""

    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    work_key: Mapped[uuid.UUID] = mapped_column(index=True)
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviewers.id", ondelete="CASCADE"))
    pr_number: Mapped[int] = mapped_column(Integer)
    pr_title: Mapped[str | None] = mapped_column(String(500))
    head_sha: Mapped[str] = mapped_column(String(40))
    reviewer_sha: Mapped[str] = mapped_column(String(40))
    trigger: Mapped[str] = mapped_column(String(30))  # mention | review_requested | auto | portal
    requested_by: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(100))
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    review_url: Mapped[str | None] = mapped_column(String(500))
    check_run_id: Mapped[int | None] = mapped_column(BigInteger)
    # The GitHub Actions run doing the review. Only that run may fetch the job and report back.
    actions_run_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    actions_run_url: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (Index("ix_runs_status_created_at", "status", "created_at"),)


class Connector(Base, TimestampMixin):
    """An outside system reviewers can read from, set up by an admin (e.g. Jira)."""

    __tablename__ = "connectors"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)  # what reviewer.yaml refers to
    kind: Mapped[str] = mapped_column(String(30))
    base_url: Mapped[str] = mapped_column(String(300))
    username: Mapped[str | None] = mapped_column(String(200))
    secret_enc: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class FindingOutcome(StrEnum):
    OPEN = "open"
    FIXED = "fixed"
    DISMISSED = "dismissed"


class PostedFinding(Base, TimestampMixin):
    """An inline finding Chakshu posted, and what became of it. Feeds the per-skill stats."""

    __tablename__ = "posted_findings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)  # the finding's deterministic ID
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviewers.id", ondelete="CASCADE"), index=True)
    skill: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(30))
    outcome: Mapped[FindingOutcome] = mapped_column(String(20), default=FindingOutcome.OPEN)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookEvent(Base, JobMixin, TimestampMixin):
    """A GitHub webhook delivery, stored before it's handled so nothing is lost on restart.

    The primary key is GitHub's delivery ID, so redeliveries are dropped on insert.
    """

    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)

    __table_args__ = (Index("ix_webhook_events_status_created_at", "status", "created_at"),)
