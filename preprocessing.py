"""
preprocessing.py
Incremental merge pipeline: new upload -> validate columns -> clean
(dates, LGA naming, duplicate Case IDs) -> merge on Case ID into
PostgreSQL -> stamp last-updated + new-since-last-upload counts.
"""
import pandas as pd
import numpy as np
import os
import logging
from datetime import datetime
from pathlib import Path
from sqlalchemy import text
import db
import streamlit as st
from sqlalchemy import bindparam

COLUMN_MAP_TO_SQL = {
    "Epid Number": "epid_number",
    "Laboratory": "laboratory",
    "Lab Assigned Specimen ID": "lab_assigned_specimen_id",
    "Age(Years)": "age_years",
    "Age (Months)": "age_months",
    "Age (Days)": "age_days",
    "Gender": "gender",
    "STATE": "state",
    "LGA": "lga",
    "Village/town": "village_town",
    "Address": "address",
    "Facility/Referred From": "facility_referred_from",
    "Date of Hospitalization": "date_of_hospitalization",
    "Date of Symptom Onset": "date_of_symptom_onset",
    "Epi Week (Onset Week)": "epi_week_onset",
    "Date of onset of Fever": "date_of_fever_onset",
    "Date of Specimen Collection": "date_of_specimen_collection",
    "Specimen Types": "specimen_types",
    "Sample Tested": "sample_tested",
    "Initial/Repeat/Follow-up": "initial_repeat_followup",
    "Date specimen sent to Lab": "date_specimen_sent_to_lab",
    "Date Specimen Received at Lab": "date_specimen_received_at_lab",
    "Epi Week (Lab Received date)": "epi_week_lab_received",
    "Date Specimen Tested": "date_specimen_tested",
    "CT Value qRT-PCR Target (MPX)": "ct_value_mpx",
    "Result Interpretation MPX (Positive, Negative, Indeterminate, Pending)": "result_interpretation_mpx",
    "CT Value qRT-PCR II Target (VZV)": "ct_value_vzv",
    "Result Interpretation VZV (Positive, Negative, Indeterminate, Pending)": "result_interpretation_vzv",
    "Final Result Interpretation (Positive, Negative, Pending, Indeterminate)": "final_result_interpretation",
    "Comments": "comments",
    "HIV Differential Result": "hiv_differential_result",
    "EpiWeek(DSO)": "epiweek_dso",
    "Outcome (Alive, Recovered, Died)": "outcome",
    "Date of Outcome": "date_of_outcome",
    "Classification": "classification",
    "is_age_outlier": "is_age_outlier",
    "is_bad_outcome": "is_bad_outcome",
}

COLUMN_MAP_FROM_SQL = {v: k for k, v in COLUMN_MAP_TO_SQL.items()}

DATE_COLUMNS = [
    "Date of Hospitalization",
    "Date of Symptom Onset",
    "Date of onset of Fever",
    "Date of Specimen Collection",
    "Date specimen sent to Lab",
    "Date Specimen Received at Lab",
    "Date Specimen Tested",
    "Date of Outcome",
]


