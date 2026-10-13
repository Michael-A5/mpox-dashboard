"""
pages/2_Epi_Curve_Trends.py
epi curve toggle by classification, epi-year comparison overlay
Logic deferred to build phase.
"""
import streamlit as st
import pandas as pd
import analytics
from datetime import datetime, timedelta
import utils
import preprocessing

try:
    clean_df = preprocessing.load_store()
except Exception:
    clean_df = pd.DataFrame()
    st.info("No data uploaded yet")

st.title("Epi Curve & Trends")

if not clean_df.empty:

    filtered_df = utils.render_sidebar_filters(clean_df)

    today = datetime.now()
    one_year_ago = today - timedelta(days=365)

    classification_options = ["Confirmed", "Probable", "Suspected"]

    st.markdown('<div class="section-header"><span class="icon">▲</span>Epi Curve</div>', unsafe_allow_html=True)

    granularity_col, classification_col = st.columns(2)

    with granularity_col:
        granularity = st.selectbox("Granularity", ["day", "week", "month"], index=1)

    with classification_col:
        selected_classification = st.multiselect(
            "Classification", options=classification_options, default=classification_options
        )

    year_filtered_df = filtered_df[
        (filtered_df["Date of Symptom Onset"] >= one_year_ago) &
        (filtered_df["Date of Symptom Onset"] <= today)
    ]

    st.caption(f"Showing {one_year_ago.strftime('%b %Y')} – {today.strftime('%b %Y')}")

    curve_data = analytics.get_epi_curve(
        year_filtered_df, granularity=granularity, classifications=selected_classification
    )

    available_columns = [c for c in selected_classification if c in curve_data.columns]

    color_map = {
        "Confirmed": "#C33F32",
        "Probable": "#D9A441",
        "Suspected": "#1DBF83",
    }
    selected_colors = [color_map[c] for c in available_columns]

    if available_columns:
        st.bar_chart(
            curve_data, x="period", y=available_columns, stack=True,
            color=selected_colors, height=500
        )
    else:
        st.info("No cases match the current filters and classification selection.")

    st.markdown('<div class="section-header"><span class="icon">◈</span>Epi-Year Comparison</div>', unsafe_allow_html=True)

    comparison_data, unmatched_count = analytics.get_epi_year_comparison(filtered_df)
    comparison_data.columns = comparison_data.columns.map(str)
    year_columns = [col for col in comparison_data.columns if col != "epi_week"]
    st.line_chart(comparison_data, x="epi_week", y=year_columns, height=400)

    if unmatched_count > 0:
        st.caption(f"{unmatched_count} cases excluded, onset date outside known epi calendar")