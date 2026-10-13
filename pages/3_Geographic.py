"""
pages/3_Geographic.py
Nigeria choropleth (graduated fill for suspected), dot overlay for confirmed, 
state/LGA drilldown table
Logic deferred to build phase.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import analytics
import utils
import preprocessing

GEOJSON_PATH = "data/nigeria_states.geojson"
CENTROIDS_PATH = "data/nigeria_state_centroids.csv"

st.title("Geographic")

try:
    clean_df = preprocessing.load_store()
    if clean_df.empty:
        st.info("No data uploaded yet")
except Exception:
    clean_df = pd.DataFrame()
    st.info("No data uploaded yet")

if not clean_df.empty:
    filtered_df = utils.render_sidebar_filters(clean_df)

    @st.cache_data
    def load_nigeria_geojson():
        with open(GEOJSON_PATH, "r") as f:
            return json.load(f)
        
    nigeria_geojson = load_nigeria_geojson()

    centroids = pd.read_csv(CENTROIDS_PATH)
    state_counts = analytics.get_state_case_counts(filtered_df)

    # Reindex against the full 36-state list so states absent from the
    # uploaded data still get an explicit zero row, instead of being
    # dropped and left uncoloured on the map
    all_states = centroids["STATE"].unique()
    state_counts = (
        state_counts.set_index("STATE")
        .reindex(all_states, fill_value=0)
        .reset_index()
    )

    dot_data = centroids.merge(state_counts[["STATE", "confirmed"]], on="STATE", how="left")
    dot_data["confirmed"] = dot_data["confirmed"].fillna(0)

    # ---- Choropleth: tiered fill for suspected cases ----
    max_suspected = state_counts["suspected"].max()
    state_counts["suspected_tier"] = pd.cut(
        state_counts["suspected"],
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

    st.markdown('<div class="section-header"><span class="icon">◈</span>Nigeria Case Distribution</div>', unsafe_allow_html=True)

    fig = px.choropleth_map(
        state_counts,
        geojson=nigeria_geojson,
        locations="STATE",
        featureidkey="properties.STATE",
        color="suspected_tier",
        category_orders={"suspected_tier": list(tier_colors.keys())},
        color_discrete_map=tier_colors,
        map_style="carto-darkmatter-nolabels",
        zoom=5.5,
        center={"lat": 9.08, "lon": 8.69},
        opacity=1.0,
        hover_data={"suspected": True, "confirmed": True},
    )
    fig.update_traces(marker_line_width=1.5, marker_line_color="white")

    # State name labels
    fig.add_trace(go.Scattermap(
        lat=centroids["lat"], lon=centroids["lon"],
        mode="text", text=centroids["STATE"],
        textfont=dict(size=10, color="white"),
        hoverinfo="skip", showlegend=False,
    ))

    # ---- Confirmed-case dots, tiered sizing (fixed pixel sizes per bucket,
    # not continuous area scaling — guarantees visible size differences
    # regardless of the data's actual min/max in any filtered view) ----
    def get_dot_size(confirmed):
        if confirmed == 0:
            return 0
        elif confirmed <= 10:
            return 8
        elif confirmed <= 30:
            return 16
        elif confirmed <= 75:
            return 28
        else:
            return 42

    dot_data["dot_size"] = dot_data["confirmed"].apply(get_dot_size)

    fig.add_trace(go.Scattermap(
        lat=dot_data["lat"], lon=dot_data["lon"],
        mode="markers",
        marker=dict(
            size=dot_data["dot_size"],
            color="#E8493B",
            opacity=0.85,
        ),
        text=dot_data["STATE"] + ": " + dot_data["confirmed"].astype(int).astype(str) + " confirmed",
        hoverinfo="text",
        showlegend=False,
    ))

    # ---- Legend: fixed tiers, matching the actual size buckets used above ----
    legend_tiers = [
        ("1-10 confirmed", 8),
        ("11-30 confirmed", 16),
        ("31-75 confirmed", 28),
        ("75+ confirmed", 42),
    ]

    for label, size in legend_tiers:
        fig.add_trace(go.Scattermap(
            lat=[None], lon=[None],
            mode="markers",
            marker=dict(size=[size], color="#E8493B", opacity=0.85),
            name=label,
            legendgroup="confirmed",
            showlegend=True,
        ))

    fig.update_layout(
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        height=650,
        legend=dict(
            title="Confirmed cases",
            bgcolor="rgba(0,0,0,0.4)",
            x=1.02, y=0.35,
            xanchor="left", yanchor="middle",
        ),
    )

    st.plotly_chart(fig, use_container_width=True)

    # ---- Drillable state/LGA ranking table ----
    st.markdown('<div class="section-header"><span class="icon">☰</span>State / LGA Ranking</div>', unsafe_allow_html=True)

    state_options = ["All"] + sorted(filtered_df["STATE"].unique().tolist())
    selected_state = st.selectbox("Drill into state", state_options)

    ranking = analytics.get_state_lga_ranking(
        filtered_df, state_filter=None if selected_state == "All" else selected_state
    )
    st.dataframe(ranking)