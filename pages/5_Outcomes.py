"""
pages/5_Outcomes.py
CFR detail, recovery/death tracking
Logic deferred to build phase.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import analytics
import utils
import os
import preprocessing

try:
    clean_df = preprocessing.load_store()
except Exception:
    clean_df = pd.DataFrame()
    st.info("No data uploaded yet")
st.title("Outcomes")

if not clean_df.empty:
    filtered_df = utils.render_sidebar_filters(clean_df)

    # ---- KPI row ----
    st.markdown('<div class="section-header"><span class="icon">▣</span>Outcome Summary</div>', unsafe_allow_html=True)

    outcome_summary = analytics.get_outcome_summary(filtered_df)
    cfr_data = analytics.get_national_cfr(filtered_df)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        with st.container(key="national_cfr_card"):
            st.metric("National CFR", f"{cfr_data['cfr_percent']:.1f}%")
            st.caption(f"{cfr_data['deaths']} deaths / {cfr_data['confirmed']} confirmed")
    with col2:
        with st.container(key="recovered_card"):
            st.metric("Recovered", outcome_summary["recovered"])
    with col3:
        with st.container(key="deaths_confirmed_card"):
            st.metric("Deaths (Confirmed)", outcome_summary["died"])
    with col4:
        with st.container(key="pending_outcome_card"):
            st.metric("Pending Outcome", outcome_summary["pending"])

    # ---- Recovered vs Deceased over time ----
    st.markdown('<div class="section-header"><span class="icon">▲</span>Outcomes Over Time</div>', unsafe_allow_html=True)

    years_present = filtered_df["Date of Symptom Onset"].dropna().dt.year.unique()

    if len(years_present) == 0:
        st.info("No dated cases available to chart.")
    else:
        years_to_build = sorted(years_present.tolist()) + [max(years_present) + 1]
        epi_calendar_df = analytics.build_epi_calendar(years_to_build)
        cfr_over_time = analytics.get_cfr_over_time(filtered_df, epi_calendar_df)

        if cfr_over_time.empty:
            st.info("No confirmed cases match the current filters.")
        else:
            cfr_over_time["epi_label"] = (
                cfr_over_time["epi_year"].astype(int).astype(str)
                + "-W" + cfr_over_time["epi_week"].astype(int).astype(str)
            )

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=cfr_over_time["epi_label"],
                y=cfr_over_time["cumulative_confirmed"],
                name="Cumulative Confirmed",
                mode="lines",
                line=dict(color="#C33F32"),
                fill="tozeroy",
            ))
            fig.add_trace(go.Scatter(
                x=cfr_over_time["epi_label"],
                y=cfr_over_time["cumulative_deaths"],
                name="Cumulative Deaths",
                mode="lines",
                line=dict(color="#8891A5"),
                fill="tozeroy",
            ))
            fig.update_layout(
                margin={"r": 0, "t": 10, "l": 0, "b": 0},
                legend=dict(bgcolor="rgba(0,0,0,0.4)"),
            )
            st.plotly_chart(fig, use_container_width=True)

    # ---- State-level outcome breakdown table ----
    st.markdown('<div class="section-header"><span class="icon">☰</span>State-Level Outcome Breakdown</div>', unsafe_allow_html=True)

    state_outcome_table = analytics.get_state_outcome_table(filtered_df)
    state_outcome_table = state_outcome_table.sort_values("cfr_percent", ascending=False)
    state_outcome_table = state_outcome_table.reset_index(drop=True)
    state_outcome_table.index = state_outcome_table.index + 1
    st.dataframe(state_outcome_table)