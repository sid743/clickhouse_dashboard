"""
Cortexa - AI Auditing & Security dashboard
"How is our AI being used, and is it safe?"

Run:  streamlit run app.py
"""

import altair as alt
import pandas as pd
import streamlit as st

import auth
import cortexa_data as cd

st.set_page_config(page_title="Cortexa · AI Auditing & Security", layout="wide")

# --------------------------------------------------------------------------- colours & style
# Allowed / blocked are the two series used across the page (validated pair, white surface).
BLUE, ORANGE, VIOLET, GRAY = "#2a78d6", "#eb6834", "#6250d6", "#b5b3ab"
DECISION_DOMAIN, DECISION_RANGE = ["Allowed", "Blocked", "Unknown"], [BLUE, ORANGE, GRAY]
# Risk is a severity, so it uses status colours (always shown with its text label).
RISK_DOMAIN = ["High", "Medium", "Low", "Not given"]
RISK_RANGE = ["#d03b3b", "#fab219", "#0ca30c", GRAY]
STEP_NAMES = {"decision_gate": "Decision gate", "intent_classifier": "Intent classifier", "router": "Router",
              "llm_caller": "LLM caller"}
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

st.markdown(f"""
<style>
  .block-container {{ padding-top: 2rem; max-width: 1400px; }}
  h1, h2, h3 {{ font-family: {FONT}; letter-spacing: -0.01em; }}
  .tile {{ border: 1px solid rgba(11,11,11,0.10); border-radius: 10px; padding: 14px 16px; background: #fff; height: 100%; }}
  .tile-label {{ color: {INK2}; font-size: 0.85rem; }}
  .tile-value {{ color: {INK}; font-size: 1.9rem; font-weight: 600; line-height: 1.2; margin-top: 2px; }}
  .tile-note {{ color: {MUTED}; font-size: 0.8rem; margin-top: 2px; }}
  .synthetic {{ border-left: 4px solid #fab219; background: #fffaf0; padding: 10px 14px; border-radius: 6px;
               color: {INK}; font-size: 0.9rem; margin: 4px 0 8px 0; }}
  .section-q {{ color: {INK2}; margin-top: -0.6rem; margin-bottom: 0.6rem; font-size: 0.92rem; }}
</style>
""", unsafe_allow_html=True)


def tile(col, label, value, note=""):
    col.markdown(f'<div class="tile"><div class="tile-label">{label}</div>'
                 f'<div class="tile-value">{value}</div><div class="tile-note">{note}</div></div>',
                 unsafe_allow_html=True)


def section(title, question):
    st.markdown("")
    st.subheader(title)
    st.markdown(f'<div class="section-q">{question}</div>', unsafe_allow_html=True)


def styled(chart, height):
    return (chart.properties(height=height, background="#ffffff")
            .configure(font=FONT)
            .configure_view(stroke=None)
            .configure_axis(labelColor=INK2, titleColor=INK2, labelFontSize=12, titleFontSize=12,
                            titleFontWeight="normal", gridColor=GRID, domainColor=AXIS, tickColor=AXIS)
            .configure_legend(orient="top", title=None, labelColor=INK2, labelFontSize=12,
                              symbolType="square", symbolSize=120))


def show(chart, height):
    st.altair_chart(styled(chart, height), width="stretch", theme=None)


def hbar(df, cat, val, color, x_title, order=None, fmt=",.0f", axis_fmt="d", tooltip=None):
    """Ranked horizontal bars, one hue, value at the bar tip."""
    order = order or df.sort_values(val, ascending=False)[cat].tolist()
    axis = alt.Axis(format=axis_fmt, tickMinStep=1) if axis_fmt == "d" else alt.Axis(format=axis_fmt, tickCount=5)
    base = alt.Chart(df).encode(
        y=alt.Y(f"{cat}:N", sort=order, title=None, axis=alt.Axis(labelLimit=280, ticks=False)),
        x=alt.X(f"{val}:Q", title=x_title, axis=axis),
        tooltip=tooltip or [alt.Tooltip(f"{cat}:N"), alt.Tooltip(f"{val}:Q", format=fmt)],
    )
    color_enc = color if isinstance(color, alt.Color) else alt.value(color)
    bars = base.mark_bar(size=18, cornerRadiusEnd=4).encode(color=color_enc)
    labels = base.mark_text(align="left", dx=5, color=INK2, fontSize=12).encode(text=alt.Text(f"{val}:Q", format=fmt))
    return bars + labels, max(len(order) * 34 + 50, 120)