def preprocess(uploaded_file):

    quality_report = {
        "duplicate_epid_count": None,
        "classification_counts": {},
        "naming_conflicts": None,
        "outlier_age_count": None,
        "bad_outcome_count": None,
        "missing_lab_date_count": None,
        "date_parse_failures": {},
    }

    # 1. Load
    raw_df = pd.read_csv(uploaded_file, encoding="utf-8", low_memory=False)

    # 2. Validate structure
    required_columns = [
        "S/N",
        "Laboratory",
        "Lab Assigned Specimen ID",
        "Epid Number",
        "Age(Years)",
        "Age (Months)",
        "Age (Days)",
        "Gender",
        "STATE",
        "LGA",
        "Village/town",
        "Address",
        "Facility/Referred From",
        "Date of Hospitalization",
        "Date of Symptom Onset",
        "Epi Week (Onset Week)",
        "Date of onset of Fever",
        "Date of Specimen Collection",
        "Specimen Types",
        "Sample Tested",
        "Initial/Repeat/Follow-up",
        "Date specimen sent to Lab",
        "Date Specimen Received at Lab",
        "Epi Week (Lab Received date)",
        "Date Specimen Tested",
        "CT Value qRT-PCR Target (MPX)",
        "Result Interpretation MPX (Positive, Negative, Indeterminate, Pending)",
        "CT Value qRT-PCR II Target (VZV)",
        "Result Interpretation VZV (Positive, Negative, Indeterminate, Pending)",
        "Final Result Interpretation (Positive, Negative, Pending, Indeterminate)",
        "Comments",
        "HIV Differential Result",
        "EpiWeek(DSO)",
        "Outcome (Alive, Recovered, Died)",
        "Date of Outcome"
    ]
    missing_columns = [col for col in required_columns if col not in raw_df.columns]

    if missing_columns:
        raise ValueError(f"Missing columns: {', '.join(missing_columns)}")

    # 3. Confirm no PII columns snuck in (real SORMAS exports may include them)
    pii_columns = ["Surname", "Other Names"]
    if any(col in raw_df.columns for col in pii_columns):
        raw_df = raw_df.drop(columns=[c for c in pii_columns if c in raw_df.columns])

    # 4. Parse dates
    for col in DATE_COLUMNS:
        original_non_null = raw_df[col].notna().sum()
        raw_df[col] = pd.to_datetime(raw_df[col], errors="coerce")
        failed = original_non_null - raw_df[col].notna().sum()
        quality_report[f"{col}_invalid_dates"] = failed

    # 5. Derive Classification from Final Result Interpretation
    classification_map = {
        "Positive": "Confirmed",
        "Negative": "Excluded",
        "Pending": "Suspected",
        "Indeterminate": "Probable"
    }

    raw_df["Classification"] = (
        raw_df["Final Result Interpretation (Positive, Negative, Pending, Indeterminate)"]
        .map(classification_map)
        .fillna("Unknown")
    )

    quality_report["classification_counts"] = raw_df["Classification"].value_counts().to_dict()

    # 6. Deduplicate on Epid Number (within this single upload)
    duplicate_mask = raw_df.duplicated(subset="Epid Number", keep="first")
    duplicate_count = duplicate_mask.sum()
    quality_report["duplicate_epid_numbers"] = duplicate_count

    raw_df = raw_df.drop_duplicates(subset="Epid Number", keep="last")

    # 7. Standardise LGA naming
    raw_df["LGA_clean"] = raw_df["LGA"].str.strip().str.title()
    naming_conflicts = (raw_df["LGA"] != raw_df["LGA_clean"]).sum()
    quality_report["naming_conflicts"] = naming_conflicts

    # 8. Flag outlier ages
    outlier_mask = (raw_df["Age(Years)"] < 0) | (raw_df["Age(Years)"] > 110)
    outlier_count = outlier_mask.sum()
    quality_report["outlier_count"] = outlier_count

    # 9. Outcome consistency check
    bad_outcome_mask = (
        (raw_df["Classification"] != "Confirmed")
        & (raw_df["Outcome (Alive, Recovered, Died)"].notna())
    )
    bad_outcome_count = bad_outcome_mask.sum()
    quality_report["bad_outcome_count"] = bad_outcome_count

    # 10. Missing lab test date check
    missing_lab_date_count = raw_df["Date Specimen Tested"].isna().sum()
    quality_report["missing_lab_date_count"] = missing_lab_date_count

    # 11. Build final clean dataframe
    clean_df = raw_df.copy()
    clean_df["LGA"] = clean_df["LGA_clean"]
    clean_df = clean_df.drop(columns=["LGA_clean"])
    clean_df["is_age_outlier"] = outlier_mask
    clean_df["is_bad_outcome"] = bad_outcome_mask

    # 12. Return both outputs
    return clean_df, quality_report


def merge_into_store(clean_df, table_name="cases"):
    """
    Upserts clean_df into PostgreSQL: inserts new Epid Numbers, updates
    existing ones on conflict. Returns the FULL refreshed store (matching
    dataframe columns your analytics.py functions expect), plus new/updated counts.
    """
    # Demo mode: no database configured, so uploads can't be saved
    if not db.is_configured():
        raise ValueError("Uploads are disabled in demo mode.")

    engine = db.get_engine()

    sql_ready_df = clean_df.rename(columns=COLUMN_MAP_TO_SQL)
    sql_ready_df = sql_ready_df[[c for c in COLUMN_MAP_TO_SQL.values() if c in sql_ready_df.columns]]

    # pg8000 can't bind numpy booleans, so convert to native Python bool
    sql_ready_df["is_age_outlier"] = sql_ready_df["is_age_outlier"].apply(bool)
    sql_ready_df["is_bad_outcome"] = sql_ready_df["is_bad_outcome"].apply(bool)

    incoming_ids = tuple(sql_ready_df["epid_number"].tolist())

    with engine.connect() as conn:
        if incoming_ids:
            existing_ids_result = conn.execute(
                text("SELECT epid_number FROM cases WHERE epid_number IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": list(incoming_ids)}
            )
            existing_ids = set(row[0] for row in existing_ids_result)
        else:
            existing_ids = set()

    new_count = len(set(incoming_ids) - existing_ids)
    updated_count = len(set(incoming_ids) & existing_ids)

    try:
        sql_ready_df.to_sql("temp_upload_staging", engine, if_exists="replace", index=False)
    except Exception as e:
        st.error(f"Staging write failed: {type(e).__name__}: {e}")
        raise

    with engine.connect() as conn:
        columns = sql_ready_df.columns.tolist()
        columns_str = ", ".join(columns)
        update_str = ", ".join([f"{c} = EXCLUDED.{c}" for c in columns if c != "epid_number"])

        upsert_query = text(f"""
            INSERT INTO {table_name} ({columns_str})
            SELECT {columns_str} FROM temp_upload_staging
            ON CONFLICT (epid_number)
            DO UPDATE SET {update_str}
        """)
        conn.execute(upsert_query)
        conn.commit()

    load_store.clear()
    merged_df = load_store(table_name)

    return merged_df, new_count, updated_count


@st.cache_data(ttl=600)
def load_store(table_name="cases"):
    """
    Loads the full store from PostgreSQL, renamed back to the original
    messy column names your analytics.py / preprocessing.py logic expects.
    Falls back to the demo parquet when no database is configured.
    """
    if not db.is_configured():
        df = pd.read_parquet("data/demo_line_list.parquet")
    else:
        engine = db.get_engine()
        df = pd.read_sql(text(f"SELECT * FROM {table_name}"), engine)
        df = df.rename(columns=COLUMN_MAP_FROM_SQL)

    # Postgres returns plain date objects, so restore proper datetime columns
    for col in DATE_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    return df