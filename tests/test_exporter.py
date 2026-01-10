from __future__ import annotations

from pathlib import Path

import pandas as pd

from exporter import SCHWAB_HEADERS, build_preview_table, export_schwab_trades


def _sample_trades() -> list[dict]:
    return [
        {
            "sell_ticker": "AAPL",
            "sell_qty": 10.123456,
            "estimated_loss": 150.25,
            "buy_ticker": "MSFT",
            "buy_qty": 5.987654,
            "pairing_id": 1,
            "sell_value": 1800.0,
            "buy_value": 1700.0,
        },
        {
            "sell_ticker": "TSLA",
            "sell_qty": 2,
            "estimated_loss": 75.75,
            "buy_ticker": "NVDA",
            "buy_qty": 1.5,
            "pairing_id": 2,
            "sell_value": 400.0,
            "buy_value": 350.0,
        },
    ]


def test_preview_table_math():
    trades = _sample_trades()
    df, summary = build_preview_table(trades)

    assert df.shape[0] == 2
    assert summary.total_trades == 2
    assert summary.total_harvested_loss == 226.0
    assert summary.net_cash_impact == 150.0


def test_schwab_compliance(tmp_path: Path):
    trades = _sample_trades()
    output_path, _, _ = export_schwab_trades(
        trades,
        account_number="12345678",
        output_dir=tmp_path,
        log_path=tmp_path / "trade_generation_errors.log",
        show_preview=False,
    )

    df = pd.read_csv(output_path)
    assert list(df.columns) == SCHWAB_HEADERS
    assert set(df["Order Type"]) == {"Market"}
    assert set(df["Timing"]) == {"Day"}
    assert list(df["Action"]) == ["Sell", "Buy", "Sell", "Buy"]
    assert df.loc[0, "Quantity"] == 10.1235
    assert df.loc[1, "Quantity"] == 5.9877


def test_corporate_action_handling(tmp_path: Path):
    trades = _sample_trades()
    trades.append(
        {
            "sell_ticker": "ABCDEFGH",
            "sell_qty": 1,
            "estimated_loss": 10.0,
            "buy_ticker": "GOOD",
            "buy_qty": 1,
            "pairing_id": 12,
            "sell_value": 100.0,
            "buy_value": 90.0,
        }
    )
    log_path = tmp_path / "trade_generation_errors.log"
    output_path, _, _ = export_schwab_trades(
        trades,
        account_number="12345678",
        output_dir=tmp_path,
        log_path=log_path,
        show_preview=False,
    )

    df = pd.read_csv(output_path)
    assert "ABCDEFGH" not in df["Symbol"].values

    log_contents = log_path.read_text()
    assert "Skipping trade pair ID 12" in log_contents
    assert "Sell Ticker 'ABCDEFGH' appears invalid" in log_contents