def fmt_int(n):
    return f"{int(n):,}"


def short_model(names):
    """amazon.nova-lite-v1:0 -> nova-lite-v1"""
    return names.astype(str).str.split(":").str[0].str.replace(r"^(amazon|openai|anthropic|meta)\.", "", regex=True)


# --------------------------------------------------------------------------- login

def load_users():
    try:
        return {name: dict(cfg) for name, cfg in st.secrets["users"].items()}
    except Exception:
        return {}


def login_screen():
    users = load_users()
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.markdown("")
        st.markdown("### Cortexa · AI Auditing & Security")
        st.caption("Sign in to view the dashboard.")
        if not users:
            st.error("No users are configured. Add them to .streamlit/secrets.toml (see README).")
            return
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
        if submitted:
            role = auth.authenticate(users, username, password)
            if role:
                st.session_state.update(user=username.strip(), role=role)
                st.rerun()
            st.error("Wrong username or password.")


if "role" not in st.session_state:
    login_screen()
    st.stop()

IS_ADMIN = st.session_state.role == "admin"
st.session_state.setdefault("dataset", "real")
st.session_state.setdefault("upload_key", 0)


# --------------------------------------------------------------------------- data

@st.cache_data(show_spinner="Reading exports...")
def load(files):
    """files: tuple of (path, modified time) so the cache refreshes when files change."""
    exports = [cd.read_export(path) for path, _ in files]
    graph, calls = cd.combine(exports)
    return cd.build_prompts(graph), calls


def file_key(paths):
    return tuple((str(p), p.stat().st_mtime) for p in paths)


def load_dataset(name):
    if name == "synthetic":
        if not cd.SYNTHETIC_FILE.exists():
            return None, None, "The synthetic file is missing. Run: python generate_synthetic.py"
        return (*load(file_key([cd.SYNTHETIC_FILE])), None)
    files = cd.real_files()
    if not files:
        msg = "No real export has been uploaded yet." + (" Use the upload panel in the sidebar." if IS_ADMIN else
                                                          " Ask an admin to upload one.")
        return None, None, msg
    return (*load(file_key(files)), None)


# --------------------------------------------------------------------------- sidebar

with st.sidebar:
    st.markdown(f"Signed in as **{st.session_state.user}**  \n{'Admin' if IS_ADMIN else 'Viewer'}")
    if st.button("Sign out", width="stretch"):
        for k in ("user", "role"):
            st.session_state.pop(k, None)
        st.rerun()

    if IS_ADMIN:
        st.divider()
        st.markdown("**Upload a ClickHouse export**")
        st.caption("Excel file with the sheets graph_state_events and llm_calls. Goes into the real-data dashboard.")
        if msg := st.session_state.pop("upload_msg", None):
            st.success(msg)
        up = st.file_uploader("Export (.xlsx)", type=["xlsx"], key=f"up_{st.session_state.upload_key}",
                              label_visibility="collapsed")
        if up is not None:
            try:
                g_new, _ = cd.read_export(up)
                p_new = cd.build_prompts(g_new)
                current, _, _ = load_dataset("real")
                known = set(current["event_id"]) if current is not None else set()
                n_new = int((~p_new["event_id"].isin(known)).sum()) if len(p_new) else 0
                if len(p_new):
                    st.info(f"{len(p_new)} prompts from {p_new['time'].min():%d %b %Y} to "
                            f"{p_new['time'].max():%d %b %Y}: {n_new} new, "
                            f"{len(p_new) - n_new} already in the dashboard.")
                else:
                    st.warning("The file has the right sheets but no prompts.")
                mode = st.radio("Load it by", ["Adding to current real data", "Replacing current real data"],
                                help="Adding keeps earlier uploads and skips duplicate rows. "
                                     "Replacing moves earlier uploads to data/real/archive.")
                if st.button("Save to dashboard", type="primary", width="stretch", disabled=not len(p_new)):
                    saved = cd.save_upload(up, replace=mode.startswith("Replacing"))
                    st.session_state.upload_msg = f"Saved {saved.name}."
                    st.session_state.upload_key += 1
                    st.session_state.dataset = "real"
                    st.rerun()
            except ValueError as exc:
                st.error(str(exc))

        files = cd.real_files()
        with st.expander(f"Real-data files ({len(files)})"):
            for f in files:
                st.caption(f.name)
            if not files:
                st.caption("None yet.")


