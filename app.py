"""
app.py -- Router only. Renders nothing itself; defines pages and navigation.
"""
import os
import streamlit as st
import db

st.set_page_config(
    page_title="Mpox Dashboard",
    layout="wide"
)

# Inject custom CSS theme (NCDC palette, KPI cards, sidebar styling)
with open("style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Access gate: only active in live mode (database configured).
# The public showcase has no database secret, so it skips this entirely.
# If APP_ACCESS_CODE is not set, nobody can get in (fails closed).
if db.is_configured():
    if not st.session_state.get("authed"):
        code = st.text_input("Access code", type="password")
        if code and code == os.getenv("APP_ACCESS_CODE"):
            st.session_state["authed"] = True
            st.rerun()
        st.stop()

overview = st.Page("pages/1_Overview.py", title="Overview", icon=":material/home:")
epi_curve = st.Page("pages/2_Epi_Curve_Trends.py", title="Epi Curve & Trends", icon=":material/show_chart:")
geographic = st.Page("pages/3_Geographic.py", title="Geographic", icon=":material/map:")
demographics = st.Page("pages/4_Demographics_Classification.py", title="Demographics & Classification", icon=":material/groups:")
outcomes = st.Page("pages/5_Outcomes.py", title="Outcomes", icon=":material/monitor_heart:")
rt_clustering = st.Page("pages/6_Rt_Clustering.py", title="Rt & Clustering", icon=":material/bubble_chart:")
data_quality = st.Page("pages/7_Data_Quality.py", title="Data Quality", icon=":material/fact_check:")

pg = st.navigation([
    overview,
    epi_curve,
    geographic,
    demographics,
    # outcomes,
    rt_clustering,
    data_quality,
])

pg.run()