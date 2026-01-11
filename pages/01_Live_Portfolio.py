from __future__ import annotations

from datetime import date
import os
import tempfile
from pathlib import Path

import pandas as pd

import streamlit as st

import database
from genesis import fetch_quotes
from ingestor import parse_schwab_positions, parse_schwab_transactions


st.set_page_config(page_title="Live Portfolio", layout="wide")
st.title("Live Portfolio")
st.caption("Upload Schwab exports and review live holdings.")

with database.connect() as conn:
    environments = [env for env in database.list_environments(conn) if env.mode == "File Upload"]

if not environments:
    st.info("No Live environments found. Create one from the Home page.")
    st.stop()

selected_name = st.selectbox("Select Environment", [env.name for env in environments])
selected_env = next(env for env in environments if env.name == selected_name)

with database.connect() as conn:
    positions = database.list_positions(conn, selected_env.id)
    trades = database.list_trades(conn, selected_env.id)

if "price_cache" not in st.session_state:
    st.session_state.price_cache = {}

price_cache = st.session_state.price_cache.setdefault(selected_env.id, {})

st.subheader("Overview")

col1, col2, col3 = st.columns(3)

total_cost = sum(position.cost_basis for position in positions)
if positions and price_cache:
    total_value = sum(position.qty * price_cache.get(position.ticker, 0.0) for position in positions)
else:
    total_value = total_cost

with col1:
    st.metric("Total Value", f"${total_value:,.2f}")
with col2:
    drift_score = abs(total_value - total_cost) / total_cost if total_cost else 0.0
    st.metric("Drift Score", f"{drift_score:.2%}")
with col3:
    st.metric("Harvested Loss", "$0.00")

col_a, col_b = st.columns(2)

with col_a:
    if st.button("Sync Prices"):
        api_key = st.secrets.get("FMP_API_KEY") or os.getenv("FMP_API_KEY")
        if not api_key:
            st.warning(
                "Missing FMP API key. Add it to .streamlit/secrets.toml or set FMP_API_KEY "
                "in the environment."
            )
        elif not positions:
            st.info("No positions to refresh.")
        else:
            symbols = [position.ticker for position in positions]
            price_cache.update(fetch_quotes(api_key, symbols))
            st.success("Latest quotes loaded.")

with col_b:
    if st.button("Scan for TLH Triggers"):
        st.info("TLH scan queued. Review signals in the compliance view.")

st.divider()

st.subheader("Upload Latest Statements")

positions_upload = st.file_uploader("Upload schwab_positions.csv", type=["csv"])
transactions_upload = st.file_uploader("Upload schwab_transactions.csv", type=["csv"])

def _save_upload(upload: st.runtime.uploaded_file_manager.UploadedFile) -> Path:
    with tempfile.NamedTemporaryFile(delete=False, suffix=upload.name) as handle:
        handle.write(upload.getvalue())
        return Path(handle.name)

if st.button("Ingest Uploads"):
    if positions_upload is None and transactions_upload is None:
        st.warning("Upload at least one file before ingesting.")
    else:
        with database.connect() as conn:
            if positions_upload is not None:
                lots = parse_schwab_positions(str(_save_upload(positions_upload)))
                database.replace_positions(conn, selected_env.id, lots)
            if transactions_upload is not None:
                transactions = parse_schwab_transactions(str(_save_upload(transactions_upload)))
                for txn in transactions:
                    database.record_trade(
                        conn,
                        selected_env.id,
                        ticker=txn["symbol"],
                        qty=txn["quantity"],
                        price=txn["price"],
                        action=txn["action"],
                        trade_date=txn["date"],
                    )
        st.success("Uploads ingested.")

st.subheader("Current Positions")
if positions:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Ticker": position.ticker,
                    "Qty": position.qty,
                    "Cost Basis": position.cost_basis,
                    "Acquired": position.acquired_date,
                }
                for position in positions
            ]
        ),
        use_container_width=True,
    )
else:
    st.info("No positions stored for this environment yet.")

st.subheader("Recent Trades")
if trades:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Date": trade.trade_date,
                    "Ticker": trade.ticker,
                    "Action": trade.action,
                    "Qty": trade.qty,
                    "Price": trade.price,
                }
                for trade in trades
            ]
        ),
        use_container_width=True,
    )
else:
    st.info("No trades recorded yet.")

st.caption(f"Data as of {date.today().isoformat()}")
