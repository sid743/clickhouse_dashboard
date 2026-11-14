# Cortexa · AI Auditing and Analysis dashboard

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

## Access and uploads

There is no login: anyone who opens the app sees the dashboard. Uploading a new export needs the
admin password, which a pop-up asks for when you click **Upload to dashboard**.

The admin password is `Cortexa@Admin1`. Change it before sharing the app:

```
python auth.py
```

Type the new password twice, then paste the printed hash into `.streamlit\secrets.toml` as the
`password_hash` under `[users.admin]`. Any user there with `role = "admin"` can upload with their
password. The `viewer` entry is no longer used.

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

Four tabs:

| Tab | Shows |
|---|---|
| Executive overview | Cards: prompt events, allowed, blocked, execution failures, users. Charts: execution (% allowed vs blocked), intent, prompt activity trend (line), what the router sent prompts to |
| Security & policy | Cards: allowed, blocked, high-risk labels. Charts: risk level, policy category (allowed vs blocked), top 10 users by high-risk prompts |
| Usage intelligence | SLM and LLM cards (calls, latency, input and output tokens), tokens by pipeline step for each, pipeline errors |
| Prompt explorer | The selected prompt at the top (decision, risk, policy, intent, outcome, gate explanation, router flags, response), then every prompt in a table with Excel-style column filters (application, decision, risk, category, policy, intent, outcome, entrypoint), a search box and CSV download. Click a row to show it at the top |

SLM vs LLM: `MODEL_TIER` at the top of `cortexa_data.py` says which model is which
(nova-lite = SLM, gpt-oss-120b = LLM). Add new models there. A model that isn't listed counts as LLM
when it writes the answer (`llm_caller` step) and SLM otherwise.

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
