"""Small local client for submitting configurable TubeForge video briefs."""
from __future__ import annotations

import argparse
import json
import getpass
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(prog="tubeforge")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-video", help="submit a title-and-notes video brief")
    create.add_argument("--title", required=True)
    create.add_argument("--note", action="append", required=True)
    create.add_argument("--preset")
    create.add_argument("--duration", type=int, dest="duration_seconds")
    create.add_argument("--captions", choices=("on", "off"))
    create.add_argument("--music")
    create.add_argument("--visual-style")
    create.add_argument("--review", choices=("manual", "auto"))
    create.add_argument("--mcp", action="append")
    create.add_argument("--url", default="http://127.0.0.1:8081")
    admin = commands.add_parser("create-admin", help="create the first local dashboard administrator")
    admin.add_argument("--username", required=True)
    admin.add_argument("--password", help="omit to enter it without echoing")
    args = parser.parse_args()
    if args.command == "create-admin":
        from tubeforge.core.config import load_settings
        from tubeforge.core.runtime import create_runtime
        password = args.password or getpass.getpass("Password: ")
        runtime = create_runtime(load_settings())
        try:
            runtime.auth.create_admin(args.username, password)
        finally:
            runtime.database.dispose()
        print("Administrator created.")
        return
    body = {"title": args.title, "notes": args.note}
    for key in ("preset", "duration_seconds", "music", "visual_style"):
        value = getattr(args, key, None)
        if value is not None:
            body["music_track" if key == "music" else key] = value
    if args.captions is not None:
        body["captions_enabled"] = args.captions == "on"
    if args.review is not None:
        body["review_mode"] = args.review
    if args.mcp is not None:
        body["mcp_servers"] = args.mcp
    request = Request(args.url.rstrip("/") + "/api/videos", data=json.dumps(body).encode(), headers={"content-type": "application/json"}, method="POST")
    with urlopen(request, timeout=30) as response:  # noqa: S310 - explicit operator localhost URL
        print(response.read().decode())


if __name__ == "__main__":
    main()
