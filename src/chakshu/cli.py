"""Command line entry point: `chakshu web`, `chakshu worker`, `chakshu migrate`, `chakshu action`."""

import argparse
import asyncio
import contextlib
import logging
import sys
import uuid
from importlib import resources
from pathlib import Path

import uvicorn

from chakshu.core import crypto
from chakshu.core.config import get_settings
from chakshu.core.logging import configure_logging


def _migrate(_: argparse.Namespace) -> None:
    from alembic import command
    from alembic.config import Config

    configure_logging(get_settings().log_level)
    config = Config()
    config.set_main_option("script_location", str(resources.files("chakshu.db") / "migrations"))
    command.upgrade(config, "head")
    logging.getLogger("chakshu.migrate").info("Database schema is up to date")


def _web(args: argparse.Namespace) -> None:
    uvicorn.run(
        "chakshu.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


def _worker(_: argparse.Namespace) -> None:
    from chakshu import worker

    configure_logging(get_settings().log_level)
    crypto.require_secret_key()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(worker.run_forever())


def _action(args: argparse.Namespace) -> None:
    from chakshu.runner import main as runner

    configure_logging("INFO")
    sys.exit(asyncio.run(runner.run(args.server, uuid.UUID(args.run_id), Path(args.workspace))))


def _worker_health(_: argparse.Namespace) -> None:
    from chakshu import worker

    sys.exit(0 if worker.heartbeat_ok() else 1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="chakshu")
    commands = parser.add_subparsers(dest="command", required=True)

    web = commands.add_parser("web", help="serve the portal and webhook endpoint")
    web.add_argument("--host", default="0.0.0.0")
    web.add_argument("--port", type=int, default=8000)
    web.set_defaults(func=_web)

    commands.add_parser("worker", help="run queued reviews").set_defaults(func=_worker)
    commands.add_parser("worker-health", help="exit 0 if the worker is alive").set_defaults(
        func=_worker_health
    )
    commands.add_parser("migrate", help="apply database migrations").set_defaults(func=_migrate)

    action = commands.add_parser("action", help="do one review inside GitHub Actions")
    action.add_argument("--run-id", required=True)
    action.add_argument("--server", required=True, help="Chakshu URL to fetch the job from")
    action.add_argument("--workspace", default="chakshu-workspace", help="folder with the PR in code/")
    action.set_defaults(func=_action)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
