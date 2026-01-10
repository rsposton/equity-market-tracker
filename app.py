from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

import database


st.set_page_config(
    page_title="Direct Index TLH Manager",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Direct Index + TLH Research Hub")
st.caption("Manage live portfolios and sandbox experiments with persistent storage.")

with database.connect() as conn:
    environments = database.list_environments(conn)

st.subheader("Active Environments")
if environments:
    env_rows = []
    for env in environments:
        env_rows.append(
            {
                "ID": env.id,
                "Name": env.name,
                "Type": "Sandbox" if env.mode.lower() == "genesis" else "Live",
                "Mode": env.mode,
                "Created": env.created_at,
                "Current Cash": round(env.current_cash, 2),
            }
        )
    st.dataframe(pd.DataFrame(env_rows), use_container_width=True)
else:
    st.info("No environments yet. Launch a new experiment to get started.")

st.divider()

if "show_new" not in st.session_state:
    st.session_state.show_new = False

if st.button("Launch New Experiment", type="primary"):
    st.session_state.show_new = True

if st.session_state.show_new:
    st.subheader("Initialize Environment")
    with st.form("new_environment"):
        name = st.text_input("Name", value="Experiment A - 120 Stocks")
        mode = st.selectbox("Mode", options=["Genesis", "File Upload"])
        budget = st.number_input(
            "Budget",
            min_value=0.0,
            value=250000.0,
            step=1000.0,
            help="Required for Genesis environments.",
        )
        submitted = st.form_submit_button("Create Environment")

    if submitted:
        current_cash = budget if mode == "Genesis" else 0.0
        with database.connect() as conn:
            database.create_environment(conn, name=name, mode=mode, current_cash=current_cash)
        st.success("Environment created. Open the Live or Sandbox page from the sidebar.")
        st.session_state.show_new = False

st.sidebar.markdown("## Quick Navigation")
st.sidebar.markdown("Use the page selector above to open Live or Sandbox workflows.")
st.sidebar.caption(f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
