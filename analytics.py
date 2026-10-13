"""
analytics.py
Cached data loading + all aggregation logic: epi curve counts, CFR, Rt (EpiEstim),
spatial clustering (Kulldorff scan statistic), classification/outcome breakdowns.

Note on "suspected": every row in the dataset is a suspected case by
definition (clinical presentation matched the case definition, so the
person was sampled and tested). Confirmed/Excluded/Probable are mutually
exclusive subsets of that universal set, resolved via lab result. Functions
below that report a "suspected" count return the FULL group size (the
universal set), not just rows still labeled Classification == "Suspected"
(which only means "result still pending" — a narrower, different number,
used deliberately on the Overview page's "Pending Lab Result" KPI card).
"""
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from scipy.stats import gamma
import epyestim


@st.cache_data
def get_summary_kpis(filtered_df):
    total_cases = len(filtered_df)

    confirmed_count = (filtered_df["Classification"] == "Confirmed").sum()
    suspected_count = (filtered_df["Classification"] == "Suspected").sum()
    probable_count = (filtered_df["Classification"] == "Probable").sum()
    # Deaths only ever count against Confirmed cases (per earlier decision)
    deaths_count = ((filtered_df["Classification"] == "Confirmed") & (filtered_df["Outcome (Alive, Recovered, Died)"] == "Died")).sum()

    return {
        "total_cases": total_cases,
        "confirmed_count": confirmed_count,
        "suspected_count": suspected_count,
        "probable_count": probable_count,
        "deaths_count": deaths_count,
    }


@st.cache_data
def get_national_cfr(filtered_df):
    confirmed_count = (filtered_df["Classification"] == "Confirmed").sum()
    deaths_count = ((filtered_df["Classification"] == "Confirmed") & (filtered_df["Outcome (Alive, Recovered, Died)"] == "Died")).sum()

    if confirmed_count == 0:
        cfr = 0
    else:
        cfr = (deaths_count / confirmed_count) * 100

    return {
        "cfr_percent": cfr,
        "deaths": deaths_count,
        "confirmed": confirmed_count
    }


@st.cache_data
def get_top_states(filtered_df, n=5):
    # "suspected" = universal set = every row in the group, not just
    # Classification == "Suspected" (which only means "still pending")
    state_table = filtered_df.groupby("STATE").agg(
        suspected=("Classification", lambda s: len(s)),
        confirmed=("Classification", lambda s: (s == "Confirmed").sum()),
    ).reset_index()

    deaths_by_state = filtered_df[
        (filtered_df["Classification"] == "Confirmed") &
        (filtered_df["Outcome (Alive, Recovered, Died)"] == "Died")
    ].groupby("STATE").size().rename("deaths")

    state_table = state_table.merge(deaths_by_state, on="STATE", how="left")
    state_table["deaths"] = state_table["deaths"].fillna(0).astype(int)

    state_table["burden"] = state_table["suspected"] + state_table["confirmed"]
    state_table = state_table.sort_values("burden", ascending=False)
    state_table = state_table.drop(columns="burden")
    state_table = state_table.head(n)

    state_table = state_table.reset_index(drop=True)
    state_table.index = state_table.index + 1
    return state_table


@st.cache_data
def get_epi_curve(filtered_df, granularity="week", classifications=None):
    date_col = "Date of Symptom Onset"

    if classifications is not None:
        df = filtered_df[filtered_df["Classification"].isin(classifications)]
    else:
        df = filtered_df

    df = df.copy()

    if granularity == "day":
        df["period"] = df[date_col].dt.date
    elif granularity == "week":
        df["period"] = df["Epi Week (Onset Week)"]
    elif granularity == "month":
        df["period"] = df[date_col].dt.to_period("M").dt.start_time
    else:
        raise ValueError(f"Unknown granularity: {granularity}")

    curve_data = (
        df.groupby(["period", "Classification"])
        .size()
        .reset_index(name="count")
        .pivot(index="period", columns="Classification", values="count")
        .fillna(0)
        .reset_index()
    )

    return curve_data


