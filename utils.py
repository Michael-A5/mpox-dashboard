"""
utils.py
Theme engine (inject_css), KPI/insight card builders, sidebar filters
(State, LGA, Epi Week, Sex, upload widget), traffic-light KPI styling,
operational mode gauge renderer.
Logic deferred to build phase.
"""
import streamlit as st
import pandas as pd
import analytics


def render_sidebar_filters(clean_df):
    if clean_df.empty:
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # Streamlit deletes widget-keyed session_state entries when you
    # navigate away from a page and recreates them fresh on return.
    # To survive page navigation, every filter's real value lives in a
    # separate "persist_*" key that we manage ourselves, and each
    # widget's on_change callback keeps that persist key up to date.
    # ------------------------------------------------------------------
    defaults = {
        "persist_state": "All",
        "persist_lga": "All",
        "persist_week_mode": "Range",
        "persist_week_range": None,   # set once we know min/max
        "persist_single_week": None,  # set once we know min/max
        "persist_sex": "All",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # ---- State ----
    def sync_state():
        st.session_state["persist_state"] = st.session_state["filter_state"]

    state_options = ["All"] + sorted(clean_df["STATE"].unique().tolist())
    state_index = (
        state_options.index(st.session_state["persist_state"])
        if st.session_state["persist_state"] in state_options else 0
    )
    state_filter = st.sidebar.selectbox(
        "State", options=state_options, index=state_index,
        key="filter_state", on_change=sync_state,
    )

    # ---- LGA (depends on State) ----
    def sync_lga():
        st.session_state["persist_lga"] = st.session_state["filter_lga"]

    if state_filter == "All":
        lga_options = sorted(clean_df["LGA"].unique().tolist())
    else:
        lga_options = sorted(
            clean_df[clean_df["STATE"] == state_filter]["LGA"].unique().tolist()
        )
    lga_full_options = ["All"] + lga_options
    lga_index = (
        lga_full_options.index(st.session_state["persist_lga"])
        if st.session_state["persist_lga"] in lga_full_options else 0
    )
    lga_filter = st.sidebar.selectbox(
        "LGA", options=lga_full_options, index=lga_index,
        key="filter_lga", on_change=sync_lga,
    )

    # ---- Epi week numbers available in the data ----
    epi_weeks_numeric = (
        clean_df["Epi Week (Onset Week)"]
        .str.extract(r"W(\d+)")[0]
        .astype(int)
    )
    week_min = int(epi_weeks_numeric.min())
    week_max = int(epi_weeks_numeric.max())

    if st.session_state["persist_week_range"] is None:
        st.session_state["persist_week_range"] = (week_min, week_max)
    if st.session_state["persist_single_week"] is None:
        st.session_state["persist_single_week"] = week_min

    # ---- Week mode toggle ----
    def sync_week_mode():
        st.session_state["persist_week_mode"] = st.session_state["filter_week_mode"]

    mode_options = ["Range", "Single week"]
    mode_index = mode_options.index(st.session_state["persist_week_mode"])
    week_mode = st.sidebar.radio(
        "Epi Week", mode_options, index=mode_index,
        key="filter_week_mode", on_change=sync_week_mode, horizontal=True,
    )

    if week_mode == "Range":
        def sync_week_range():
            st.session_state["persist_week_range"] = st.session_state["filter_week_range"]

        # Clamp any stored value to the current data's bounds
        stored_range = st.session_state["persist_week_range"]
        safe_range = (
            max(week_min, min(stored_range[0], week_max)),
            max(week_min, min(stored_range[1], week_max)),
        )
        epi_week_range = st.sidebar.slider(
            "Epi Week Range",
            min_value=week_min, max_value=week_max,
            value=safe_range,
            key="filter_week_range", on_change=sync_week_range,
        )
    else:
        def sync_single_week():
            st.session_state["persist_single_week"] = st.session_state["filter_single_week"]

        stored_single = st.session_state["persist_single_week"]
        safe_single = max(week_min, min(stored_single, week_max))
        single_week = st.sidebar.number_input(
            "Epi Week",
            min_value=week_min, max_value=week_max,
            value=safe_single,
            key="filter_single_week", on_change=sync_single_week,
        )
        epi_week_range = (single_week, single_week)

    # ---- Sex ----
    def sync_sex():
        st.session_state["persist_sex"] = st.session_state["filter_sex"]

    sex_options = ["All"] + sorted(clean_df["Gender"].unique().tolist())
    sex_index = (
        sex_options.index(st.session_state["persist_sex"])
        if st.session_state["persist_sex"] in sex_options else 0
    )
    sex_filter = st.sidebar.selectbox(
        "Sex", options=sex_options, index=sex_index,
        key="filter_sex", on_change=sync_sex,
    )

    # ---- Apply ----
    filtered_df = analytics.filter_by_selection(
        clean_df,
        state=None if state_filter == "All" else state_filter,
        lga=None if lga_filter == "All" else lga_filter,
        epi_week_range=epi_week_range,
        sex=None if sex_filter == "All" else sex_filter,
    )

    return filtered_df