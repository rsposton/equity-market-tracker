from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import database
from exporter import export_genesis_orders
from genesis import build_genesis_portfolio


st.set_page_config(page_title="Sandbox Experiments", layout="wide")
st.title("Sandbox Experiments")
st.caption("Run genesis exercises and test TLH workflows.")

with database.connect() as conn:
    environments = [env for env in database.list_environments(conn) if env.mode == "Genesis"]

if not environments:
    st.info("No Sandbox environments found. Create one from the Home page.")
    st.stop()

selected_name = st.selectbox("Select Environment", [env.name for env in environments])
selected_env = next(env for env in environments if env.name == selected_name)

with database.connect() as conn:
    positions = database.list_positions(conn, selected_env.id)
    trades = database.list_trades(conn, selected_env.id)

st.subheader("Overview")

col1, col2, col3 = st.columns(3)

total_cost = sum(position.cost_basis for position in positions)

with col1:
    st.metric("Total Value", f"${total_cost:,.2f}")
with col2:
    st.metric("Drift Score", "0.00%")
with col3:
    st.metric("Harvested Loss", "$0.00")

col_a, col_b = st.columns(2)

with col_a:
    if st.button("Sync Prices"):
        st.info("Price sync is disabled in sandbox mode. Use genesis to refresh orders.")

with col_b:
    if st.button("Scan for TLH Triggers"):
        st.info("TLH scan queued. Review signals in the compliance view.")

st.divider()

st.subheader("Genesis Exercise")
st.write(f"Current cash available: ${selected_env.current_cash:,.2f}")

if st.button("Run Genesis Exercise", type="primary"):
    api_key = st.secrets.get("FMP_API_KEY")
    if not api_key:
        st.warning("Missing FMP API key. Add it to .streamlit/secrets.toml")
    elif selected_env.current_cash <= 0:
        st.warning("No cash available. Create a new sandbox with a budget.")
    else:
        portfolio = build_genesis_portfolio(total_cash=selected_env.current_cash, api_key=api_key)
        orders = portfolio["orders"]
        report = portfolio["report"]

        with database.connect() as conn:
            database.apply_genesis_orders(
                conn,
                selected_env.id,
                orders,
                trade_date=date.today().isoformat(),
            )

        output_path, preview_df = export_genesis_orders(
            orders,
            output_dir=Path("exports"),
            account_number="",
        )

        st.success("Genesis orders created and stored.")
        st.write(report)
        if not preview_df.empty:
            st.dataframe(preview_df, use_container_width=True)
        with output_path.open("rb") as handle:
            st.download_button(
                "Download Schwab Genesis CSV",
                data=handle,
                file_name=output_path.name,
                mime="text/csv",
            )

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