def get_epi_week_start(year: int) -> date:
    """
    Nigeria's epi week 1 starts on the Sunday on/before January 4th
    (matches CDC/MMWR-style rule, confirmed against NCDC's 2026 calendar)
    """
    jan4 = date(year, 1, 4)
    days_since_sunday = (jan4.weekday() + 1) % 7
    return jan4 - timedelta(days=days_since_sunday)


@st.cache_data
def build_epi_calendar(years: list[int]) -> pd.DataFrame:
    rows = []
    for year in years:
        week1_start = get_epi_week_start(year)
        next_year_start = get_epi_week_start(year + 1)
        week_number = 1
        current_start = week1_start
        while current_start < next_year_start:
            week_end = current_start + timedelta(days=6)
            rows.append({
                "epi_year": year,
                "epi_week": week_number,
                "start_date": current_start,
                "end_date": week_end,
            })
            current_start = current_start + timedelta(days=7)
            week_number += 1

    calendar_df = pd.DataFrame(rows)
    calendar_df["start_date"] = pd.to_datetime(calendar_df["start_date"])
    calendar_df["end_date"] = pd.to_datetime(calendar_df["end_date"])
    return calendar_df


@st.cache_data
def get_epi_year_and_week(onset_date, epi_calendar_df: pd.DataFrame):
    match = epi_calendar_df[
        (epi_calendar_df["start_date"] <= onset_date)
        & (onset_date <= epi_calendar_df["end_date"])
    ]
    if match.empty:
        return None, None
    return match.iloc[0]["epi_year"], match.iloc[0]["epi_week"]


@st.cache_data
def get_epi_year_comparison(filtered_df):
    df = filtered_df.copy()

    years_present = df["Date of Symptom Onset"].dropna().dt.year.unique()
    years_to_build = sorted(years_present.tolist()) + [max(years_present) + 1]
    epi_calendar_df = build_epi_calendar(years_to_build)

    matched = df["Date of Symptom Onset"].apply(
        lambda d: get_epi_year_and_week(d, epi_calendar_df)
    )
    df["epi_year"] = matched.apply(lambda m: m[0])
    df["epi_week"] = matched.apply(lambda m: m[1])

    unmatched_count = df["epi_year"].isna().sum()
    df = df[df["epi_year"].notna()]

    comparison_data = (
        df.groupby(["epi_week", "epi_year"])
        .size()
        .reset_index(name="count")
        .pivot(index="epi_week", columns="epi_year", values="count")
        .reset_index()
    )

    return comparison_data, unmatched_count


@st.cache_data
def get_state_case_counts(filtered_df):
    # "suspected" = universal set = every row for that state
    state_counts = filtered_df.groupby("STATE").apply(
        lambda g: pd.Series({
            "suspected": len(g),
            "confirmed": (g["Classification"] == "Confirmed").sum(),
            "probable": (g["Classification"] == "Probable").sum(),
        })
    ).reset_index()

    state_counts = state_counts.sort_values("confirmed", ascending=False)
    state_counts = state_counts.reset_index(drop=True)
    state_counts.index = state_counts.index + 1
    return state_counts


@st.cache_data
def get_state_lga_ranking(filtered_df, state_filter=None):
    df = filtered_df
    if state_filter is not None:
        df = df[df["STATE"] == state_filter]
        group_by_col = "LGA"
    else:
        group_by_col = "STATE"

    # "suspected" = universal set = every row in the group
    ranking = df.groupby(group_by_col).apply(
        lambda g: pd.Series({
            "suspected": len(g),
            "confirmed": (g["Classification"] == "Confirmed").sum(),
            "deaths": ((g["Classification"] == "Confirmed") & (g["Outcome (Alive, Recovered, Died)"] == "Died")).sum(),
        })
    ).reset_index()

    ranking = ranking.sort_values("confirmed", ascending=False)
    ranking = ranking.reset_index(drop=True)
    ranking.index = ranking.index + 1
    return ranking


