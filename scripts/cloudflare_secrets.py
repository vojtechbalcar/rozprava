#!/usr/bin/env python3
"""Copy the production secrets into the Cloudflare Worker without printing them.

Reads VOYAGE_API_KEY and ANTHROPIC_API_KEY from `.env`, DATABASE_URL from
`.env.production`, and generates ADMIN_TOKEN (for POST /_admin/update) into
`.env.production` when it is missing. Each value is piped to
`npx wrangler secret put NAME` in deploy/cloudflare. Run `npx wrangler login`
there first. See docs/production-deployment.md.

    uv run python scripts/cloudflare_secrets.py
"""

import secrets
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / "deploy" / "cloudflare"
LOCAL, PRODUCTION = ROOT / ".env", ROOT / ".env.production"


def main() -> int:
    local = dotenv_values(LOCAL) if LOCAL.exists() else {}
    production = dotenv_values(PRODUCTION) if PRODUCTION.exists() else {}
    if not production.get("ADMIN_TOKEN"):
        with PRODUCTION.open("a", encoding="utf-8") as handle:
            handle.write(f"ADMIN_TOKEN={secrets.token_urlsafe(32)}\n")
        PRODUCTION.chmod(0o600)
        production = dotenv_values(PRODUCTION)
    values = {
        "DATABASE_URL": production.get("DATABASE_URL"),
        "ADMIN_TOKEN": production.get("ADMIN_TOKEN"),
        "VOYAGE_API_KEY": local.get("VOYAGE_API_KEY"),
        "ANTHROPIC_API_KEY": local.get("ANTHROPIC_API_KEY"),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        print(f"Missing: {', '.join(missing)}; nothing was sent.", file=sys.stderr)
        return 1
    for name, value in values.items():
        result = subprocess.run(
            ["npx", "wrangler", "secret", "put", name],
            cwd=WORKER,
            input=value,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            # Wrangler's error text does not contain the value that was piped in.
            print(f"{name}: failed\n{result.stderr[-1500:]}", file=sys.stderr)
            return 1
        print(f"{name}: stored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
