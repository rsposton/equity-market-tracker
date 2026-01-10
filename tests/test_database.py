from __future__ import annotations

from datetime import date

import pytest

import database
from genesis import build_genesis_portfolio_from_holdings


def test_environment_isolation(tmp_path):
    db_path = tmp_path / "envs.db"
    with database.connect(db_path) as conn:
        live_id = database.create_environment(conn, "Live Portfolio", "File Upload", 0.0)
        sandbox_id = database.create_environment(conn, "Sandbox A", "Genesis", 0.0)

        database.record_trade(
            conn,
            live_id,
            ticker="AAPL",
            qty=10,
            price=100.0,
            action="buy",
            trade_date="2024-01-01",
        )
        database.record_trade(
            conn,
            sandbox_id,
            ticker="AAPL",
            qty=5,
            price=100.0,
            action="buy",
            trade_date="2024-01-01",
        )
        database.record_trade(
            conn,
            sandbox_id,
            ticker="AAPL",
            qty=2,
            price=110.0,
            action="sell",
            trade_date="2024-01-02",
        )

    with database.connect(db_path) as conn:
        live_positions = database.list_positions(conn, live_id)
        sandbox_positions = database.list_positions(conn, sandbox_id)

    assert live_positions[0].qty == 10
    assert sandbox_positions[0].qty == 3


def test_genesis_persistence(tmp_path):
    db_path = tmp_path / "genesis.db"
    holdings = [
        {"symbol": "AAA", "weightPercentage": 0.6, "sector": "tech", "price": 100.0},
        {"symbol": "BBB", "weightPercentage": 0.4, "sector": "health", "price": 200.0},
    ]

    portfolio = build_genesis_portfolio_from_holdings(
        holdings=holdings,
        total_cash=250000.0,
        price_lookup={"AAA": 100.0, "BBB": 200.0},
    )

    with database.connect(db_path) as conn:
        env_id = database.create_environment(conn, "Sandbox", "Genesis", 250000.0)
        database.apply_genesis_orders(conn, env_id, portfolio["orders"], date.today().isoformat())

    with database.connect(db_path) as conn:
        positions = database.list_positions(conn, env_id)

    total_cost = sum(position.cost_basis for position in positions)
    assert total_cost == pytest.approx(portfolio["report"]["total_allocated"], rel=1e-3)
