from __future__ import annotations

import pandas as pd
import streamlit as st

import database


st.set_page_config(page_title="Wash Sale Registry", layout="wide")
st.title("Wash Sale Registry")
st.caption("Global compliance view across all environments.")

with database.connect() as conn:
    trades = database.list_trades(conn, environment_id=None)
    environments = {env.id: env for env in database.list_environments(conn)}

if not trades:
    st.info("No trades recorded yet.")
    st.stop()

rows = []
for trade in trades:
    env = environments.get(trade.environment_id)
    rows.append(
        {
            "Environment": env.name if env else trade.environment_id,
            "Mode": env.mode if env else "Unknown",
            "Date": trade.trade_date,
            "Ticker": trade.ticker,
            "Action": trade.action,
            "Qty": trade.qty,
            "Price": trade.price,
        }
    )

st.dataframe(pd.DataFrame(rows), use_container_width=True)