def filter_by_selection(clean_df, state=None, lga=None, epi_week_range=None, sex=None):
    df = clean_df
    if state is not None:
        df = df[df["STATE"] == state]
    if lga is not None:
        df = df[df["LGA"] == lga]
    if epi_week_range is not None:
        week_numbers = df["Epi Week (Onset Week)"].str.extract(r"W(\d+)")[0].astype(int)
        df = df[
            (week_numbers >= epi_week_range[0])
            & (week_numbers <= epi_week_range[1])
        ]
    if sex is not None:
        df = df[df["Gender"] == sex]
    return df


@st.cache_data
def get_age_sex_breakdown(filtered_df):
    df = filtered_df.copy()
    age_bins = [0, 9, 19, 29, 39, 49, 59, 200]
    age_labels = ["0-9", "10-19", "20-29", "30-39", "40-49", "50-59", "60+"]

    df["age_bracket"] = pd.cut(df["Age(Years)"], bins=age_bins, labels=age_labels)
    df = df[df["is_age_outlier"] == False]

    breakdown = (
        df.groupby(["age_bracket", "Gender"], observed=False)
        .size()
        .reset_index(name="count")
        .pivot(index="age_bracket", columns="Gender", values="count")
        .fillna(0)
        .reset_index()
    )
    return breakdown


@st.cache_data
def get_classification_breakdown(filtered_df):
    suspected_total = len(filtered_df)

    confirmed_count = (filtered_df["Classification"] == "Confirmed").sum()
    excluded_count = (filtered_df["Classification"] == "Excluded").sum()

    confirmed_pct = (confirmed_count / suspected_total * 100) if suspected_total > 0 else 0
    excluded_pct = (excluded_count / suspected_total * 100) if suspected_total > 0 else 0

    return {
        "suspected": {"count": suspected_total, "pct": 100},
        "confirmed": {"count": confirmed_count, "pct": confirmed_pct},
        "excluded": {"count": excluded_count, "pct": excluded_pct},
    }


@st.cache_data
def get_outcome_summary(filtered_df):
    confirmed_df = filtered_df[filtered_df["Classification"] == "Confirmed"]

    recovered_count = (confirmed_df["Outcome (Alive, Recovered, Died)"] == "Recovered").sum()
    died_count = (confirmed_df["Outcome (Alive, Recovered, Died)"] == "Died").sum()
    alive_count = (confirmed_df["Outcome (Alive, Recovered, Died)"] == "Alive").sum()
    pending_count = confirmed_df["Outcome (Alive, Recovered, Died)"].isna().sum()

    return {
        "recovered": recovered_count,
        "died": died_count,
        "alive": alive_count,
        "pending": pending_count,
    }


@st.cache_data
def get_cfr_over_time(filtered_df, epi_calendar_df):
    df = filtered_df[filtered_df["Classification"] == "Confirmed"].copy()

    df = df.sort_values("Date of Symptom Onset")
    calendar_sorted = epi_calendar_df.sort_values("start_date")

    df = pd.merge_asof(
        df,
        calendar_sorted[["epi_year", "epi_week", "start_date", "end_date"]],
        left_on="Date of Symptom Onset",
        right_on="start_date",
        direction="backward",
    )
    within_range = df["Date of Symptom Onset"] <= df["end_date"]
    df.loc[~within_range, ["epi_year", "epi_week"]] = None
    df = df[df["epi_year"].notna()]

    weekly = df.groupby(["epi_year", "epi_week"]).apply(
        lambda g: pd.Series({
            "confirmed": len(g),
            "deaths": (g["Outcome (Alive, Recovered, Died)"] == "Died").sum(),
        })
    ).reset_index()

    weekly["cfr_percent"] = weekly.apply(
        lambda r: (r["deaths"] / r["confirmed"] * 100) if r["confirmed"] > 0 else 0,
        axis=1,
    )

    weekly = weekly.sort_values(["epi_year", "epi_week"])
    weekly["cumulative_confirmed"] = weekly["confirmed"].cumsum()
    weekly["cumulative_deaths"] = weekly["deaths"].cumsum()
    weekly["cumulative_cfr"] = (
        weekly["cumulative_deaths"] / weekly["cumulative_confirmed"] * 100
    )

    return weekly


