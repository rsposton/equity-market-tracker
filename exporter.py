from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

LOG_FILE_NAME = "trade_generation_errors.log"
SCHWAB_HEADERS = [
    "Account Number",
    "Symbol",
    "Action",
    "Quantity",
    "Order Type",
    "Timing",
]


@dataclass(frozen=True)
class PreviewSummary:
    total_trades: int
    total_harvested_loss: float
    net_cash_impact: float


def _configure_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("trade_exporter")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing_handler = next(
        (
            handler
            for handler in logger.handlers
            if isinstance(handler, logging.FileHandler)
            and Path(handler.baseFilename) == log_path
        ),
        None,
    )
    if existing_handler is None:
        handler = logging.FileHandler(log_path)
        formatter = logging.Formatter(
            "[%(levelname)s %(asctime)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


def _normalize_ticker(ticker: Optional[str]) -> str:
    return str(ticker or "").strip().upper()


def _validate_ticker(ticker: Optional[str]) -> tuple[bool, str, str]:
    normalized = _normalize_ticker(ticker)
    if not normalized:
        return False, normalized, "ticker is missing"
    if len(normalized) > 5:
        return False, normalized, "ticker length exceeds 5 characters"
    if re.search(r"\d", normalized):
        return False, normalized, "ticker contains numeric characters"
    if not re.fullmatch(r"[A-Z]+", normalized):
        return False, normalized, "ticker contains unexpected characters"
    return True, normalized, ""


def _log_invalid_ticker(
    logger: logging.Logger,
    pairing_id: str,
    side_label: str,
    ticker: str,
    reason: str,
) -> None:
    logger.error(
        "Skipping trade pair ID %s: %s Ticker '%s' appears invalid (%s).",
        pairing_id,
        side_label,
        ticker,
        reason,
    )


def _filter_valid_trades(
    trades: Iterable[dict],
    logger: logging.Logger,
) -> list[dict]:
    valid_trades: list[dict] = []
    for trade in trades:
        pairing_id = str(trade.get("pairing_id", "unknown"))

        sell_valid, sell_ticker, sell_reason = _validate_ticker(trade.get("sell_ticker"))
        buy_valid, buy_ticker, buy_reason = _validate_ticker(trade.get("buy_ticker"))

        if not sell_valid:
            _log_invalid_ticker(logger, pairing_id, "Sell", sell_ticker, sell_reason)
        if not buy_valid:
            _log_invalid_ticker(logger, pairing_id, "Buy", buy_ticker, buy_reason)

        if sell_valid and buy_valid:
            trade = dict(trade)
            trade["sell_ticker"] = sell_ticker
            trade["buy_ticker"] = buy_ticker
            valid_trades.append(trade)
    return valid_trades


def build_preview_table(trades: Iterable[dict]) -> tuple[pd.DataFrame, PreviewSummary]:
    rows = []
    total_loss = 0.0
    net_cash = 0.0
    for trade in trades:
        estimated_loss = float(trade.get("estimated_loss", 0.0))
        sell_value = float(trade.get("sell_value", 0.0))
        buy_value = float(trade.get("buy_value", 0.0))
        total_loss += estimated_loss
        net_cash += sell_value - buy_value
        rows.append(
            {
                "Sell Ticker": trade.get("sell_ticker"),
                "Sell Qty": trade.get("sell_qty"),
                "Est. Realized Loss ($)": estimated_loss,
                "Buy Ticker": trade.get("buy_ticker"),
                "Buy Qty": trade.get("buy_qty"),
                "Pairing ID": trade.get("pairing_id"),
            }
        )

    df = pd.DataFrame(rows)
    summary = PreviewSummary(
        total_trades=len(rows),
        total_harvested_loss=round(total_loss, 2),
        net_cash_impact=round(net_cash, 2),
    )
    return df, summary


def render_preview(df: pd.DataFrame, summary: PreviewSummary) -> str:
    table_text = df.to_string(index=False) if not df.empty else "(no valid trades)"
    footer = (
        f"Total Trades: {summary.total_trades}\n"
        f"Total Harvested Loss: ${summary.total_harvested_loss:,.2f}\n"
        f"Net Cash Impact: ${summary.net_cash_impact:,.2f}"
    )
    return f"{table_text}\n\n{footer}"


def export_schwab_trades(
    trades: Iterable[dict],
    account_number: str,
    output_dir: Path | str = Path("."),
    log_path: Path | str = Path(LOG_FILE_NAME),
    show_preview: bool = True,
) -> tuple[Path, pd.DataFrame, PreviewSummary]:
    output_dir = Path(output_dir)
    log_path = Path(log_path)
    logger = _configure_logger(log_path)

    valid_trades = _filter_valid_trades(trades, logger)
    preview_df, summary = build_preview_table(valid_trades)

    if show_preview:
        print(render_preview(preview_df, summary))

    rows = []
    for trade in valid_trades:
        sell_qty = round(float(trade.get("sell_qty", 0.0)), 4)
        buy_qty = round(float(trade.get("buy_qty", 0.0)), 4)
        rows.append(
            {
                "Account Number": account_number,
                "Symbol": trade.get("sell_ticker"),
                "Action": "Sell",
                "Quantity": sell_qty,
                "Order Type": "Market",
                "Timing": "Day",
            }
        )
        rows.append(
            {
                "Account Number": account_number,
                "Symbol": trade.get("buy_ticker"),
                "Action": "Buy",
                "Quantity": buy_qty,
                "Order Type": "Market",
                "Timing": "Day",
            }
        )

    df = pd.DataFrame(rows, columns=SCHWAB_HEADERS)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"schwab_trades_{date.today():%Y%m%d}.csv"
    df.to_csv(output_path, index=False)
    return output_path, preview_df, summary


def export_genesis_orders(
    orders: Iterable[dict],
    output_dir: Path | str = Path("."),
    filename: str = "schwab_genesis_orders.csv",
    account_number: str = "",
) -> tuple[Path, pd.DataFrame]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for order in orders:
        rows.append(
            {
                "Account Number": account_number,
                "Symbol": order.get("symbol"),
                "Action": order.get("action", "Buy"),
                "Quantity": order.get("qty"),
                "Order Type": "Market",
                "Timing": "Day",
            }
        )

    df = pd.DataFrame(rows, columns=SCHWAB_HEADERS)
    output_path = output_dir / filename
    df.to_csv(output_path, index=False)
    return output_path, df