# --------------------------------------------------------------------------- header & dataset switch

st.title("AI Auditing & Security")
st.markdown(f'<div class="section-q">How is our AI being used, and is it safe? · Cortexa ClickHouse telemetry</div>',
            unsafe_allow_html=True)

b1, b2, _ = st.columns([1.5, 1.7, 3.6])
if b1.button("View real data dashboard", type="primary" if st.session_state.dataset == "real" else "secondary",
             width="stretch"):
    st.session_state.dataset = "real"
    st.rerun()
if b2.button("View synthetic data dashboard",
             type="primary" if st.session_state.dataset == "synthetic" else "secondary", width="stretch"):
    st.session_state.dataset = "synthetic"
    st.rerun()

DATASET = st.session_state.dataset
prompts_all, calls_all, problem = load_dataset(DATASET)
if DATASET == "synthetic":
    st.markdown('<div class="synthetic"><b>Synthetic demo data.</b> Every prompt, user and attack below is fictional, '
                'generated to show what the dashboard looks like with more activity. It is not real Cortexa traffic.</div>',
                unsafe_allow_html=True)
if problem:
    st.info(problem)
    st.stop()
if prompts_all.empty:
    st.info("The loaded export contains no prompts.")
    st.stop()

# Filter row - one control, scopes everything below
first, last = prompts_all["time"].min().date(), prompts_all["time"].max().date()
f1, f2 = st.columns([1.6, 4.4], vertical_alignment="bottom")
picked = f1.date_input("Date range (UTC)", value=(first, last), min_value=first, max_value=last,
                       format="DD/MM/YYYY", key=f"dates_{DATASET}_{first}_{last}")
start, end = (picked if isinstance(picked, (list, tuple)) and len(picked) == 2 else (first, last))
in_range = lambda s: (s >= pd.Timestamp(start)) & (s < pd.Timestamp(end) + pd.Timedelta(days=1))
P = prompts_all[in_range(prompts_all["time"])]
C = calls_all[in_range(calls_all["event_timestamp"])]
f2.caption(f"{len(P):,} prompts between {start:%d %b %Y} and {end:%d %b %Y}. All times are UTC as stored in ClickHouse.")

if P.empty:
    st.info("No prompts in this date range.")
    st.stop()

has_users = P["user_id"].notna().any()
n = len(P)
blocked = int((P["decision"] == "Blocked").sum())
high = P[P["risk"] == "High"]
high_allowed = int((high["decision"] == "Allowed").sum())
allowed = P[P["decision"] == "Allowed"]
failed = int((P["outcome"] == "Failed").sum())
# Colour follows the decision everywhere on the page; "Unknown" only appears if the data has it
present = [d for d in DECISION_DOMAIN if d in set(P["decision"])]
DECISION_SCALE = alt.Scale(domain=present, range=[DECISION_RANGE[DECISION_DOMAIN.index(d)] for d in present])

# --------------------------------------------------------------------------- KPI row
k = st.columns(5)
tile(k[0], "Prompts", fmt_int(n), f"{P['date'].nunique()} active days")
tile(k[1], "Blocked by policy", fmt_int(blocked), f"{blocked / n:.0%} of prompts")
tile(k[2], "High-risk prompts", fmt_int(len(high)),
     "all blocked" if len(high) and not high_allowed else f"{high_allowed} allowed" if len(high) else "none")
tile(k[3], "Failed runs", fmt_int(failed), f"{failed / max(len(allowed), 1):.0%} of allowed prompts")
tile(k[4], "Users", fmt_int(P["user_id"].nunique()) if has_users else "–",
     f"{P['session_id'].nunique()} sessions" if has_users else "user_id not recorded")

