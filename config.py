"""
config.py
=========
Central configuration for the Mpox Surveillance Dashboard.
Paths, theme system, epi constants. No business logic here.
"""

from pathlib import Path

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
ASSETS_DIR = ROOT_DIR / "assets"

LINE_LIST_STORE_PATH = DATA_DIR / "merged_line_list.parquet"   # persisted merged data
STYLE_CSS_PATH = ROOT_DIR / "style.css"
LOGO_PATH = ASSETS_DIR / "ncdc_logo.png"

APP_TITLE = "Mpox Surveillance Dashboard"
APP_SUBTITLE = "NCDC Emergency Operations Centre"
APP_ICON = str(LOGO_PATH)

# ----------------------------------------------------------------------------
# BRAND COLOR SYSTEM -- placeholder, swap in exact NCDC hex values before build
# ----------------------------------------------------------------------------
BRAND = "#00693E"   # placeholder NCDC green

THEMES = {
    "dark": {},   # TODO: mirror sales dashboard THEMES structure with NCDC palette
    "light": {},  # TODO
}

# Semantic colors -- meaning-driven, not decorative (see brainstorm notes)
CLASSIFICATION_COLORS = {
    "Confirmed": "#C33F32",
    "Probable": "#D9A441",
    "Suspected": "#B38A58",
}

OUTCOME_COLORS = {
    "Recovered": "#1F8F5F",
    "Died": "#C33F32",
    "Alive": "#5B7A99",
}

# ----------------------------------------------------------------------------
# EPI CONSTANTS
# ----------------------------------------------------------------------------
CLASSIFICATION_ORDER = ["Suspected", "Probable", "Confirmed"]
OUTCOME_ORDER = ["Alive", "Recovered", "Died"]
NIGERIA_STATES = []  # TODO: full 36 states + FCT list

# Epi year uses Nigeria's epi week calendar, not calendar year

# ----------------------------------------------------------------------------
# NAVIGATION
# ----------------------------------------------------------------------------
NAV_ITEMS = [
    {"label": "Overview", "icon": "home", "page": "app.py"},
    {"label": "Epi Curve & Trends", "icon": "trending-up", "page": "pages/2_Epi_Curve_Trends.py"},
    {"label": "Geographic", "icon": "globe", "page": "pages/3_Geographic.py"},
    {"label": "Demographics & Classification", "icon": "users", "page": "pages/4_Demographics_Classification.py"},
    {"label": "Outcomes", "icon": "activity", "page": "pages/5_Outcomes.py"},
    {"label": "Rt & Clustering", "icon": "chart-bar", "page": "pages/6_Rt_Clustering.py"},
    {"label": "Data Quality", "icon": "flask", "page": "pages/7_Data_Quality.py"},
]
