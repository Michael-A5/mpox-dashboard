"""
pages/1_Overview.py -- Overview page content.
KPI cards, operational mode gauge, national epi curve, top states, national CFR.
Logic deferred to build phase.
"""
import streamlit as st
import preprocessing
import analytics
import utils
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import altair as alt
import json
import db

GEOJSON_PATH = "data/nigeria_states.geojson"
CENTROIDS_PATH = "data/nigeria_state_centroids.csv"
STATE_POP_PATH = "data/nigeria_state_population.csv"


@st.dialog("About this dashboard")
def show_disclaimer():
    st.write(
        "This dashboard uses a **synthetic line list**, modeled on real NCDC "
        "mpox reporting patterns and publicly available situation report data "
        "(case counts, state distribution, CFR trends). It does **not** "
        "contain real patient data."
    )
    if st.button("Got it", key="disclaimer_ack_button"):
        st.session_state["seen_disclaimer"] = True
        st.rerun()

if "seen_disclaimer" not in st.session_state:
    st.session_state["seen_disclaimer"] = False

if not st.session_state["seen_disclaimer"]:
    show_disclaimer()

# 1. Load the persistent store
try:
    clean_df = preprocessing.load_store()
    if clean_df.empty:
        st.info("No data uploaded yet. Upload a line list to get started.")
except Exception:
    clean_df = pd.DataFrame()
    st.info("No data uploaded yet. Upload a line list to get started.")

# 2. Upload widget (disabled in the hosted demo, where no database is configured)
if db.is_configured():
    uploaded_file = st.sidebar.file_uploader("Upload epidemiological data", type="csv")
else:
    uploaded_file = None
    st.sidebar.caption("Upload is disabled in the public demo.")

if uploaded_file is not None:
    file_signature = (uploaded_file.name, uploaded_file.size)
    if st.session_state.get("last_processed_file") != file_signature:
        try:
            new_clean_df, quality_report = preprocessing.preprocess(uploaded_file)
            merged_df, new_count, updated_count = preprocessing.merge_into_store(new_clean_df)
            preprocessing.load_store.clear()

            clean_df = merged_df
            st.session_state["last_processed_file"] = file_signature
            st.session_state["last_upload_message"] = f"{new_count} new cases, {updated_count} updated"
            st.session_state["last_upload_time"] = datetime.now().strftime("%d %b %Y, %H:%M")
            st.session_state["last_quality_report"] = quality_report
            st.session_state["last_upload_rows"] = len(new_clean_df)
        except ValueError as e:
            st.error(str(e))

    if "last_upload_message" in st.session_state:
        st.success(st.session_state["last_upload_message"])

if "last_upload_time" not in st.session_state:
    st.session_state["last_upload_time"] = "No uploads yet"
last_upload_timestamp = st.session_state["last_upload_time"]

# 3. Sidebar filters
filtered_df = utils.render_sidebar_filters(clean_df)

# 4. Title + date pill
today_str = datetime.now().strftime("%A, %B %d, %Y")
st.markdown(f"<div class='date-pill'>{today_str}</div>", unsafe_allow_html=True)
st.title("Mpox Dashboard")

st.markdown(
    "<div class='welcome-banner'><strong>Welcome back</strong> — here's how the outbreak response is performing.</div>",
    unsafe_allow_html=True,
)

st.markdown(
    f"Last upload: {last_upload_timestamp} · Source: manual line list upload · {len(filtered_df)} total cases"
)

if filtered_df.empty:
    st.warning("No data available for the selected filters.")
    st.stop()

# ---- Precompute everything needed below ----
kpis = analytics.get_summary_kpis(filtered_df)
cfr_data = analytics.get_national_cfr(filtered_df)
top_states = analytics.get_top_states(filtered_df)

# Extra context for Executive Insights: Rt, flagged states, outcomes
confirmed_count_check = (filtered_df["Classification"] == "Confirmed").sum()
rt_summary = None
if confirmed_count_check >= 10:
    rt_data_summary = analytics.get_rt_estimate(filtered_df)
    if not rt_data_summary.empty:
        rt_summary = rt_data_summary.iloc[-1]

outcome_summary = analytics.get_outcome_summary(filtered_df)

