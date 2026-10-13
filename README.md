# Mpox Surveillance Dashboard

A full-stack epidemiological surveillance dashboard built with Streamlit, modeled on Nigeria's mpox outbreak reporting patterns. Built as a technical project demonstrating data pipeline engineering, epidemiological modeling, geospatial visualization, and public health data communication.

**⚠️ This dashboard uses a synthetic line list.** It does not contain real patient data. The synthetic dataset is modeled on publicly available NCDC situation report statistics (case counts, sex distribution, geographic concentration, CFR trends) to reflect realistic reporting patterns — see [Data Sources](#data-sources--citations) below.

---

## What this demonstrates

- Incremental data pipeline design (validate → clean → deduplicate → merge on unique ID)
- Epidemiological modeling: effective reproduction number (Rt) estimation via the Cori et al. method
- Custom spatial risk-screening logic, clearly scoped against what it is and isn't
- Real geographic boundary data integration (choropleth mapping at state and LGA level)
- A from-scratch epi week calendar generator, matching Nigeria's actual reporting calendar
- Cross-page persistent filtering in a multi-page Streamlit application
- Honest documentation of every methodological shortcut, data limitation, and borrowed assumption

---

## Pages

| Page | What it shows |
|---|---|
| **Overview** | KPI cards, IDSR-style operational mode gauge, current Rt mini-card, national epi curve, geographic spread, sex distribution, executive insights, top states |
| **Epi Curve & Trends** | Stacked epi curve by classification, epi-year-over-year comparison |
| **Geographic** | Nigeria choropleth (state-level), confirmed-case dot overlay, drillable state/LGA ranking table |
| **Demographics & Classification** | Age/sex pyramid, classification breakdown, outlier tracking |
| **Outcomes** | National CFR, recovery/death tracking, cumulative outcomes over time, state-level outcome table |
| **Rt & Clustering** | Rt estimation with 95% confidence band, state and LGA case concentration screening |
| **Data Quality** | Cleaning pipeline summary, tiered quality checks, actionable recommendations per issue |

---

## Tech stack

Python · Streamlit (`st.navigation`/`st.Page` multi-page routing) · Pandas · Plotly (choropleth mapping, gauges) · Altair (age/sex pyramid) · `epyestim` (Rt estimation) · SciPy · PostgreSQL (via SQLAlchemy + `pg8000`) · Custom CSS theming

No authentication in the current build — see [Known Limitations](#known-limitations--future-work).

### Storage

Case data persists in PostgreSQL, not a flat file. Uploads are upserted into a single `cases` table, keyed on Epid Number (insert new, update existing on conflict). A column-mapping layer translates between the line list's original messy header names (e.g. `"Outcome (Alive, Recovered, Died)"`) and clean snake_case SQL columns (`outcome`), so the rest of the codebase keeps working against the original header names it was built around. Reads are cached (`@st.cache_data(ttl=60)`) and explicitly invalidated right after every upload, so new data appears immediately without waiting for the cache to expire.

The PostgreSQL driver is `pg8000` (pure Python), not `psycopg2` — chosen after `psycopg2`'s compiled DLL was blocked by Windows Application Control / Smart App Control during local development. `pg8000` has no compiled binary component and sidesteps that class of issue entirely.

Credentials live in a `.env` file (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`), loaded via `python-dotenv` and never committed — `.env` and the old Parquet artifact are both in `.gitignore`.

---

## Why Streamlit over a BI tool (Looker Studio, Power BI, Tableau)

BI tools are faster to build in and come with built-in enterprise auth and sharing. This project deliberately traded that for full control over the underlying logic:

- Every calculation (Rt, case concentration, epi week bucketing, incremental merge) is custom code that can be inspected, explained, and defended line by line — important for a public-health context where "how was this number calculated" needs a real answer, not "the BI tool did it."
- No licensing cost, no vendor lock-in.
- Statistical/epidemiological methods (Rt via a real, cited package; custom screening logic) aren't achievable inside a standard BI tool's built-in chart types.

The honest tradeoff: a BI tool is faster to build and hand off to someone else to maintain. This dashboard's logic requires Python literacy to extend.

---

## Data sources & citations

**Line list data:** Synthetic, generated to match the schema of a SORMAS-style laboratory line list. Adjusted to reflect real reported patterns:
- Sex distribution (~69% male among confirmed cases) — matches NCDC's reported outbreak sex skew
- Geographic concentration (cases concentrated in ~25 states, weighted toward Lagos, Rivers, FCT, Bayelsa, and other historically affected states) — matches NCDC situation report patterns, rather than an unrealistic uniform spread across all 37 states

**Serial interval (for Rt estimation):** Mean 8.5 days, SD 5.0 days — Madewell ZJ, Charniga K, Masters NB, et al. "Serial Interval and Incubation Period Estimates of Monkeypox Virus Infection in 12 Jurisdictions, United States, May–August 2022." *Emerging Infectious Diseases*, 2023;29(4). https://doi.org/10.3201/eid2904.221622

This estimate is derived from a 2022 US outbreak and may not fully reflect Nigerian transmission patterns. A 2025 study on Clade Ib transmission in the DRC found the serial interval varies meaningfully by transmission mode (shorter for sexual transmission, longer for non-sexual/household transmission) — a distinction the current dataset does not capture.

**Rt estimation method:** Cori et al. (2013) renewal-equation method, via the `epyestim` Python package — a direct implementation of the same method used by R's widely-adopted EpiEstim package.

**Nigeria state boundaries (GeoJSON):** geoBoundaries open database. One data-quality error in the source (Osun mislabeled as a duplicate Ogun polygon) was identified and corrected by cross-referencing each polygon's geographic centroid against the known location of each state's capital.

**Nigeria LGA boundaries (GeoJSON):** OSGOF/HDX Common Operational Dataset for Administrative Boundaries (COD-AB), accessed via the World Bank data catalog. 34 naming inconsistencies were reconciled against the population dataset (e.g. "Isiukwuato" vs "Isuikwuato"); the Bakassi Peninsula (ceded to Cameroon in 2008) was excluded as a non-current Nigerian LGA.

**Population data (state and LGA level):** 2022 NBS/NPC population projections, based on the 2006 national census. This is the most recent detailed figure publicly available — Nigeria has not conducted a full census since 2006. Nigerian census/population figures carry documented, longstanding disputes over accuracy in some regions, tied to federal revenue allocation. These figures should be treated as estimates, not precise counts.

**Epi week calendar:** Generated programmatically (Sunday on/before January 4th = week 1, matching CDC/MMWR convention), confirmed against NCDC's published 2026 epi week calendar at one verification point. Not independently obtained from NCDC as a full multi-year document — treat as a close approximation, not an official source.

---

## Methodology notes

### Rt (Effective Reproduction Number)
Standard Cori et al. sliding-window method (7-day window), applied to confirmed case counts by date of symptom onset. The serial interval is a borrowed assumption (see citation above), not derived from this dataset — this dashboard has no contact-tracing data, so it cannot independently estimate transmission timing.

### Case Concentration Screening (Rt & Clustering page)
**This is not a formal Kulldorff spatial scan statistic.** It is a simplified observed-vs-expected ratio:

```
expected_cases(area) = (area_population / total_population) × total_confirmed_cases
relative_risk(area)  = observed_cases(area) / expected_cases(area)
```

Computed at two levels, shown side by side:
- **State-level**: national choropleth, all 37 states + FCT, relative risk against the national population/case totals.
- **LGA-level**: national choropleth, all 773 LGAs, relative risk against the national population/case totals. LGA names are not unique across states (6 real collisions found: Bassa, Ifelodun, Irepodun, Nasarawa, Obi, Surulere), so map matching uses a combined `STATE | LGA` key, not LGA name alone.

States are flagged in a summary table when relative risk ≥ **1.5×** their population-predicted share — an arbitrary, clearly-labeled screening cutoff, not a statistically derived significance threshold.

No statistical significance testing is performed (no Monte Carlo simulation, no p-values). This is a screening indicator meant to flag areas worth further investigation, not a validated cluster-detection method.

A true Kulldorff analysis requires SaTScan (the authoritative implementation, built by Kulldorff himself) — a standalone program, not a Python library, that cannot run on free-tier hosting. Deploying this on infrastructure the developer controls (e.g. an organizational server) would allow proper SaTScan integration via Python's `subprocess` module.

### Operational Mode Gauge
Uses an IDSR-style statistical threshold (mean + 1 SD = Alert, mean + 2 SD = Response), matching the *method* NCDC publicly uses for other diseases (e.g. Lassa fever). No mpox-specific numeric threshold is publicly published by NCDC — this is a defensible generic method, not an official mpox-specific policy.

### Classification Logic
Suspected/Confirmed/Excluded are derived from lab test results (`Final Result Interpretation`), not a separate case-investigation classification field. "Suspected" is used in two senses across the dashboard: on the Overview KPI card it means "still awaiting a lab result" (a shrinking, live number); on the Demographics page's classification breakdown it means "total ever tested" (the base of a genuine funnel, since Confirmed is a subset of it). This distinction is documented here because it isn't obvious from the UI alone.

---

## Known limitations & future work

- **Hosting**: the current PostgreSQL instance runs locally. A public Streamlit Community Cloud deployment needs a reachable hosted Postgres instance (e.g. Supabase or Neon's free tiers) — the app code itself doesn't change, only the `.env` connection details.
- **Spatial clustering**: see methodology note above — SaTScan integration is the correct next step for a server-hosted deployment.
- **Real SORMAS/DHIS2 API integration**: the current upload flow accepts manual CSV uploads. Direct API integration with a live case-management system (SORMAS) is architecturally feasible but requires institutional authorization and a persistent backend — out of scope for a portfolio/demo build.
- **PII handling**: the pipeline strips Surname/Other Names columns if present in an uploaded file, since real SORMAS exports may include them. This dashboard has never processed real patient data.
- **Simulation/scenario modeling tool**: discussed as a natural extension (SEIR compartmental model, scenario comparison for outbreak preparedness training) but intentionally scoped as a separate tool, not a tab on this dashboard — mixing live surveillance data with hypothetical projections on one interface risks the two being confused.

---

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Upload a CSV matching the expected line list schema (see `preprocessing.py` for the full required column list) via the sidebar on the Overview page.

---

## Project structure

```
app.py                  # Router — st.navigation/st.Page setup only
config.py                # Paths, theme constants, epi constants
preprocessing.py         # Upload validation, cleaning, incremental merge
analytics.py              # All aggregation/calculation logic
utils.py                   # Shared cross-page sidebar filters
style.css                   # NCDC-inspired theme, dark mode
pages/
  1_Overview.py
  2_Epi_Curve_Trends.py
  3_Geographic.py
  4_Demographics_Classification.py
  5_Outcomes.py
  6_Rt_Clustering.py
  7_Data_Quality.py
data/
  merged_line_list.parquet         # Persistent case data store
  nigeria_states.geojson             # State boundaries
  nigeria_lga_boundaries.geojson      # LGA boundaries
  nigeria_state_centroids.csv          # State center points (map labels/dots)
  nigeria_state_population.csv          # 2022 NBS/NPC projections
  nigeria_lga_population.csv             # 2022 NBS/NPC projections
```
