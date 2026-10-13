"""
pages/7_Data_Quality.py
Cleaning pipeline summary, field completeness, missing values, duplicate checks
Logic deferred to build phase.
"""
import streamlit as st
import pandas as pd
import preprocessing
import analytics
import os
import preprocessing

STORE_PATH = "data/merged_line_list.parquet"

st.title("Data Quality")

if "last_quality_report" not in st.session_state or "last_upload_rows" not in st.session_state:
    st.info("No upload has been processed yet this session. Upload a line list on the Overview page to see quality metrics here.")
else:
    quality_report = st.session_state["last_quality_report"]
    total_rows = st.session_state["last_upload_rows"]

    tiered = analytics.get_quality_summary(quality_report, total_rows)

    tier_colors = {
        "optimal": "#1DBF83",
        "acceptable": "#1DBF83",
        "attention": "#D9A441",
        "critical": "#C33F32",
        "n/a": "#8891A5",
    }
    tier_labels = {
        "optimal": "Optimal",
        "acceptable": "Acceptable",
        "attention": "Attention Required",
        "critical": "Critical",
        "n/a": "—",
    }

    recommendations = {
        "duplicate_epid_numbers": "Review the source line list for repeated Epid Numbers before re-uploading. If a case was genuinely re-entered, keep only the most recent record.",
        "naming_conflicts": "Standardize LGA name spelling/capitalization at the point of data entry, or provide a reference list of official LGA names to data collectors.",
        "outlier_count": "Verify ages flagged as negative or over 110 years directly with the reporting facility — likely a data entry error (e.g. wrong field, transposed digits).",
        "bad_outcome_count": "Check records where an Outcome was recorded for a non-Confirmed case — this shouldn't happen under current classification logic and may indicate a data entry or classification error upstream.",
        "missing_lab_date_count": "Follow up with the laboratory to confirm whether these samples were tested; if untested, the specimen date field may need correction.",
    }

    # ---- Pipeline stage strip ----
    st.markdown('<div class="section-header"><span class="icon">▣</span>Cleaning Pipeline</div>', unsafe_allow_html=True)
    stage_col1, stage_col2, stage_col3, stage_col4 = st.columns(4)
    with stage_col1:
        st.markdown("**1. Raw Ingest**")
        st.caption(f"{total_rows} rows loaded")
    with stage_col2:
        st.markdown("**2. Validation**")
        st.caption("Columns checked")
    with stage_col3:
        st.markdown("**3. Deduplication**")
        st.caption(f"{quality_report.get('duplicate_epid_numbers', 0)} duplicate(s) found")
    with stage_col4:
        st.markdown("**4. Geographic Cleanup**")
        st.caption(f"{quality_report.get('naming_conflicts', 0)} LGA naming issue(s)")

    # ---- Key metric cards, with tier + recommended action ----
    st.markdown('<div class="section-header"><span class="icon">☰</span>Key Checks</div>', unsafe_allow_html=True)

    metric_checks = [
        ("duplicate_epid_numbers", "Duplicate Epid Numbers"),
        ("naming_conflicts", "LGA Naming Conflicts"),
        ("outlier_count", "Outlier Ages"),
        ("bad_outcome_count", "Inconsistent Outcomes"),
        ("missing_lab_date_count", "Missing Lab Test Dates"),
    ]

    cols = st.columns(len(metric_checks))
    for col, (key, label) in zip(cols, metric_checks):
        entry = tiered.get(key, {"value": 0, "tier": "n/a"})
        with col:
            st.metric(label=label, value=int(entry["value"]))
            color = tier_colors.get(entry["tier"], "#8891A5")
            st.markdown(
                f"<span style='color:{color}; font-size:0.8rem; font-weight:600;'>"
                f"{tier_labels.get(entry['tier'], '—')}</span>",
                unsafe_allow_html=True,
            )
            if entry["value"] > 0 and key in recommendations:
                st.caption(recommendations[key])

    # ---- Date parsing failures ----
    date_failure_keys = [k for k in quality_report if k.endswith("_invalid_dates")]
    if date_failure_keys:
        st.markdown('<div class="section-header"><span class="icon">◈</span>Date Parsing Failures</div>', unsafe_allow_html=True)
        date_failures = {
            k.replace("_invalid_dates", ""): quality_report[k]
            for k in date_failure_keys if quality_report[k] > 0
        }
        if date_failures:
            df_dates = pd.DataFrame(
                list(date_failures.items()), columns=["Field", "Invalid Count"]
            )
            st.dataframe(df_dates, hide_index=True)
            st.caption("Dates that could not be parsed were likely entered in an unexpected format. Confirm the reporting template uses a consistent date format (DD/MM/YYYY) before the next upload.")
        else:
            st.caption("No date parsing failures.")

    # ---- Classification counts (context, not a quality issue itself) ----
    if "classification_counts" in quality_report:
        st.markdown('<div class="section-header"><span class="icon">▲</span>Classification Breakdown (This Upload)</div>', unsafe_allow_html=True)
        class_counts = quality_report["classification_counts"]
        df_class = pd.DataFrame(
            list(class_counts.items()), columns=["Classification", "Count"]
        )
        st.dataframe(df_class, hide_index=True)

    st.markdown(
        """
        <div class='insight-card'>
        <strong>Note:</strong> These metrics reflect the most recently uploaded file, 
        not the full accumulated line list. Re-upload a file to refresh this page.
        </div>
        """,
        unsafe_allow_html=True,
    )