state_pop_df = pd.read_csv(STATE_POP_PATH)
concentration_data = analytics.get_case_concentration(filtered_df, state_pop_df)
flagged_states_count = (concentration_data["relative_risk"] >= 1.5).sum()

left_col, right_col = st.columns([1, 3])

# =========================================================
# LEFT COLUMN: Map (top) + Executive Insights (bottom)
# =========================================================
with left_col:
    st.markdown('<div class="section-header"><span class="icon">◈</span>Geographic Spread</div>', unsafe_allow_html=True)

    @st.cache_data
    def load_nigeria_geojson():
        with open(GEOJSON_PATH, "r") as f:
            return json.load(f)
    nigeria_geojson = load_nigeria_geojson()

    centroids = pd.read_csv(CENTROIDS_PATH)
    mini_state_counts = analytics.get_state_case_counts(filtered_df)
    mini_dot_data = centroids.merge(mini_state_counts[["STATE", "confirmed"]], on="STATE", how="left")
    mini_dot_data["confirmed"] = mini_dot_data["confirmed"].fillna(0)

    # ---- Tiered teal fill, matching pages/3_Geographic.py ----
    max_suspected = mini_state_counts["suspected"].max()
    mini_state_counts["suspected_tier"] = pd.cut(
        mini_state_counts["suspected"],
        bins=[-1, 0, 5, 15, 30, max(max_suspected + 1, 31)],
        labels=["No cases", "Low (1-5)", "Moderate (6-15)", "High (16-30)", "Very High (30+)"]
    )

    tier_colors = {
        "No cases": "#0e1424",
        "Low (1-5)": "#c6f0e5",
        "Moderate (6-15)": "#7ad9c0",
        "High (16-30)": "#2ba889",
        "Very High (30+)": "#0e5c47",
    }

    mini_fig = px.choropleth_map(
        mini_state_counts, geojson=nigeria_geojson, locations="STATE",
        featureidkey="properties.STATE", color="suspected_tier",
        category_orders={"suspected_tier": list(tier_colors.keys())},
        color_discrete_map=tier_colors,
        map_style="carto-darkmatter-nolabels",
        zoom=4.5, center={"lat": 9.08, "lon": 8.69}, opacity=1.0,
    )
    mini_fig.update_traces(marker_line_width=1, marker_line_color="white")

    mini_max_confirmed = max(int(mini_dot_data["confirmed"].max()), 1)
    mini_sizeref_val = 2. * mini_max_confirmed / (40.**2)

    mini_fig.add_trace(go.Scattermap(
        lat=mini_dot_data["lat"], lon=mini_dot_data["lon"], mode="markers",
        marker=dict(size=mini_dot_data["confirmed"], sizemode="area", sizeref=mini_sizeref_val,
                    sizemin=3, color="#E8493B", opacity=0.85),
        text=mini_dot_data["STATE"] + ": " + mini_dot_data["confirmed"].astype(int).astype(str) + " confirmed",
        hoverinfo="text", showlegend=False,
    ))
    mini_fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=450,
                            showlegend=False, coloraxis_showscale=False)
    st.plotly_chart(mini_fig, use_container_width=True)
    st.page_link("pages/3_Geographic.py", label="View full Geographic page →")

    st.markdown('<div class="section-header"><span class="icon">✦</span>Executive Insights</div>', unsafe_allow_html=True)

    insights = []
    if kpis["confirmed_count"] > 0:
        insights.append(
            f"<strong>{kpis['confirmed_count']}</strong> confirmed cases recorded, with a national CFR of "
            f"<strong>{cfr_data['cfr_percent']:.1f}%</strong> ({cfr_data['deaths']} deaths / {cfr_data['confirmed']} confirmed)."
        )
    if not top_states.empty:
        top_state_row = top_states.iloc[0]
        insights.append(
            f"<strong>{top_state_row['STATE']}</strong> carries the highest reported burden, with "
            f"{int(top_state_row['confirmed'])} confirmed and {int(top_state_row['suspected'])} suspected cases."
        )
    if kpis["suspected_count"] > 0:
        insights.append(f"<strong>{kpis['suspected_count']}</strong> cases remain pending lab confirmation.")

    if rt_summary is not None:
        rt_trend_word = "growing" if rt_summary["r_mean"] > 1.0 else "declining"
        insights.append(
            f"Current Rt is <strong>{rt_summary['r_mean']:.2f}</strong> "
            f"(95% CI {rt_summary['r_lower']:.2f}–{rt_summary['r_upper']:.2f}), "
            f"suggesting transmission is currently <strong>{rt_trend_word}</strong>."
        )

    if outcome_summary["recovered"] > 0 or outcome_summary["died"] > 0:
        insights.append(
            f"Of confirmed cases with a resolved outcome, <strong>{outcome_summary['recovered']}</strong> "
            f"have recovered and <strong>{outcome_summary['died']}</strong> have died; "
            f"<strong>{outcome_summary['pending']}</strong> confirmed case(s) still have no outcome recorded."
        )

    if flagged_states_count > 0:
        insights.append(
            f"<strong>{flagged_states_count}</strong> state(s) currently show case concentration "
            f"1.5× or more above their population-predicted share — see Rt & Clustering for detail."
        )

    if not insights:
        insights.append("No cases currently match the selected filters.")

    for i in insights:
        st.markdown(f"<div class='insight-card'><span class='insight-icon'>●</span>{i}</div>", unsafe_allow_html=True)

