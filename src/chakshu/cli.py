"""Command line entry point: `chakshu web`, `chakshu worker`, `chakshu migrate`."""

import argparse
import asyncio
import contextlib
import logging
import sys
from importlib import resources

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

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
