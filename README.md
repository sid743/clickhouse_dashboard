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

Two buttons at the top switch between the two dashboards.

**Real data**: every Excel export an admin has uploaded, combined. Rows that appear in more than one
upload are counted once. Files live in `data\real\uploads\`. Your first export is already loaded (`initial_clickhouse_export.xlsx`).

**Synthetic data**: `data\synthetic\clickhouse_export_synthetic.xlsx`: 201 fictional prompts over
four weeks, 24 users, with prompt-injection, credential, personal-data and exfiltration attempts,
some repeated probing, and pipeline failures. The page shows a yellow banner whenever it is in use.
Recreate it with `python generate_synthetic.py`. Policy codes S07, S15, S16 and S17, the intents
Analyze, Search and Action, and error code LLM001 are made up for the demo.

### Uploading an export (admin)

Use the sidebar. The file must be `.xlsx` with the sheets `graph_state_events` and `llm_calls`
(other sheets are ignored). Before saving, the app shows how many prompts are new. Then choose:

- **Adding to current real data**: keeps earlier uploads.
- **Replacing current real data**: moves earlier uploads to `data\real\archive\`.

## What's on the page

| Section | Shows | Form |
|---|---|---|
| KPI row | Prompts, blocked, high-risk, failed runs, users | Stat tiles |
| Activity | Prompts per day (per week past ~2 months), allowed vs blocked | Stacked columns |
| Is it safe? | Prompts by risk level and by policy category; users with the most blocks; prompts to review | Bars + table |
| How is it being used? | Intents, and the capabilities the router asked for | Ranked bars |
| Is it working? | Pipeline errors by module and code | Table |
| LLM usage | Calls, tokens and latency; tokens by pipeline step; per-model table | Stat tiles + bars + table |
| Audit trail | Every prompt, searchable, with CSV download | Table |

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
data\real\uploads\      uploaded real exports
data\synthetic\         synthetic export
```