# =========================================================
# RIGHT COLUMN: KPIs + Gauge, Epi Curve + (Pyramid | Donut)
# =========================================================
with right_col:
    kpi_col, gauge_col = st.columns([3, 1])

    with kpi_col:
        st.markdown('<div class="section-header"><span class="icon">▣</span>Key Performance Indicators</div>', unsafe_allow_html=True)

        kcol1, kcol2, kcol3, kcol4 = st.columns(4)
        with kcol1:
            st.metric(label="Total Cases", value=kpis["total_cases"])
        with kcol2:
            with st.container(key="confirmed_card"):
                st.metric(label="Confirmed", value=kpis["confirmed_count"])
        with kcol3:
            with st.container(key="suspected_card"):
                st.metric(label="Pending Lab Result", value=kpis["suspected_count"])
        with kcol4:
            with st.container(key="deaths_card"):
                st.metric(label="Deaths", value=kpis["deaths_count"])

        cfr_col, _ = st.columns([1, 3])
        with cfr_col:
            with st.container(key="cfr_card"):
                st.metric(label="National CFR", value=f"{cfr_data['cfr_percent']:.1f}%")
                st.caption(f"{cfr_data['deaths']} deaths / {cfr_data['confirmed']} confirmed")

    with gauge_col:
        st.markdown('<div class="section-header"><span class="icon">◉</span>Operational Mode</div>', unsafe_allow_html=True)

        threshold_data = analytics.get_epidemic_threshold(filtered_df)

        gauge_max = max(threshold_data["epidemic_threshold"] * 1.3, threshold_data["latest_count"] * 1.2, 5)

        gauge_fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=threshold_data["latest_count"],
            number={"font": {"size": 28}},
            gauge={
                "axis": {"range": [0, gauge_max]},
                "bar": {"color": "#1DBF83" if threshold_data["mode"] == "Watch" else ("#D9A441" if threshold_data["mode"] == "Alert" else "#C33F32")},
                "steps": [
                    {"range": [0, threshold_data["alert_threshold"]], "color": "rgba(29,191,131,0.2)"},
                    {"range": [threshold_data["alert_threshold"], threshold_data["epidemic_threshold"]], "color": "rgba(217,164,65,0.2)"},
                    {"range": [threshold_data["epidemic_threshold"], gauge_max], "color": "rgba(195,63,50,0.2)"},
                ],
            },
        ))
        gauge_fig.update_layout(
            height=180,
            margin={"r": 10, "t": 10, "l": 10, "b": 0},
        )
        st.plotly_chart(gauge_fig, use_container_width=True)
        st.caption(f"**{threshold_data['mode']}** · This week: {threshold_data['latest_count']} confirmed cases")
        if threshold_data["insufficient_data"]:
            st.caption("Insufficient historical data for a reliable threshold — showing raw count only.")

        # ---- Rt mini KPI ----
        confirmed_count = (filtered_df["Classification"] == "Confirmed").sum()
        if confirmed_count >= 10:
            rt_data = analytics.get_rt_estimate(filtered_df)
            if not rt_data.empty:
                latest_rt = rt_data.iloc[-1]
                with st.container(key="rt_mini_card"):
                    st.metric(label="Current Rt", value=f"{latest_rt['r_mean']:.2f}")
                    st.caption(f"95% CI: {latest_rt['r_lower']:.2f}–{latest_rt['r_upper']:.2f}")
                st.page_link("pages/6_Rt_Clustering.py", label="View full Rt & Clustering →")
        else:
            st.caption("Not enough confirmed cases yet for a reliable Rt estimate.")

    st.markdown('<div class="section-header"><span class="icon">▲</span>Epi Curve</div>', unsafe_allow_html=True)

    curve_data = analytics.get_epi_curve(filtered_df, granularity="week")
    try:
        curve_data["period_dt"] = pd.to_datetime(curve_data["period"] + "-1", format="%G-W%V-%u")
    except (ValueError, TypeError):
        curve_data["period_dt"] = pd.NaT
    curve_data = curve_data[curve_data["period_dt"].notna()]

    cutoff = pd.Timestamp.now() - pd.DateOffset(months=12)
    curve_data = curve_data[curve_data["period_dt"] >= cutoff]

    classifications = ["Confirmed", "Probable", "Suspected"]
    available_columns = [c for c in classifications if c in curve_data.columns]
    color_map = {"Confirmed": "#C33F32", "Probable": "#D9A441", "Suspected": "#1DBF83"}
    selected_colors = [color_map[c] for c in available_columns]

    if available_columns:
        st.bar_chart(curve_data, x="period", y=available_columns, stack=True, color=selected_colors)
    else:
        st.info("No data to show")
    st.page_link("pages/2_Epi_Curve_Trends.py", label="View full Epi Curve & Trends →")

    pyramid_col, donut_col = st.columns(2)

    with pyramid_col:
        st.markdown('<div class="section-header"><span class="icon">▤</span>Age / Sex</div>', unsafe_allow_html=True)

        mini_age_sex = analytics.get_age_sex_breakdown(filtered_df)
        if not mini_age_sex.empty:
            mini_pyramid = mini_age_sex.melt(id_vars="age_bracket", var_name="Gender", value_name="count")
            mini_pyramid["count"] = mini_pyramid.apply(
                lambda r: -r["count"] if r["Gender"] == "Male" else r["count"], axis=1
            )
            mini_chart = alt.Chart(mini_pyramid).mark_bar().encode(
                x=alt.X("count:Q", title=None, axis=alt.Axis(labelExpr="abs(datum.value)")),
                y=alt.Y("age_bracket:N", sort="-y", title=None),
                color=alt.Color(
                    "Gender:N",
                    scale=alt.Scale(domain=["Male", "Female"], range=["#5B7A99", "#E84393"]),
                    legend=None,
                ),
            ).properties(height=220)
            st.altair_chart(mini_chart, use_container_width=True)
        else:
            st.info("No data to show")
        st.page_link("pages/4_Demographics_Classification.py", label="View full Demographics page →")

    with donut_col:
        st.markdown('<div class="section-header"><span class="icon">◐</span>Sex Distribution</div>', unsafe_allow_html=True)

        sex_counts = filtered_df["Gender"].value_counts().reset_index()
        sex_counts.columns = ["Gender", "count"]

        if not sex_counts.empty:
            total = int(sex_counts["count"].sum())
            donut_fig = go.Figure(data=[go.Pie(
                labels=sex_counts["Gender"], values=sex_counts["count"], hole=0.6,
                marker=dict(colors=["#5B7A99", "#E84393"]),
            )])
            donut_fig.update_layout(
                showlegend=True, height=220, margin={"r": 0, "t": 0, "l": 0, "b": 0},
                annotations=[dict(text=str(total), x=0.5, y=0.5, font_size=24, showarrow=False, font_color="white")],
            )
            st.plotly_chart(donut_fig, use_container_width=True)
        else:
            st.info("No data to show")
        st.page_link("pages/4_Demographics_Classification.py", label="View full Demographics page →")

# 8. Top states table
st.markdown('<div class="section-header"><span class="icon">☰</span>Top States</div>', unsafe_allow_html=True)
st.dataframe(top_states)