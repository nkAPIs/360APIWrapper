"""
dump_code_table.py

Fetch and print the rows of a 360 code table, e.g. "Case status", so you
can read off the Recno/Code/Description values to use as arguments to
Public360Client methods (create_case's `status`, `access_code`, etc.).

Uses the same config/token setup as test.py - run that first if you
don't yet have an offline token stored for this tenant.

Usage:
    uv run python scripts/dump_code_table.py "Case status"
    uv run python scripts/dump_code_table.py "Case type" --include-expired
"""

import argparse
import sys

from src.config import get_configuration
from src.public360_client import Public360AuthError, Public360Client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("code_table_name", help='e.g. "Case status", "Case type"')
    parser.add_argument(
        "--include-expired",
        action="store_true",
        help="Include expired/inactive rows (default: active only).",
    )
    args = parser.parse_args()

    config = get_configuration()
    client = Public360Client(
        realm_url=config.realm_url,
        client_id=config.client_id,
        tenant_host=config.tenant_host,
        token_storage_path=config.token_storage_path,
    )

    try:
        client._load_offline_token()
    except Public360AuthError:
        print("No offline token found, starting bootstrap (browser will open)...")
        client.bootstrap()

    try:
        result = client.get_code_table_rows(
            args.code_table_name,
            include_expired_values=args.include_expired,
        )
    except Public360AuthError as exc:
        print(f"FAILED - authentication error: {exc}", file=sys.stderr)
        return 1

    rows = result.get("CodeTableRows", [])
    print(f'{args.code_table_name}: {len(rows)} row(s)')
    for row in rows:
        print(
            f"  recno:{row.get('Recno')}\t"
            f"Code={row.get('Code')!r}\t"
            f"Description={row.get('Description')!r}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