# --------------------------------------------------------------------------- activity
section("Activity", "How much is the AI being used, and how much of it is blocked?")
span_days = (P["date"].max() - P["date"].min()).days
period = "week" if span_days > 62 else "day"
to_period = (lambda s: s.dt.to_period("W").dt.start_time) if period == "week" else (lambda s: s.dt.normalize())
act = P.assign(period=to_period(P["time"])).groupby(["period", "decision"]).size().reset_index(name="prompts")
# every day/week in the range gets a slot, so quiet days show as gaps rather than disappearing
slots = pd.date_range(to_period(pd.Series([pd.Timestamp(start)]))[0], pd.Timestamp(end),
                      freq="W-MON" if period == "week" else "D")
act = act.pivot(index="period", columns="decision", values="prompts").reindex(slots, fill_value=0).fillna(0)
act = act.rename_axis("period").reset_index().melt("period", var_name="decision", value_name="prompts")
act["label"] = act["period"].dt.strftime("%d %b")
act["stack"] = act["decision"].map({"Allowed": 0, "Blocked": 1}).fillna(2)
bar_px = int(max(4, min(24, 0.6 * 1100 / len(slots))))  # thin columns, capped at 24px
activity = alt.Chart(act).mark_bar(size=bar_px, stroke="#ffffff", strokeWidth=1).encode(
    x=alt.X("label:O", title=None, sort=act["label"].unique().tolist(),
            axis=alt.Axis(labelAngle=0, ticks=False, labelOverlap="greedy", labelSeparation=8)),
    y=alt.Y("sum(prompts):Q", title=f"Prompts per {period}", axis=alt.Axis(tickMinStep=1)),
    color=alt.Color("decision:N", scale=DECISION_SCALE),
    order=alt.Order("stack:Q"),
    tooltip=[alt.Tooltip("label:O", title="Week of" if period == "week" else "Day"),
             alt.Tooltip("decision:N", title="Decision"), alt.Tooltip("sum(prompts):Q", title="Prompts")],
)
show(activity, 240)

# --------------------------------------------------------------------------- safety
section("Is it safe?", "Risk and policy labels come from Cortexa's decision gate, which checks every prompt "
                       "before it reaches a model.")
c1, c2 = st.columns(2, gap="large")
with c1:
    st.markdown("**Prompts by risk level**")
    risk = (P.groupby("risk").agg(prompts=("event_id", "size"),
                                  allowed=("decision", lambda s: (s == "Allowed").sum()),
                                  blocked=("decision", lambda s: (s == "Blocked").sum()))
            .reindex(RISK_DOMAIN[:3] + (["Not given"] if (P["risk"] == "Not given").any() else []), fill_value=0)
            .reset_index())
    chart, h = hbar(risk, "risk", "prompts",
                    alt.Color("risk:N", scale=alt.Scale(domain=RISK_DOMAIN, range=RISK_RANGE), legend=None),
                    "Prompts", order=risk["risk"].tolist(),
                    tooltip=[alt.Tooltip("risk:N", title="Risk"), alt.Tooltip("prompts:Q", title="Prompts"),
                             alt.Tooltip("allowed:Q", title="Allowed"), alt.Tooltip("blocked:Q", title="Blocked")])
    show(chart, h)
