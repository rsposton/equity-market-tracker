from __future__ import annotations

import io
import tempfile
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

from compliance import check_safety, list_records
from engine import mock_wash_sale_registry, propose_trades
from exporter import export_schwab_trades
from ingestor import parse_schwab_positions, parse_schwab_transactions


def _save_upload(upload: st.runtime.uploaded_file_manager.UploadedFile) -> Path:
    with tempfile.NamedTemporaryFile(delete=False, suffix=upload.name) as handle:
        handle.write(upload.getvalue())
        return Path(handle.name)


def _positions_from_upload(upload: st.runtime.uploaded_file_manager.UploadedFile) -> list[dict]:
    path = _save_upload(upload)
    return parse_schwab_positions(str(path))


def _transactions_from_upload(
    upload: st.runtime.uploaded_file_manager.UploadedFile,
) -> list[dict]:
    path = _save_upload(upload)
    return parse_schwab_transactions(str(path))


def _build_registry(transactions: Iterable[dict]) -> dict:
    recent_sales: dict[str, str] = {}
    for txn in transactions:
        if str(txn.get("action", "")).lower() != "sell":
            continue
        recent_sales[str(txn.get("symbol", "")).upper()] = str(txn.get("date"))
    return mock_wash_sale_registry(recent_sales=recent_sales)


def _replacement_prices_from_lots(lots: Iterable[dict]) -> dict:
    prices = {}
    for lot in lots:
        symbol = str(lot.get("symbol", "")).upper()
        prices[symbol] = float(lot.get("current_price", 0.0) or 0.0)
    return prices


def _build_trade_pairs(trades: Iterable[dict]) -> list[dict]:
    sells = [trade for trade in trades if trade.get("action") == "sell"]
    buys = [trade for trade in trades if trade.get("action") == "buy"]
    buys_by_replaces = {
        trade.get("replaces"): trade for trade in buys if trade.get("replaces")
    }

    pairs = []
    for sell in sells:
        symbol = sell.get("symbol")
        replacement = sell.get("replacement")
        buy = buys_by_replaces.get(symbol)
        blocked = False
        blocked_reason = ""
        if replacement and not check_safety(replacement, date.today()):
            blocked = True
            blocked_reason = "Wash Sale"

        if buy is None:
            blocked = True
            if not blocked_reason:
                blocked_reason = "Unavailable"

        status = "Approved" if not blocked else f"Blocked ({blocked_reason})"

        pairs.append(
            {
                "sell_ticker": symbol,
                "sell_qty": float(sell.get("qty", 0.0)),
                "sell_price": float(sell.get("price", 0.0)),
                "buy_ticker": replacement,
                "buy_qty": float(buy.get("qty", 0.0)) if buy else 0.0,
                "buy_price": float(buy.get("price", 0.0)) if buy else 0.0,
                "status": status,
            }
        )
    return pairs


def _preview_dataframe(pairs: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Sell Ticker": pair["sell_ticker"],
                "Sell Qty": pair["sell_qty"],
                "Sell Price": pair["sell_price"],
                "Buy Ticker": pair["buy_ticker"],
                "Buy Qty": pair["buy_qty"],
                "Buy Price": pair["buy_price"],
                "Status": pair["status"],
            }
            for pair in pairs
        ]
    )


