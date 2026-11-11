# Cortexa · AI Auditing & Security dashboard

A one-page Streamlit dashboard over Cortexa's ClickHouse telemetry. It answers
"How is our AI being used, and is it safe?"

## Run it (Windows, Command Prompt)

```
cd C:\Users\Sid\Claude\Projects\clickhouse_dashboard
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. Next time you only need the `activate` and `streamlit run` lines.

## Logins

| User | Password | Can do |
|---|---|---|
| `admin` | `Cortexa@Admin1` | View the dashboard, upload ClickHouse exports |
| `viewer` | `Cortexa@View1` | View the dashboard |

Change these before sharing the app. To set a new password:

```
python auth.py
```

Type the password twice, then paste the printed hash into `.streamlit\secrets.toml` as that user's
`password_hash`. To add a user, copy one of the `[users.xxx]` blocks, rename it and set `role` to
`admin` or `viewer`.

This login is fine for a demo or an internal tool. It keeps no audit of sign-ins, has no lockout,
and a browser refresh signs you out. For production, put the app behind the company's SSO.

## Data

The left sidebar holds the data and filters:

- **Data origin**: two buttons switch between the real-data and synthetic-data dashboards.
- **Application**: one app or all. ClickHouse stores only app IDs, so the app shows as `App a1db2bf3` until
  you give it a name in `data\app_names.csv` (columns `app_id,app_name`).
- **Policy decision**: all decisions, allowed only, or blocked only.
- **Date range** (UTC).

The filters apply to every section, including the LLM usage figures and the CSV download.

**Real data**: every Excel export an admin has uploaded, combined. Rows that appear in more than one
upload are counted once. Files live in `data\real\uploads\`. Your first export is already loaded (`initial_clickhouse_export.xlsx`).

**Synthetic data**: `data\synthetic\clickhouse_export_synthetic.xlsx`: 201 fictional prompts over
four weeks, 24 users, with prompt-injection, credential, personal-data and exfiltration attempts,
some repeated probing, and pipeline failures, spread over three fictional applications (Pharma
regulatory assistant, Quality docs copilot, HR policy assistant). The page shows a yellow banner
whenever it is in use. Recreate it with `python generate_synthetic.py`. Policy codes S07, S15, S16
and S17, the intents Analyze, Search and Action, error code LLM001 and the three app IDs are made up
for the demo.

### Uploading an export (admin)

Use the sidebar. The file must be `.xlsx` with the sheets `graph_state_events` and `llm_calls`
(other sheets are ignored). Before saving, the app shows how many prompts are new. Then choose:

- **Adding to current real data**: keeps earlier uploads.
- **Replacing current real data**: moves earlier uploads to `data\real\archive\`.

## What's on the page

One scrolling page with four sections. The links under the title jump to each one.

| Section | Shows | Form |
|---|---|---|
| Executive overview | Prompts, blocked, high-risk, failed runs, users; prompt activity per day (per week past ~2 months), allowed vs blocked; intents | Stat tiles, stacked columns, ranked bars |
| Security & policy | Prompts by risk level and by policy category; users with the most blocks; prompts to review | Bars + table |
| Usage intelligence | Capabilities the router asked for; pipeline errors; LLM calls, tokens and latency; tokens by pipeline step; per-model table | Bars, tables, stat tiles |
| Prompt explorer | Every prompt, searchable, with CSV download. Click a row to see its decision, risk, policy, intent, outcome, gate explanation, router flags and response | Table + detail panel |

Colours stay the same on every chart: blue = allowed, orange = blocked. Risk uses red, amber and
green, always with its text label.

## How the numbers are worked out

- One prompt = one `event_id`. The prompt text comes from the `prepare` step.
- Decision, category, risk and policy come from the `decision_gate` message
  (`Category: …, Risk: …, Policy: …`).
- Cortexa records blocked prompts with status `failed`. The dashboard counts those as **Blocked**.
  **Failed runs** counts only allowed prompts whose run then failed.
- Errors are counted at the step that raised them (for example Collector `COL001`), not again in
  the `orchestrator_output` summary.
- All times are UTC, as stored in ClickHouse.

## Files

```
app.py                  the dashboard
cortexa_data.py         reads and checks exports, builds the per-prompt table
auth.py                 login check + password-hash helper
generate_synthetic.py   builds the synthetic workbook
.streamlit\config.toml  white theme
.streamlit\secrets.toml users and password hashes (keep out of git)
data\app_names.csv      optional readable names for app IDs
data\real\uploads\      uploaded real exports
data\synthetic\         synthetic export
```
