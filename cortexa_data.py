"""
Read Cortexa ClickHouse exports (.xlsx) and turn them into tables the dashboard uses.

An export must contain two sheets:
  graph_state_events - one row per pipeline step (prepare, decision_gate, router, ...)
  llm_calls          - one row per LLM call with tokens and latency
Other sheets (monthly_token_usage, README, ...) are ignored.
"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent / "data"
REAL_DIR = BASE / "real" / "uploads"
REAL_ARCHIVE = BASE / "real" / "archive"
SYNTHETIC_FILE = BASE / "synthetic" / "clickhouse_export_synthetic.xlsx"
APP_NAMES_FILE = BASE / "app_names.csv"   # optional: app_id,app_name

# Which models the dashboard calls SLM (small language model) and LLM. Add new models here.
# A model not listed counts as LLM if it answers the user (llm_caller step), otherwise SLM.
MODEL_TIER = {
    "amazon.nova-lite-v1:0": "SLM",
    "openai.gpt-oss-120b-1:0": "LLM",
}


def model_tier(llm_name, submodule):
    return MODEL_TIER.get(str(llm_name), "LLM" if submodule == "llm_caller" else "SLM")

REQUIRED = {
    "graph_state_events": ["event_id", "submodule", "submodule_delta", "event_timestamp",
                           "submodule_execution_status"],
    "llm_calls": ["event_id", "submodule", "event_timestamp", "llm_name",
                  "input_tokens", "output_tokens", "duration_ms"],
}

GATE_RE = re.compile(r"Category:\s*(?P<category>[^,]+),\s*Risk:\s*(?P<risk>[^,]+),\s*Policy:\s*(?P<policy>[^.]+)\.?\s*(?P<reason>.*)",
                     re.S)
ROUTE_FLAGS = {"requires_rag": "Knowledge base (RAG)", "requires_online_search": "Online search",
               "requires_tool": "Tool call", "requires_reasoning": "Reasoning"}


# --------------------------------------------------------------------------- reading files

def read_export(source):
    """Read one export (path or uploaded file). Returns (graph, calls) or raises ValueError."""
    try:
        sheets = pd.read_excel(source, sheet_name=None)
    except Exception as exc:  # not an Excel file, corrupt, password protected...
        raise ValueError(f"Could not open the file as Excel: {exc}") from exc
    problems = []
    for sheet, cols in REQUIRED.items():
        if sheet not in sheets:
            problems.append(f"missing sheet '{sheet}'")
            continue
        missing = [c for c in cols if c not in sheets[sheet].columns]
        if missing:
            problems.append(f"sheet '{sheet}' is missing columns: {', '.join(missing)}")
    if problems:
        raise ValueError("This does not look like a Cortexa ClickHouse export - " + "; ".join(problems))
    return _clean(sheets["graph_state_events"], sheets["llm_calls"])


def _clean(graph, calls):
    graph = graph.copy()
    calls = calls.copy()
    for df in (graph, calls):
        df["event_timestamp"] = pd.to_datetime(df["event_timestamp"], errors="coerce")
        df["event_id"] = df["event_id"].astype(str)
        for col in ("user_id", "session_id", "entrypoint", "error_message", "app_id"):
            if col not in df.columns:
                df[col] = None
    for col in ("input_tokens", "output_tokens", "duration_ms"):
        calls[col] = pd.to_numeric(calls[col], errors="coerce").fillna(0)
    graph["submodule_execution_status"] = pd.to_numeric(graph["submodule_execution_status"], errors="coerce")
    return graph, calls


def combine(exports):
    """Stack several exports and drop rows that appear in more than one."""
    if not exports:
        return _clean(pd.DataFrame(columns=REQUIRED["graph_state_events"]),
                      pd.DataFrame(columns=REQUIRED["llm_calls"]))
    graph = pd.concat([g for g, _ in exports], ignore_index=True)
    calls = pd.concat([c for _, c in exports], ignore_index=True)
    graph = graph.drop_duplicates(subset=["event_id", "submodule", "event_timestamp"])
    call_key = ["id"] if "id" in calls.columns else ["event_id", "submodule", "event_timestamp"]
    calls = calls.drop_duplicates(subset=call_key)
    return graph, calls


def real_files():
    REAL_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(REAL_DIR.glob("*.xlsx"))


def save_upload(uploaded_file, replace):
    """Store an admin upload. replace=True moves the current files to data/real/archive/."""
    REAL_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if replace:
        archive = REAL_ARCHIVE / stamp
        archive.mkdir(parents=True, exist_ok=True)
        for f in real_files():
            shutil.move(str(f), archive / f.name)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(uploaded_file.name).name)
    target = REAL_DIR / f"{stamp}_{safe_name}"
    target.write_bytes(uploaded_file.getvalue())
    return target


def app_names():
    """ClickHouse stores only app IDs. data/app_names.csv (app_id,app_name) gives them readable names."""
    try:
        df = pd.read_csv(APP_NAMES_FILE, dtype=str).dropna()
        return dict(zip(df["app_id"].str.strip(), df["app_name"].str.strip()))
    except (FileNotFoundError, KeyError, ValueError):
        return {}


def app_label(app_id, names):
    if app_id is None or (isinstance(app_id, float) and pd.isna(app_id)):
        return "Not recorded"
    return names.get(str(app_id), f"App {str(app_id)[:8]}")


# --------------------------------------------------------------------------- prompt-level table

def _json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {}


def build_prompts(graph):
    """One row per prompt (event_id) with decision, risk, intent, routing and outcome."""
    if graph.empty:
        return pd.DataFrame()
    graph = graph.sort_values("event_timestamp")
    rows = {}
    for r in graph.itertuples(index=False):
        p = rows.setdefault(r.event_id, {
            "event_id": r.event_id, "time": r.event_timestamp, "app_id": r.app_id, "user_id": r.user_id,
            "session_id": r.session_id, "entrypoint": r.entrypoint, "prompt": None,
            "decision": None, "category": None, "risk": None, "policy": None, "gate_reason": None,
            "intent": None, "routes": None, "status": None, "response": None, "errors": [],
            "summary_errors": [],
        })
        delta = _json(r.submodule_delta)
        step = r.submodule
        if step == "prepare":
            p["prompt"] = delta.get("query")
            p["time"] = r.event_timestamp
        elif step == "decision_gate":
            out = delta.get("decision_gate_output", {})
            p["decision"] = (out.get("decision") or "").lower() or None
            m = GATE_RE.match(out.get("message") or "")
            if m:
                p.update(category=m["category"].strip(), risk=m["risk"].strip().title(),
                         policy=m["policy"].strip(), gate_reason=m["reason"].strip())
            else:
                p["gate_reason"] = out.get("message")
        elif step == "intent_classifier":
            intents = delta.get("intent_classifier_output", {}).get("matched_intents") or []
            p["intent"] = ", ".join(intents) if intents else None
        elif step == "router":
            out = delta.get("router_output", {})
            p["routes"] = [label for key, label in ROUTE_FLAGS.items() if out.get(key)]
        elif step in ("finalize", "orchestrator_output"):
            p["status"] = delta.get("status") or p["status"]
            p["response"] = delta.get("response") or p["response"]
        # errors: count them at the step that raised them; orchestrator_output repeats them as a
        # summary, so it is only used when no step-level errors were recorded for the prompt
        target = "summary_errors" if step == "orchestrator_output" else "errors"
        for e in delta.get("error_messages", []) or []:
            p[target].append((e.get("module"), e.get("error_code"), e.get("message"), r.event_timestamp))

    for p in rows.values():
        if not p["errors"]:
            p["errors"] = p["summary_errors"]
        del p["summary_errors"]

    df = pd.DataFrame(rows.values())
    df["outcome"] = "Completed"
    df.loc[df["status"] == "failed", "outcome"] = "Failed"
    df.loc[df["decision"] == "blocked", "outcome"] = "Blocked"
    df.loc[df["status"].isna() & df["decision"].ne("blocked"), "outcome"] = "In progress / unknown"
    df["decision"] = df["decision"].fillna("unknown").str.title()
    df["risk"] = df["risk"].fillna("Not given")
    df["category_policy"] = df.apply(
        lambda x: f"{x['category']} ({x['policy']})" if x["category"] else "Not given", axis=1)
    df["error_codes"] = df["errors"].map(lambda es: ", ".join(sorted({c for _, c, _, _ in es if c})))
    df["date"] = df["time"].dt.normalize()
    return df.sort_values("time", ascending=False).reset_index(drop=True)


def error_table(prompts):
    rows = [dict(module=m, code=c, message=msg, time=t)
            for es in prompts["errors"] for (m, c, msg, t) in es]
    if not rows:
        return pd.DataFrame(columns=["Module", "Error code", "Message", "Occurrences", "Last seen (UTC)"])
    e = pd.DataFrame(rows)
    e["message"] = e["message"].astype(str).str.split("\n").str[0].str.slice(0, 160)
    out = (e.groupby(["module", "code"])
           .agg(message=("message", "first"), count=("time", "size"), last=("time", "max"))
           .reset_index().sort_values("count", ascending=False))
    out.columns = ["Module", "Error code", "Message", "Occurrences", "Last seen (UTC)"]
    return out