with c2:
    st.markdown("**Prompts by policy category**")
    pol = P.groupby(["category_policy", "decision"]).size().reset_index(name="prompts")
    totals = pol.groupby("category_policy")["prompts"].sum().sort_values(ascending=False)
    pol["stack"] = pol["decision"].map({"Allowed": 0, "Blocked": 1}).fillna(2)
    order = totals.index.tolist()
    bars = alt.Chart(pol).mark_bar(size=18, stroke="#ffffff", strokeWidth=1).encode(
        y=alt.Y("category_policy:N", sort=order, title=None, axis=alt.Axis(labelLimit=280, ticks=False)),
        x=alt.X("sum(prompts):Q", title="Prompts", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("decision:N", scale=DECISION_SCALE),
        order=alt.Order("stack:Q"),
        tooltip=[alt.Tooltip("category_policy:N", title="Category (policy)"),
                 alt.Tooltip("decision:N", title="Decision"), alt.Tooltip("sum(prompts):Q", title="Prompts")],
    )
    labels = alt.Chart(totals.reset_index()).mark_text(align="left", dx=5, color=INK2, fontSize=12).encode(
        y=alt.Y("category_policy:N", sort=order), x="prompts:Q", text="prompts:Q")
    show(bars + labels, max(len(order) * 34 + 70, 140))

if has_users:
    st.markdown("**Users with the most blocked prompts**")
    users = (P.groupby("user_id").agg(blocked=("decision", lambda s: int((s == "Blocked").sum())),
                                      prompts=("event_id", "size"), sessions=("session_id", "nunique"))
             .reset_index())
    users = users[users["blocked"] > 0].sort_values(["blocked", "prompts"], ascending=False).head(10)
    if users.empty:
        st.caption("No user had a prompt blocked in this period.")
    else:
        chart, h = hbar(users, "user_id", "blocked", ORANGE, "Blocked prompts",
                        tooltip=[alt.Tooltip("user_id:N", title="User"), alt.Tooltip("blocked:Q", title="Blocked"),
                                 alt.Tooltip("prompts:Q", title="All prompts"),
                                 alt.Tooltip("sessions:Q", title="Sessions")])
        cu, _ = st.columns([1, 1])
        with cu:
            show(chart, h)
        st.caption("Several blocks from one user, especially in one session, can point to deliberate probing.")
else:
    st.caption("Per-user activity can't be shown: user_id and session_id are empty in this export.")

st.markdown("**Prompts to review** · blocked, or rated medium/high risk")
review = P[(P["decision"] == "Blocked") | P["risk"].isin(["High", "Medium"])]
if review.empty:
    st.caption("Nothing to review in this period.")
else:
    st.dataframe(
        review[["time", "user_id", "prompt", "decision", "risk", "category_policy", "gate_reason"]],
        hide_index=True, height=min(38 + 35 * len(review), 320),
        column_order=["time", "user_id", "prompt", "decision", "risk", "category_policy", "gate_reason"]
        if has_users else ["time", "prompt", "decision", "risk", "category_policy", "gate_reason"],
        column_config={
            "time": st.column_config.DatetimeColumn("Time (UTC)", format="DD MMM YYYY, HH:mm"),
            "user_id": "User", "prompt": st.column_config.TextColumn("Prompt", width="large"),
            "decision": "Decision", "risk": "Risk", "category_policy": "Category (policy)",
            "gate_reason": st.column_config.TextColumn("Gate explanation", width="large"),
        })

# --------------------------------------------------------------------------- usage
section("How is it being used?", "Only allowed prompts go on to the intent classifier and router.")
u1, u2 = st.columns(2, gap="large")
with u1:
    st.markdown("**What people asked for** · intent")
    intents = P["intent"].dropna().str.split(", ").explode().value_counts().rename_axis("intent").reset_index(name="prompts")
    if intents.empty:
        st.caption("No intent classifications in this period.")
    else:
        chart, h = hbar(intents, "intent", "prompts", BLUE, "Prompts")
        show(chart, h)
with u2:
    routed = P[P["routes"].notna()]
    st.markdown(f"**What the router sent them to** · share of {len(routed):,} routed prompts")
    if routed.empty:
        st.caption("No routing decisions in this period.")
    else:
        caps = list(cd.ROUTE_FLAGS.values()) + ["Direct answer only"]
        counts = {c: int(routed["routes"].map(lambda r, c=c: c in r).sum()) for c in caps[:-1]}
        counts["Direct answer only"] = int(routed["routes"].map(len).eq(0).sum())
        cap_df = pd.DataFrame({"capability": list(counts), "prompts": list(counts.values())})
        cap_df["share"] = cap_df["prompts"] / len(routed)
        chart, h = hbar(cap_df, "capability", "share", BLUE, "Share of routed prompts", fmt=".0%", axis_fmt=".0%",
                        tooltip=[alt.Tooltip("capability:N", title="Capability"),
                                 alt.Tooltip("prompts:Q", title="Prompts"),
                                 alt.Tooltip("share:Q", title="Share", format=".0%")])
        show(chart, h)
        st.caption("A prompt can need more than one capability.")

# --------------------------------------------------------------------------- pipeline health
section("Is it working?", "Errors raised inside the Cortexa pipeline for allowed prompts.")
errors = cd.error_table(P)
if errors.empty:
    st.success("No pipeline errors in this period.")
else:
    st.dataframe(errors, hide_index=True,
                 column_config={"Message": st.column_config.TextColumn(width="large"),
                                "Last seen (UTC)": st.column_config.DatetimeColumn(format="DD MMM YYYY, HH:mm")})
    st.caption(f"{failed} of {len(allowed)} allowed prompts ended in a failed run. "
               "A failure in one module can cause errors in the modules after it.")

# --------------------------------------------------------------------------- LLM usage
section("LLM usage", "Model calls made by the pipeline, including the decision-gate checks on blocked prompts.")
if C.empty:
    st.caption("No LLM calls in this period.")
else:
    m = st.columns(4)
    tile(m[0], "LLM calls", fmt_int(len(C)), f"{len(C) / n:.1f} per prompt")
    tile(m[1], "Input tokens", fmt_int(C["input_tokens"].sum()))
    tile(m[2], "Output tokens", fmt_int(C["output_tokens"].sum()))
    tile(m[3], "Median call time", f"{C['duration_ms'].median() / 1000:.1f} s",
         f"95th percentile {C['duration_ms'].quantile(0.95) / 1000:.1f} s")
    st.markdown("")
    l1, l2 = st.columns([1, 1], gap="large")
    with l1:
        st.markdown("**Tokens by pipeline step** · input + output")
        steps = (C.assign(model=short_model(C["llm_name"]))
                 .groupby(["submodule", "model"])
                 .agg(tokens=("input_tokens", "sum"), out=("output_tokens", "sum"), calls=("event_id", "size"))
                 .reset_index())
        steps["tokens"] = steps["tokens"] + steps["out"]
        steps["step"] = steps["submodule"].map(lambda x: STEP_NAMES.get(x, x.replace("_", " ").capitalize())) \
            + " · " + steps["model"]
        chart, h = hbar(steps, "step", "tokens", VIOLET, "Tokens",
                        tooltip=[alt.Tooltip("step:N", title="Step · model"),
                                 alt.Tooltip("tokens:Q", title="Tokens", format=","),
                                 alt.Tooltip("calls:Q", title="Calls")], fmt=",", axis_fmt="~s")
        show(chart, h)
    with l2:
        st.markdown("**By model**")
        by_model = (C.assign(model=short_model(C["llm_name"])).groupby("model")
                    .agg(calls=("event_id", "size"), inp=("input_tokens", "sum"), out=("output_tokens", "sum"),
                         p50=("duration_ms", "median"))
                    .round(0).reset_index().sort_values("calls", ascending=False))
        by_model.columns = ["Model", "Calls", "Input tokens", "Output tokens", "Median ms"]
        st.dataframe(by_model, hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format="localized")
                                    for c in by_model.columns[1:]})
        st.caption("Model names are shortened (provider prefix and version suffix removed).")

