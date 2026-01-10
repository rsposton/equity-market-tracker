from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DEFAULT_DB_PATH = Path(__file__).with_name("portfolio.db")


@dataclass(frozen=True)
class Environment:
    id: int
    name: str
    mode: str
    created_at: str
    current_cash: float


@dataclass(frozen=True)
class Position:
    id: int
    environment_id: int
    ticker: str
    qty: float
    cost_basis: float
    acquired_date: str


@dataclass(frozen=True)
class Trade:
    id: int
    environment_id: int
    ticker: str
    qty: float
    price: float
    action: str
    trade_date: str


@contextmanager
def connect(db_path: Path | str = DEFAULT_DB_PATH) -> Iterable[sqlite3.Connection]:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _init_db(conn)
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS environments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            mode TEXT NOT NULL,
            created_at TEXT NOT NULL,
            current_cash REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            environment_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            qty REAL NOT NULL,
            cost_basis REAL NOT NULL,
            acquired_date TEXT NOT NULL,
            FOREIGN KEY(environment_id) REFERENCES environments(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            environment_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            qty REAL NOT NULL,
            price REAL NOT NULL,
            action TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            FOREIGN KEY(environment_id) REFERENCES environments(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_positions_env ON positions(environment_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trades_env ON trades(environment_id)"
    )
    conn.commit()


def create_environment(
    conn: sqlite3.Connection,
    name: str,
    mode: str,
    current_cash: float,
) -> int:
    created_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO environments (name, mode, created_at, current_cash) VALUES (?, ?, ?, ?)",
        (name, mode, created_at, float(current_cash)),
    )
    conn.commit()
    return int(cursor.lastrowid)


def list_environments(conn: sqlite3.Connection) -> list[Environment]:
    rows = conn.execute(
        "SELECT id, name, mode, created_at, current_cash FROM environments ORDER BY created_at DESC"
    ).fetchall()
    return [Environment(**dict(row)) for row in rows]


def get_environment(conn: sqlite3.Connection, environment_id: int) -> Environment | None:
    row = conn.execute(
        "SELECT id, name, mode, created_at, current_cash FROM environments WHERE id = ?",
        (environment_id,),
    ).fetchone()
    if row is None:
        return None
    return Environment(**dict(row))


def update_environment_cash(
    conn: sqlite3.Connection,
    environment_id: int,
    current_cash: float,
) -> None:
    conn.execute(
        "UPDATE environments SET current_cash = ? WHERE id = ?",
        (float(current_cash), environment_id),
    )
    conn.commit()


def list_positions(conn: sqlite3.Connection, environment_id: int) -> list[Position]:
    rows = conn.execute(
        """
        SELECT id, environment_id, ticker, qty, cost_basis, acquired_date
        FROM positions WHERE environment_id = ? ORDER BY ticker
        """,
        (environment_id,),
    ).fetchall()
    return [Position(**dict(row)) for row in rows]


def list_trades(conn: sqlite3.Connection, environment_id: int | None = None) -> list[Trade]:
    if environment_id is None:
        rows = conn.execute(
            "SELECT id, environment_id, ticker, qty, price, action, trade_date FROM trades ORDER BY trade_date DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, environment_id, ticker, qty, price, action, trade_date
            FROM trades WHERE environment_id = ? ORDER BY trade_date DESC
            """,
            (environment_id,),
        ).fetchall()
    return [Trade(**dict(row)) for row in rows]


def replace_positions(conn: sqlite3.Connection, environment_id: int, lots: Iterable[dict]) -> None:
    conn.execute("DELETE FROM positions WHERE environment_id = ?", (environment_id,))
    for lot in lots:
        conn.execute(
            """
            INSERT INTO positions (environment_id, ticker, qty, cost_basis, acquired_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                environment_id,
                str(lot.get("symbol") or lot.get("ticker") or "").upper(),
                float(lot.get("qty") or 0.0),
                float(lot.get("total_cost_basis") or lot.get("cost_basis") or 0.0),
                str(
                    lot.get("acquisition_date")
                    or lot.get("acquired_date")
                    or datetime.now(timezone.utc).date()
                ),
            ),
        )
    conn.commit()


def record_trade(
    conn: sqlite3.Connection,
    environment_id: int,
    ticker: str,
    qty: float,
    price: float,
    action: str,
    trade_date: str,
) -> None:
    normalized_ticker = str(ticker or "").upper()
    normalized_action = str(action or "").lower()
    conn.execute(
        """
        INSERT INTO trades (environment_id, ticker, qty, price, action, trade_date)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (environment_id, normalized_ticker, float(qty), float(price), normalized_action, trade_date),
    )
    existing = conn.execute(
        """
        SELECT id, qty, cost_basis, acquired_date
        FROM positions WHERE environment_id = ? AND ticker = ?
        """,
        (environment_id, normalized_ticker),
    ).fetchone()

    if normalized_action == "buy":
        added_cost = float(qty) * float(price)
        if existing is None:
            conn.execute(
                """
                INSERT INTO positions (environment_id, ticker, qty, cost_basis, acquired_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (environment_id, normalized_ticker, float(qty), added_cost, trade_date),
            )
        else:
            new_qty = float(existing["qty"]) + float(qty)
            new_cost = float(existing["cost_basis"]) + added_cost
            conn.execute(
                "UPDATE positions SET qty = ?, cost_basis = ? WHERE id = ?",
                (new_qty, new_cost, int(existing["id"])),
            )
    elif normalized_action == "sell" and existing is not None:
        existing_qty = float(existing["qty"])
        existing_cost = float(existing["cost_basis"])
        if existing_qty > 0:
            sold_qty = min(float(qty), existing_qty)
            cost_per_share = existing_cost / existing_qty if existing_qty else 0.0
            remaining_qty = existing_qty - sold_qty
            remaining_cost = max(existing_cost - sold_qty * cost_per_share, 0.0)
            if remaining_qty <= 0:
                conn.execute("DELETE FROM positions WHERE id = ?", (int(existing["id"]),))
            else:
                conn.execute(
                    "UPDATE positions SET qty = ?, cost_basis = ? WHERE id = ?",
                    (remaining_qty, remaining_cost, int(existing["id"])),
                )

    conn.commit()


def apply_genesis_orders(
    conn: sqlite3.Connection,
    environment_id: int,
    orders: Iterable[dict],
    trade_date: str,
) -> float:
    total_spent = 0.0
    for order in orders:
        qty = float(order.get("qty") or 0.0)
        price = float(order.get("price") or 0.0)
        total_spent += qty * price
        record_trade(
            conn,
            environment_id,
            ticker=str(order.get("symbol") or "").upper(),
            qty=qty,
            price=price,
            action="buy",
            trade_date=trade_date,
        )
    environment = get_environment(conn, environment_id)
    if environment is not None:
        update_environment_cash(conn, environment_id, environment.current_cash - total_spent)
    return total_spent
