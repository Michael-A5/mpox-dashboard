"""
pages/4_Demographics_Classification.py
age/sex breakdown, classification funnel
Logic deferred to build phase.
"""
import streamlit as st
import pandas as pd
import altair as alt
import analytics
import utils
import preprocessing

try:
    clean_df = preprocessing.load_store()
except Exception:
    clean_df = pd.DataFrame()
    st.info("No data uploaded yet")

st.title("Demographics & Classification")

if not clean_df.empty:
    filtered_df = utils.render_sidebar_filters(clean_df)

    # ---- Classification switcher for the pyramid ----
    st.markdown('<div class="section-header"><span class="icon">▤</span>Age / Sex Distribution</div>', unsafe_allow_html=True)

    classification_options = ["All"] + sorted(filtered_df["Classification"].unique().tolist())
    pyramid_classification = st.selectbox(
        "Classification", options=classification_options, key="pyramid_classification"
    )

    pyramid_source_df = (
        filtered_df if pyramid_classification == "All"
        else filtered_df[filtered_df["Classification"] == pyramid_classification]
    )

    age_sex_data = analytics.get_age_sex_breakdown(pyramid_source_df)

    if age_sex_data.empty:
        st.info("No cases match the current filters and classification selection.")
    else:
        pyramid_data = age_sex_data.melt(
            id_vars="age_bracket", var_name="Gender", value_name="count"
        )
        pyramid_data["count"] = pyramid_data.apply(
            lambda r: -r["count"] if r["Gender"] == "Male" else r["count"], axis=1
        )

        chart = alt.Chart(pyramid_data).mark_bar().encode(
            x=alt.X("count:Q", title="Count", axis=alt.Axis(labelExpr="abs(datum.value)")),
            y=alt.Y("age_bracket:N", sort="-y", title="Age Bracket"),
            color=alt.Color(
                "Gender:N",
                scale=alt.Scale(domain=["Male", "Female"], range=["#5B7A99", "#E84393"]),
            ),
            tooltip=["age_bracket", "Gender", alt.Tooltip("count:Q", title="Count", format="d")]
        ).properties(height=400)

        st.altair_chart(chart, use_container_width=True)

    # ---- Classification breakdown ----
    st.markdown('<div class="section-header"><span class="icon">▣</span>Classification Breakdown</div>', unsafe_allow_html=True)

    breakdown = analytics.get_classification_breakdown(filtered_df)
    outlier_count = filtered_df["is_age_outlier"].sum()

    suspected_col, outlier_col = st.columns(2)

    with suspected_col:
        st.metric("Suspected (total tested)", breakdown["suspected"]["count"])

    with outlier_col:
        with st.container(key="outlier_card"):
            st.metric("Age Outliers Excluded", int(outlier_count))
            st.caption("Ages outside a valid range (negative or unrealistically high) — excluded from the age/sex chart above.")

    col1, col2 = st.columns(2)
    with col1:
        with st.container(key="demo_confirmed_card"):
            st.metric(
                "Confirmed",
                breakdown["confirmed"]["count"],
                f"{breakdown['confirmed']['pct']:.1f}% of suspected",
            )
    with col2:
        with st.container(key="demo_excluded_card"):
            st.metric(
                "Excluded",
                breakdown["excluded"]["count"],
                f"{breakdown['excluded']['pct']:.1f}% of suspected",
            )