# --------------------------------------------------------------------------- audit trail
section("Audit trail", "Every prompt in the selected period. Search, then download as CSV.")
query = st.text_input("Search prompts, users, policies or event IDs", placeholder="e.g. password, USR-007, S13")
audit = P.copy()
audit["capabilities"] = audit["routes"].map(lambda r: ", ".join(r) if isinstance(r, list) else None)
cols = ["time", "user_id", "session_id", "prompt", "decision", "risk", "category", "policy", "intent",
        "capabilities", "outcome", "error_codes", "response", "entrypoint", "event_id"]
audit = audit[cols]
if query:
    hay = audit.astype(object).where(audit.notna(), "").astype(str).agg(" ".join, axis=1).str.lower()
    audit = audit[hay.str.contains(query.lower(), regex=False)]
st.dataframe(
    audit, hide_index=True, height=420,
    column_order=cols if has_users else [c for c in cols if c not in ("user_id", "session_id")],
    column_config={
        "time": st.column_config.DatetimeColumn("Time (UTC)", format="DD MMM YYYY, HH:mm:ss"),
        "user_id": "User", "session_id": "Session", "prompt": st.column_config.TextColumn("Prompt", width="large"),
        "decision": "Decision", "risk": "Risk", "category": "Category", "policy": "Policy", "intent": "Intent",
        "capabilities": "Capabilities", "outcome": "Outcome", "error_codes": "Errors",
        "response": st.column_config.TextColumn("Response", width="medium"), "entrypoint": "Entrypoint",
        "event_id": "Event ID",
    })
st.download_button(
    f"Download {len(audit):,} rows as CSV",
    audit.to_csv(index=False).encode("utf-8"),
    file_name=f"cortexa_audit_{DATASET}_{start:%Y%m%d}_{end:%Y%m%d}.csv", mime="text/csv")