def _style_preview(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    def _highlight(row: pd.Series) -> list[str]:
        status = str(row.get("Status", ""))
        if "Wash Sale" in status:
            color = "background-color: #7a1f1f; color: #fff"
            return [color] * len(row)
        if "Blocked" in status:
            color = "background-color: #8a6d1f; color: #fff"
            return [color] * len(row)
        return [""] * len(row)

    return df.style.apply(_highlight, axis=1)


def _trade_export_payload(pairs: list[dict]) -> list[dict]:
    payload = []
    for idx, pair in enumerate(pairs, start=1):
        if not str(pair.get("status", "")).startswith("Approved"):
            continue
        sell_value = float(pair.get("sell_qty", 0.0)) * float(
            pair.get("sell_price", 0.0)
        )
        buy_value = float(pair.get("buy_qty", 0.0)) * float(
            pair.get("buy_price", 0.0)
        )
        payload.append(
            {
                "pairing_id": f"pair-{idx}",
                "sell_ticker": pair.get("sell_ticker"),
                "buy_ticker": pair.get("buy_ticker"),
                "sell_qty": pair.get("sell_qty"),
                "buy_qty": pair.get("buy_qty"),
                "sell_value": sell_value,
                "buy_value": buy_value,
                "estimated_loss": 0.0,
            }
        )
    return payload


def _unrealized_gain_loss(lots: Iterable[dict]) -> float:
    total = 0.0
    for lot in lots:
        qty = float(lot.get("qty", 0.0))
        total_cost = float(lot.get("total_cost_basis", 0.0))
        current_price = float(lot.get("current_price", 0.0))
        total += qty * current_price - total_cost
    return total


def _tracking_error_proxy(summary: dict) -> float:
    turnover = float(summary.get("turnover_ratio", 0.0) or 0.0)
    return min(max(turnover, 0.0), 1.0)


st.set_page_config(
    page_title="Direct Index TLH Manager",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Direct Index + TLH Manager")
st.caption("Upload Schwab exports to generate trade previews and wash-sale checks.")

with st.sidebar:
    st.header("Inputs")
    positions_upload = st.file_uploader(
        "Upload schwab_positions.csv",
        type=["csv"],
        accept_multiple_files=False,
    )
    transactions_upload = st.file_uploader(
        "Upload schwab_transactions.csv",
        type=["csv"],
        accept_multiple_files=False,
    )
    drawdown_mode = st.toggle("Drawdown Mode (Aggressive)", value=False)
    account_number = st.text_input("Schwab Account Number", value="")

positions: list[dict] = []
transactions: list[dict] = []
parse_errors = []

if positions_upload is not None:
    try:
        positions = _positions_from_upload(positions_upload)
        st.success("Positions CSV parsed successfully.")
    except Exception as exc:  # noqa: BLE001
        parse_errors.append(str(exc))
        st.error(f"Positions CSV parsing failed: {exc}")

if transactions_upload is not None:
    try:
        transactions = _transactions_from_upload(transactions_upload)
        st.success("Transactions CSV parsed successfully.")
    except Exception as exc:  # noqa: BLE001
        parse_errors.append(str(exc))
        st.error(f"Transactions CSV parsing failed: {exc}")

if positions and not parse_errors:
    registry = _build_registry(transactions) if transactions else None
    replacement_prices = _replacement_prices_from_lots(positions)
    payload = {
        "lots": positions,
        "replacement_prices": replacement_prices,
    }
    trade_result = propose_trades(
        payload,
        drawdown_mode=drawdown_mode,
        wash_sale_registry=registry,
    )
    st.success("Trade generation complete.")

    summary = trade_result.get("summary", {})
    total_portfolio_value = float(summary.get("total_portfolio_value", 0.0) or 0.0)
    harvested_loss = float(summary.get("harvested_loss", 0.0) or 0.0)
    unrealized_gain_loss = _unrealized_gain_loss(positions)

    tile_1, tile_2, tile_3 = st.columns(3)
    tile_1.metric("Total Portfolio Value", f"${total_portfolio_value:,.2f}")
    tile_2.metric("Unrealized Gain/Loss", f"${unrealized_gain_loss:,.2f}")
    tile_3.metric("Total Harvested Loss (YTD)", f"${harvested_loss:,.2f}")

    st.subheader("Drift Analysis")
    tracking_error = _tracking_error_proxy(summary)
    st.progress(tracking_error)
    st.caption(f"Tracking Error vs S&P 500: {tracking_error * 100:.2f}%")

    st.subheader("Trade Preview")
    trade_pairs = _build_trade_pairs(trade_result.get("trades", []))
    preview_df = _preview_dataframe(trade_pairs)
    if preview_df.empty:
        st.info("No eligible trades were generated.")
    else:
        st.dataframe(_style_preview(preview_df), use_container_width=True)

    export_pairs = _trade_export_payload(trade_pairs)
    if export_pairs:
        output_path, _, _ = export_schwab_trades(
            export_pairs,
            account_number=account_number or "UNKNOWN",
            output_dir=Path(tempfile.gettempdir()),
            show_preview=False,
        )
        buffer = io.BytesIO(output_path.read_bytes())
        st.download_button(
            "Download schwab_trade_file.csv",
            data=buffer,
            file_name="schwab_trade_file.csv",
            mime="text/csv",
        )
    else:
        st.info("No approved trades available for export.")

st.subheader("Wash-Sale Calendar")
records = list_records()
if records:
    wash_df = pd.DataFrame(
        [
            {
                "Ticker": record.ticker,
                "Sell Date": record.sell_date.isoformat(),
                "Unlock Date": record.unlock_date.isoformat(),
                "Shares Sold": record.shares_sold,
            }
            for record in records
        ]
    )
    st.dataframe(wash_df, use_container_width=True)
else:
    st.info("No wash-sale locks are currently active.")
