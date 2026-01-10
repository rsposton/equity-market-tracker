from __future__ import annotations

import argparse
from pathlib import Path

from compliance import DEFAULT_DB_PATH, clear_ticker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clear a ticker from wash sale lockout")
    parser.add_argument("ticker", help="Ticker symbol to clear")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to the wash sale SQLite database",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    removed = clear_ticker(args.ticker, db_path=args.db_path)
    print(f"Removed {removed} record(s) for {args.ticker.upper()} from {args.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
