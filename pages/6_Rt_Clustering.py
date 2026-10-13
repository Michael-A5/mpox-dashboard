"""
pages/6_Rt_Clustering.py
Rt estimation (EpiEstim), Kulldorff spatial clustering
Logic deferred to build phase.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
import analytics
import utils
import os
import preprocessing

try:
    clean_df = preprocessing.load_store()
except Exception:
    clean_df = pd.DataFrame()
    st.info("No data uploaded yet")

st.title("Rt & Clustering")

if not clean_df.empty:
    filtered_df = utils.render_sidebar_filters(clean_df)

    confirmed_count = (filtered_df["Classification"] == "Confirmed").sum()

    if confirmed_count < 10:
        st.warning(
            f"Only {confirmed_count} confirmed case(s) in the current selection. "
            "Rt estimates need at least 10 confirmed cases to be meaningful — "
            "adjust filters to include more data."
        )
    else:
        rt_data = analytics.get_rt_estimate(filtered_df)

        if rt_data.empty:
            st.info("Not enough data to estimate Rt for the current filters.")
        else:
            latest_row = rt_data.iloc[-1]
            previous_row = rt_data.iloc[-2] if len(rt_data) > 1 else latest_row

            if latest_row["r_mean"] > previous_row["r_mean"]:
                trend_label, trend_icon = "Increasing", "▲"
            elif latest_row["r_mean"] < previous_row["r_mean"]:
                trend_label, trend_icon = "Decreasing", "▼"
            else:
                trend_label, trend_icon = "Stable", "—"

            st.markdown('<div class="section-header"><span class="icon">▣</span>Effective Reproduction Number (Rt)</div>', unsafe_allow_html=True)

            rt_col, _ = st.columns([1, 3])
            with rt_col:
                with st.container(key="rt_card"):
                    st.metric(label="Current Rt", value=f"{latest_row['r_mean']:.2f}")
                    st.caption(
                        f"95% CI: {latest_row['r_lower']:.2f} – {latest_row['r_upper']:.2f}  ·  "
                        f"{trend_icon} {trend_label}"
                    )

            st.markdown('<div class="section-header"><span class="icon">▲</span>Rt Trajectory (95% Confidence Band)</div>', unsafe_allow_html=True)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=rt_data.index, y=rt_data["r_upper"],
                mode="lines", line=dict(width=0),
                showlegend=False, hoverinfo="skip",
            ))
            fig.add_trace(go.Scatter(
                x=rt_data.index, y=rt_data["r_lower"],
                mode="lines", line=dict(width=0),
                fill="tonexty", fillcolor="rgba(29,191,131,0.15)",
                name="95% CI", hoverinfo="skip",
            ))
            fig.add_trace(go.Scatter(
                x=rt_data.index, y=rt_data["r_mean"],
                mode="lines", line=dict(color="#1DBF83", width=2),
                name="Rt (median)",
            ))
            fig.add_hline(y=1.0, line_dash="dash", line_color="#E8493B",
                          annotation_text="Threshold Rt = 1.0", annotation_position="top left")

            fig.update_layout(
                margin={"r": 0, "t": 10, "l": 0, "b": 0},
                legend=dict(bgcolor="rgba(0,0,0,0.4)"),
                yaxis_title="Rt",
                yaxis=dict(range=[0, 4], dtick=1),
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown(
                """
                <div class='insight-card'>
                <strong>Methodology:</strong> Rt estimated using the Cori et al. (2013) method 
                (7-day sliding window), via the <code>epyestim</code> Python package. 
                Serial interval assumed: mean 8.5 days, SD 5.0 days, based on 
                <a href="https://doi.org/10.3201/eid2904.221622" target="_blank">
                Madewell et al. (2023), Emerging Infectious Diseases</a>. 
                This estimate was derived from a 2022 US outbreak (12 jurisdictions) and may not 
                fully reflect Nigerian transmission patterns. A 2025 study on Clade Ib in the DRC 
                found the serial interval varies by transmission mode — shorter for sexual 
                transmission, longer for non-sexual/household transmission — a distinction this 
                dataset does not currently capture.
                </div>
                """,
                unsafe_allow_html=True,
            )

# ---- Spatial Clustering ----
GEOJSON_STATE_PATH = "data/nigeria_states.geojson"
GEOJSON_LGA_PATH = "data/nigeria_lga_boundaries.geojson"
STATE_POP_PATH = "data/nigeria_state_population.csv"
LGA_POP_PATH = "data/nigeria_lga_population.csv"

RISK_THRESHOLD = 1.5

st.markdown('<div class="section-header"><span class="icon">◈</span>Case Concentration (Observed vs Expected)</div>', unsafe_allow_html=True)

if clean_df.empty:
    st.info("No data uploaded yet")
else:
    state_pop_df = pd.read_csv(STATE_POP_PATH)
    lga_pop_df = pd.read_csv(LGA_POP_PATH)

    with open(GEOJSON_STATE_PATH) as f:
        state_geojson = json.load(f)
    with open(GEOJSON_LGA_PATH) as f:
        lga_geojson = json.load(f)


    state_concentration = analytics.get_case_concentration(filtered_df, state_pop_df)

    # National LGA concentration — relative risk computed against the national total
    lga_concentration_national = analytics.get_lga_case_concentration(
        filtered_df, lga_pop_df, state_filter=None
    )
    lga_concentration_national["LGA_STATE_KEY"] = (
        lga_concentration_national["STATE"] + " | " + lga_concentration_national["LGA"]
    )

    map_col, lga_map_col = st.columns(2)

    with map_col:
        st.markdown("**State-level**")
        state_fig = px.choropleth_map(
            state_concentration,
            geojson=state_geojson,
            locations="STATE",
            featureidkey="properties.STATE",
            color="relative_risk",
            color_continuous_scale="Reds",
            range_color=(0, max(2, state_concentration["relative_risk"].max())),
            map_style="carto-darkmatter-nolabels",
            zoom=4.3,
            center={"lat": 9.08, "lon": 8.69},
            opacity=1.0,
            hover_data={"observed": True, "expected": ":.1f", "relative_risk": ":.2f"},
        )
        state_fig.update_traces(marker_line_width=1, marker_line_color="white")
        state_fig.update_layout(
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            height=420,
            coloraxis_colorbar=dict(title="Relative Risk"),
        )
        st.plotly_chart(state_fig, use_container_width=True)

    with lga_map_col:
        st.markdown("**LGA-level (National)**")

        if lga_concentration_national.empty:
            st.info("No LGA data available.")
        else:
            lga_fig = px.choropleth_map(
                lga_concentration_national,
                geojson=lga_geojson,
                locations="LGA_STATE_KEY",
                featureidkey="properties.STATE_LGA_KEY",
                color="relative_risk",
                color_continuous_scale="Reds",
                range_color=(0, max(2, lga_concentration_national["relative_risk"].max())),
                map_style="carto-darkmatter-nolabels",
                zoom=4.3,
                center={"lat": 9.08, "lon": 8.69},
                opacity=1.0,
                hover_data={"STATE": True, "observed": True, "expected": ":.1f", "relative_risk": ":.2f"},
            )
            lga_fig.update_traces(marker_line_width=0.5, marker_line_color="white")
            lga_fig.update_layout(
                margin={"r": 0, "t": 0, "l": 0, "b": 0},
                height=420,
                coloraxis_colorbar=dict(title="Relative Risk"),
            )
            st.plotly_chart(lga_fig, use_container_width=True)

    st.markdown('<div class="section-header"><span class="icon">☰</span>Flagged States (Relative Risk ≥ 1.5×)</div>', unsafe_allow_html=True)

    flagged = state_concentration[state_concentration["relative_risk"] >= RISK_THRESHOLD]
    if flagged.empty:
        st.info("No states currently exceed the 1.5× relative risk threshold.")
    else:
        display_cols = flagged[["STATE", "observed", "expected", "population_2022", "relative_risk"]].copy()
        display_cols["expected"] = display_cols["expected"].round(1)
        display_cols["relative_risk"] = display_cols["relative_risk"].round(2)
        display_cols = display_cols.reset_index(drop=True)
        display_cols.index = display_cols.index + 1
        st.dataframe(display_cols)

    st.markdown(
        """
        <div class='insight-card'>
        <strong>Methodology:</strong> This is a simplified observed-vs-expected case 
        concentration screen, <em>not</em> a formal Kulldorff spatial scan statistic. 
        Expected cases are calculated as each state's/LGA's share of the national (or 
        in-state) population, multiplied by total confirmed cases. Relative risk is the 
        ratio of observed to expected cases. No statistical significance testing 
        (e.g. Monte Carlo simulation) is performed — this is a screening indicator to 
        prioritize areas for further investigation, not a validated cluster detection 
        method. Population figures are 2022 NBS/NPC projections based on the 2006 
        census, the most recent available; Nigeria has not conducted a full census 
        since then. A formal Kulldorff analysis (e.g. via SaTScan) is recommended for 
        confirmatory spatial cluster detection once this dashboard moves to a 
        server-hosted deployment.
        </div>
        """,
        unsafe_allow_html=True,
    )