"""Command line entry point: `chakshu web`, plus more commands as they land."""

import argparse

import uvicorn


def _web(args: argparse.Namespace) -> None:
    uvicorn.run(
        "chakshu.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="chakshu")
    commands = parser.add_subparsers(dest="command", required=True)

    web = commands.add_parser("web", help="serve the portal and webhook endpoint")
    web.add_argument("--host", default="0.0.0.0")
    web.add_argument("--port", type=int, default=8000)
    web.set_defaults(func=_web)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