@st.cache_data
def get_state_outcome_table(filtered_df):
    # "suspected" = universal set = every row for that state
    state_table = filtered_df.groupby("STATE").apply(
        lambda g: pd.Series({
            "suspected": len(g),
            "confirmed": (g["Classification"] == "Confirmed").sum(),
            "recovered": ((g["Classification"] == "Confirmed") & (g["Outcome (Alive, Recovered, Died)"] == "Recovered")).sum(),
            "deceased": ((g["Classification"] == "Confirmed") & (g["Outcome (Alive, Recovered, Died)"] == "Died")).sum(),
        })
    ).reset_index()

    state_table["cfr_percent"] = state_table.apply(
        lambda r: (r["deceased"] / r["confirmed"] * 100) if r["confirmed"] > 0 else 0,
        axis=1,
    )

    state_table = state_table.sort_values("confirmed", ascending=False)
    state_table = state_table.reset_index(drop=True)
    state_table.index = state_table.index + 1
    return state_table


def get_quality_summary(quality_report, total_rows):
    """
    Tiers each quality check based on what % of total rows it affects.
    total_rows should be the row count of the uploaded file BEFORE 
    cleaning/deduplication, so percentages reflect the real scale of each issue.
    """
    def get_tier(count):
        if total_rows == 0:
            return "unclassified"
        pct = (count / total_rows) * 100
        if pct == 0:
            return "optimal"
        elif pct <= 5:
            return "acceptable"
        elif pct <= 15:
            return "attention"
        else:
            return "critical"

    formatted_report = {}
    for check, value in quality_report.items():
        if isinstance(value, (int, float)):
            formatted_report[check] = {"value": value, "tier": get_tier(value)}
        else:
            formatted_report[check] = {"value": value, "tier": "n/a"}

    return formatted_report


@st.cache_data
def get_rt_estimate(filtered_df, window_size=7):
    df = filtered_df[filtered_df["Classification"] == "Confirmed"]

    daily_counts = df.groupby("Date of Symptom Onset").size()
    full_range = pd.date_range(daily_counts.index.min(), daily_counts.index.max(), freq="D")
    daily_series = daily_counts.reindex(full_range, fill_value=0)

    # Serial interval: mean=8.5, SD=5.0 (Madewell et al. 2023, Emerging Infectious Diseases)
    si_mean = 8.5
    si_sd = 5.0
    si_variance = si_sd ** 2
    si_scale = si_variance / si_mean
    si_shape = si_mean ** 2 / si_variance

    gt_distribution = epyestim.distributions.discretise_gamma(a=si_shape, scale=si_scale)

    posterior = epyestim.estimate_r.estimate_r(
        daily_series,
        gt_distribution=gt_distribution,
        a_prior=1,
        b_prior=5,
        window_size=window_size,
    )

    posterior["r_mean"] = posterior["a_posterior"] * posterior["b_posterior"]
    posterior["r_lower"] = gamma.ppf(0.025, a=posterior["a_posterior"], scale=posterior["b_posterior"])
    posterior["r_upper"] = gamma.ppf(0.975, a=posterior["a_posterior"], scale=posterior["b_posterior"])

    return posterior


