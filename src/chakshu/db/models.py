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
    rules: Mapped[str | None] = mapped_column(String(300))
    fail_check_on: Mapped[str | None] = mapped_column(String(20))
    source_path: Mapped[str] = mapped_column(String(300))
    source_sha: Mapped[str] = mapped_column(String(40))
    errors: Mapped[list[str]] = mapped_column(JSONB, default=list)

    __table_args__ = (Index("uq_reviewers_installation_name", "installation_id", "name", unique=True),)


class JobStatus(StrEnum):
    """Lifecycle shared by everything the worker processes (runs, webhook events)."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


RunStatus = JobStatus


class Run(Base, TimestampMixin):
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
    status: Mapped[RunStatus] = mapped_column(String(20), default=RunStatus.QUEUED)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(100))
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    review_url: Mapped[str | None] = mapped_column(String(500))
    check_run_id: Mapped[int | None] = mapped_column(BigInteger)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_runs_status_created_at", "status", "created_at"),)


class WebhookEvent(Base, TimestampMixin):
    """A GitHub webhook delivery, stored before it's handled so nothing is lost on restart.

    The primary key is GitHub's delivery ID, so redeliveries are dropped on insert.
    """

    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[JobStatus] = mapped_column(String(20), default=JobStatus.QUEUED)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_webhook_events_status_created_at", "status", "created_at"),)
