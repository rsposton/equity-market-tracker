from __future__ import annotations

import argparse
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional


DEFAULT_DB_PATH = Path("wash_sale.db")
WASH_SALE_WINDOW = 31
COMPLIANCE_DUMMY = False


@dataclass(frozen=True)
class WashSaleRecord:
    ticker: str
    sell_date: date
    unlock_date: date
    shares_sold: int


def _ensure_date(value: date | datetime | str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS wash_sales (
            ticker TEXT NOT NULL,
            sell_date TEXT NOT NULL,
            unlock_date TEXT NOT NULL,
            shares_sold INTEGER NOT NULL,
            UNIQUE(ticker, sell_date)
        )
        """
    )
    return connection


def record_harvest(ticker: str, qty: int, sell_date: date | datetime | str, db_path: Path = DEFAULT_DB_PATH) -> bool:
    normalized_sell_date = _ensure_date(sell_date)
    unlock_date = normalized_sell_date + timedelta(days=WASH_SALE_WINDOW)
    with _connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO wash_sales (ticker, sell_date, unlock_date, shares_sold)
            VALUES (?, ?, ?, ?)
            """,
            (ticker.upper(), normalized_sell_date.isoformat(), unlock_date.isoformat(), qty),
        )
    return cursor.rowcount == 1


def check_safety(ticker: str, current_date: date | datetime | str, db_path: Path = DEFAULT_DB_PATH) -> bool:
    normalized_current_date = _ensure_date(current_date)
    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT MAX(unlock_date)
            FROM wash_sales
            WHERE ticker = ?
            """,
            (ticker.upper(),),
        ).fetchone()
    if row is None or row[0] is None:
        return True
    latest_unlock_date = _ensure_date(row[0])
    if normalized_current_date < latest_unlock_date:
        logging.getLogger(__name__).info(
            "Wash sale lockout active for %s until %s.",
            ticker.upper(),
            latest_unlock_date.isoformat(),
        )
        return False
    return True


def get_locked_tickers(current_date: Optional[date | datetime | str] = None, db_path: Path = DEFAULT_DB_PATH) -> list[str]:
    normalized_current_date = _ensure_date(current_date or date.today())
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT ticker, MAX(unlock_date) AS latest_unlock
            FROM wash_sales
            GROUP BY ticker
            HAVING DATE(latest_unlock) > DATE(?)
            """,
            (normalized_current_date.isoformat(),),
        ).fetchall()
    return [row[0] for row in rows]


def clear_ticker(ticker: str, db_path: Path = DEFAULT_DB_PATH) -> int:
    with _connect(db_path) as connection:
        cursor = connection.execute(
            "DELETE FROM wash_sales WHERE ticker = ?",
            (ticker.upper(),),
        )
    return cursor.rowcount


def list_records(db_path: Path = DEFAULT_DB_PATH) -> list[WashSaleRecord]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT ticker, sell_date, unlock_date, shares_sold
            FROM wash_sales
            ORDER BY sell_date ASC
            """
        ).fetchall()
    return [
        WashSaleRecord(
            ticker=row[0],
            sell_date=_ensure_date(row[1]),
            unlock_date=_ensure_date(row[2]),
            shares_sold=row[3],
        )
        for row in rows
    ]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wash sale compliance admin tool")
    parser.add_argument("ticker", help="Ticker symbol to clear")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to the wash sale SQLite database",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    removed = clear_ticker(args.ticker, db_path=args.db_path)
    print(f"Removed {removed} record(s) for {args.ticker.upper()} from {args.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