@st.cache_data
def get_case_concentration(filtered_df, population_df):
    """
    Simplified relative-risk screening tool, NOT a formal Kulldorff
    scan statistic. Flags states with more confirmed cases than their
    population share would predict. No statistical significance test
    is performed (no Monte Carlo simulation) — this is a screening
    indicator, not a validated cluster detection method.
    """
    confirmed_df = filtered_df[filtered_df["Classification"] == "Confirmed"]
    total_confirmed = len(confirmed_df)

    state_cases = (
        confirmed_df.groupby("STATE")
        .size()
        .reset_index(name="observed")
    )

    total_population = population_df["population_2022"].sum()

    merged = population_df.merge(state_cases, on="STATE", how="left")
    merged["observed"] = merged["observed"].fillna(0)

    merged["expected"] = (merged["population_2022"] / total_population) * total_confirmed

    merged["relative_risk"] = merged.apply(
        lambda r: (r["observed"] / r["expected"]) if r["expected"] > 0 else 0,
        axis=1,
    )

    merged = merged.sort_values("relative_risk", ascending=False)
    return merged


@st.cache_data
def get_lga_case_concentration(filtered_df, lga_population_df, state_filter=None):
    """
    Same relative-risk screening approach as get_case_concentration,
    but at LGA granularity. NOT a formal Kulldorff scan statistic —
    no significance testing, purely an observed/expected ratio.
    """
    confirmed_df = filtered_df[filtered_df["Classification"] == "Confirmed"]

    if state_filter is not None:
        confirmed_df = confirmed_df[confirmed_df["STATE"] == state_filter]
        lga_population_df = lga_population_df[lga_population_df["STATE"] == state_filter]

    total_confirmed = len(confirmed_df)

    lga_cases = (
        confirmed_df.groupby(["STATE", "LGA"])
        .size()
        .reset_index(name="observed")
    )

    total_population = lga_population_df["population_2022"].sum()

    merged = lga_population_df.merge(lga_cases, on=["STATE", "LGA"], how="left")
    merged["observed"] = merged["observed"].fillna(0)

    merged["expected"] = (merged["population_2022"] / total_population) * total_confirmed

    merged["relative_risk"] = merged.apply(
        lambda r: (r["observed"] / r["expected"]) if r["expected"] > 0 else 0,
        axis=1,
    )

    merged = merged.sort_values("relative_risk", ascending=False)

    return merged


@st.cache_data
def get_epidemic_threshold(filtered_df):
    """
    IDSR-style statistical threshold, matching NCDC's published approach for
    other diseases (e.g. Lassa fever) since no mpox-specific public threshold
    exists. Alert = mean + 1 SD of weekly confirmed case counts; 
    Epidemic/Response = mean + 2 SD. This is a generic method borrowed from
    NCDC's IDSR framework, not an official mpox-specific NCDC policy.
    """
    confirmed_df = filtered_df[filtered_df["Classification"] == "Confirmed"]

    weekly_counts = (
        confirmed_df.groupby("Epi Week (Onset Week)")
        .size()
        .sort_index()
    )

    if len(weekly_counts) < 3:
        return {
            "latest_count": int(weekly_counts.iloc[-1]) if len(weekly_counts) > 0 else 0,
            "mean": 0, "alert_threshold": 0, "epidemic_threshold": 0,
            "mode": "Watch", "insufficient_data": True,
        }

    mean = weekly_counts.mean()
    std = weekly_counts.std()
    alert_threshold = mean + std
    epidemic_threshold = mean + (2 * std)
    latest_count = weekly_counts.iloc[-1]

    if latest_count >= epidemic_threshold:
        mode = "Response"
    elif latest_count >= alert_threshold:
        mode = "Alert"
    else:
        mode = "Watch"

    return {
        "latest_count": int(latest_count),
        "mean": round(mean, 1),
        "alert_threshold": round(alert_threshold, 1),
        "epidemic_threshold": round(epidemic_threshold, 1),
        "mode": mode,
        "insufficient_data": False,
    }