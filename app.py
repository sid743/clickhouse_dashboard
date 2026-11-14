"""
Cortexa - AI Auditing and Analysis dashboard

Run:  streamlit run app.py
"""

import base64
import html
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import auth
import cortexa_data as cd

MARK = Path(__file__).parent / "assets" / "cortexa_mark.png"    # icon only, used for the browser tab
LOGO = Path(__file__).parent / "assets" / "cortexa_logo.png"    # full logo from cortexa.global, used in the sidebar
APP_TITLE = "AI Auditing and Analysis"
st.set_page_config(page_title=f"Cortexa · {APP_TITLE}", layout="wide",
                   page_icon=str(MARK) if MARK.exists() else None)
LOGO_B64 = base64.b64encode(LOGO.read_bytes()).decode() if LOGO.exists() else ""

# --------------------------------------------------------------------------- colours & style
# Allowed / blocked are the two series used across the page (validated pair, white surface).
# Brand colours from the Cortexa logo: indigo #3b12f0 and purple #8a12c8
BLUE, ORANGE, VIOLET, GRAY = "#3b12f0", "#eb6834", "#8a12c8", "#b5b3ab"
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
  .tile {{ border: 1px solid rgba(11,11,11,0.10); border-radius: 10px; padding: 14px 12px; background: #fff; height: 100%; }}
  .tile-label {{ color: {INK2}; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.02em; text-transform: uppercase;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .tile-value {{ color: {INK}; font-size: 1.9rem; font-weight: 600; line-height: 1.2; margin-top: 2px; }}
  .tile-note {{ color: {MUTED}; font-size: 0.8rem; margin-top: 2px; }}
  .tile.small .tile-value {{ font-size: 1.15rem; }}
  /* the four main tabs: big, bold, brand underline */
  .stTabs [role="tablist"] {{ gap: 2.4rem; margin-bottom: 1rem; }}
  .stTabs [role="tab"] {{ height: 3.4rem; padding: 0 0.2rem; }}
  .stTabs [role="tab"] p {{ font-size: 1.35rem !important; font-weight: 700 !important; color: {INK2}; }}
  .stTabs [role="tab"][aria-selected="true"] p {{ color: {BLUE}; }}
  .stTabs [data-baseweb="tab-highlight"] {{ background: linear-gradient(90deg, {BLUE}, {VIOLET}); height: 4px; }}
  .big-split {{ font-size: 1.35rem; color: {INK}; margin: 0.4rem 0 0.2rem 0; }}
  .tier-head {{ font-size: 1.25rem; font-weight: 700; color: {VIOLET}; margin-bottom: 0.4rem; }}
  .brand {{ display: flex; align-items: center; margin-bottom: 0.2rem;
           background: linear-gradient(90deg, {BLUE}, {VIOLET}); -webkit-background-clip: text; color: transparent; }}
  .brand img {{ width: 200px; max-width: 100%; }}
  [data-testid="stHeading"] hr {{ background: linear-gradient(90deg, {BLUE}, {VIOLET}) !important; height: 2px; border: 0; }}
  .brand-sub {{ font-size: 0.75rem; font-weight: 600; color: {MUTED}; letter-spacing: 0.08em; margin-bottom: 0.6rem; }}
  .side-head {{ font-size: 0.8rem; font-weight: 700; color: {INK}; letter-spacing: 0.06em; margin: 0.4rem 0 0.2rem 0; }}
  .prompt-text {{ font-size: 1.1rem; color: {INK}; margin: 0.2rem 0 0.5rem 0; }}
  .meta {{ color: {MUTED}; font-size: 0.82rem; }}
  .caps div {{ margin: 0.15rem 0; color: {INK}; }}
  .caps .off {{ color: {MUTED}; }}
</style>
""", unsafe_allow_html=True)


def tile(col, label, value, note="", small=False):
    col.markdown(f'<div class="tile{" small" if small else ""}"><div class="tile-label">{label}</div>'
                 f'<div class="tile-value">{value}</div><div class="tile-note">{note}</div></div>',
                 unsafe_allow_html=True)



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


def text_or(value, default="–"):
    return default if value is None or (isinstance(value, float) and pd.isna(value)) or value == "" else value


# --------------------------------------------------------------------------- upload password
# There is no login. Anyone can view the dashboard; saving a new export asks for an admin password
# (any user with role = "admin" in .streamlit/secrets.toml).

def load_users():
    try:
        return {name: dict(cfg) for name, cfg in st.secrets["users"].items()}
    except Exception:
        return {}


def is_admin_password(password):
    return any(cfg.get("role") == "admin" and auth.check_password(password, cfg.get("password_hash", ""))
               for cfg in load_users().values())


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
        msg = "No real export has been uploaded yet. Use the upload panel in the sidebar."
        return None, None, msg
    return (*load(file_key(files)), None)


@st.dialog("Admin password required")
def confirm_upload(up, replace):
    st.write(f"Enter the admin password to {'replace the real data with' if replace else 'add'} **{up.name}**.")
    if not load_users():
        st.error("No admin user is set up. Add one to .streamlit/secrets.toml (see README).")
        return
    with st.form("upload_password"):
        password = st.text_input("Admin password", type="password")
        ok = st.form_submit_button("Upload", type="primary", width="stretch")
    if ok:
        if is_admin_password(password):
            saved = cd.save_upload(up, replace=replace)
            st.session_state.upload_msg = f"Saved {saved.name}."
            st.session_state.upload_key += 1
            st.session_state.dataset = "real"
            st.rerun()
        st.error("Wrong password. Nothing was uploaded.")


def admin_upload():
    st.markdown('<div class="side-head">UPLOAD A CLICKHOUSE EXPORT</div>', unsafe_allow_html=True)
    st.caption("Excel file with the sheets graph_state_events and llm_calls. Goes into the real-data dashboard. "
               "Needs the admin password.")
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
            if st.button("Upload to dashboard", type="primary", width="stretch", disabled=not len(p_new)):
                confirm_upload(up, mode.startswith("Replacing"))
        except ValueError as exc:
            st.error(str(exc))
    files = cd.real_files()
    with st.expander(f"Real-data files ({len(files)})"):
        for f in files:
            st.caption(f.name)
        if not files:
            st.caption("None yet.")


# --------------------------------------------------------------------------- sidebar: data & filters

sidebar = st.sidebar
sidebar.markdown(f'<div class="brand"><img src="data:image/png;base64,{LOGO_B64}" alt="CORTEXA"/></div>'
                 '<div class="brand-sub">AI AUDIT CONSOLE</div>',
                 unsafe_allow_html=True)
sidebar.markdown('<div class="side-head">DATA & FILTERS</div>', unsafe_allow_html=True)
sidebar.caption("Data origin")
for label, name in (("View real data dashboard", "real"), ("View synthetic data dashboard", "synthetic")):
    if sidebar.button(label, type="primary" if st.session_state.dataset == name else "secondary",
                      width="stretch", key=f"ds_{name}"):
        st.session_state.dataset = name
        st.rerun()

DATASET = st.session_state.dataset
prompts_all, calls_all, problem = load_dataset(DATASET)

if not problem and not prompts_all.empty:
    names = cd.app_names()  # read every run so edits to app_names.csv show up straight away
    prompts_all = prompts_all.assign(app=prompts_all["app_id"].map(lambda a: cd.app_label(a, names)))
    apps = sorted(prompts_all["app"].unique())
    app_pick = sidebar.selectbox("Application", ["All applications"] + apps, key=f"app_{DATASET}")
    decision_pick = sidebar.selectbox("Policy decision", ["All decisions", "Allowed only", "Blocked only"],
                                      key=f"decision_{DATASET}")
    first, last = prompts_all["time"].min().date(), prompts_all["time"].max().date()
    picked = sidebar.date_input("Date range (UTC)", value=(first, last), min_value=first, max_value=last,
                                format="DD/MM/YYYY", key=f"dates_{DATASET}_{first}_{last}")
    start, end = (picked if isinstance(picked, (list, tuple)) and len(picked) == 2 else (first, last))
    sidebar.caption("Filters apply to every section.")

sidebar.divider()
with sidebar:
    admin_upload()


# --------------------------------------------------------------------------- header

st.title(APP_TITLE)
if problem:
    st.info(problem)
    st.stop()
if prompts_all.empty:
    st.info("The loaded export contains no prompts.")
    st.stop()

mask = (prompts_all["time"] >= pd.Timestamp(start)) & (prompts_all["time"] < pd.Timestamp(end) + pd.Timedelta(days=1))
if app_pick != "All applications":
    mask &= prompts_all["app"] == app_pick
if decision_pick != "All decisions":
    mask &= prompts_all["decision"] == decision_pick.split()[0]
P = prompts_all[mask]
C = calls_all[calls_all["event_id"].isin(P["event_id"])]
if P.empty:
    st.info("No prompts match these filters.")
    st.stop()

has_users = P["user_id"].notna().any()
n = len(P)
blocked = int((P["decision"] == "Blocked").sum())
high = P[P["risk"] == "High"]
high_allowed = int((high["decision"] == "Allowed").sum())
allowed = P[P["decision"] == "Allowed"]
failed = int((P["outcome"] == "Failed").sum())
high_note = "all blocked" if len(high) and not high_allowed else f"{high_allowed} allowed" if len(high) else "none"
# Colour follows the decision everywhere on the page; "Unknown" only appears if the data has it
present = [d for d in DECISION_DOMAIN if d in set(P["decision"])]
DECISION_SCALE = alt.Scale(domain=present, range=[DECISION_RANGE[DECISION_DOMAIN.index(d)] for d in present])

tab_overview, tab_security, tab_usage, tab_explorer = st.tabs(
    ["Executive overview", "Security & policy", "Usage intelligence", "Prompt explorer"])


# =========================================================================== 1. Executive overview
with tab_overview:
    k = st.columns(5)
    tile(k[0], "Prompt events", fmt_int(n), f"{P['date'].nunique()} active days")
    tile(k[1], "Allowed", fmt_int(len(allowed)), f"{len(allowed) / n:.0%} of prompts")
    tile(k[2], "Blocked", fmt_int(blocked), f"{blocked / n:.0%} of prompts")
    tile(k[3], "Execution failures", fmt_int(failed), f"{failed / max(len(allowed), 1):.0%} of allowed")
    tile(k[4], "Users", fmt_int(P["user_id"].nunique()) if has_users else "–",
         f"{P['session_id'].nunique()} sessions" if has_users else "user_id not recorded")
    st.markdown("")

    o1, o2 = st.columns(2, gap="medium")
    with o1, st.container(border=True):
        st.markdown("**Execution** · share of prompts allowed vs blocked")
        split = P["decision"].value_counts().reindex(present, fill_value=0).rename_axis("decision").reset_index(name="prompts")
        split["share"] = split["prompts"] / n
        split["end"] = split["share"].cumsum()
        split["start"] = split["end"] - split["share"]
        split["mid"] = (split["start"] + split["end"]) / 2
        split["label"] = split.apply(lambda r: f"{r['share']:.0%}" if r["share"] >= 0.06 else "", axis=1)
        figures = " &nbsp;·&nbsp; ".join(f"<b>{r.share:.0%}</b> {r.decision.lower()}" for r in split.itertuples())
        st.markdown(f'<div class="big-split">{figures}</div>', unsafe_allow_html=True)
        seg = alt.Chart(split).mark_bar(size=28, cornerRadius=4, stroke="#ffffff", strokeWidth=2).encode(
            x=alt.X("start:Q", axis=None, scale=alt.Scale(domain=[0, 1])), x2="end:Q",
            color=alt.Color("decision:N", scale=DECISION_SCALE),
            tooltip=[alt.Tooltip("decision:N", title="Decision"), alt.Tooltip("prompts:Q", title="Prompts"),
                     alt.Tooltip("share:Q", title="Share", format=".0%")])
        text = alt.Chart(split).mark_text(color="#ffffff", fontSize=13, fontWeight="bold").encode(
            x="mid:Q", text="label:N")
        show(seg + text, 70)
        completed = int((allowed["outcome"] == "Completed").sum())
        st.caption(f"Of {len(allowed):,} allowed prompts, {completed:,} completed and {failed:,} failed during execution.")

    with o2, st.container(border=True):
        st.markdown("**Intent** · what people asked for (allowed prompts)")
        intents = (P["intent"].dropna().str.split(", ").explode().value_counts()
                   .rename_axis("intent").reset_index(name="prompts"))
        if intents.empty:
            st.caption("No intent classifications for these filters. Blocked prompts never reach the intent classifier.")
        else:
            chart, h = hbar(intents, "intent", "prompts", BLUE, "Prompts")
            show(chart, h)

    o3, o4 = st.columns(2, gap="medium")
    with o3, st.container(border=True):
        span_days = (P["date"].max() - P["date"].min()).days
        period = "week" if span_days > 62 else "day"
        st.markdown(f"**Prompt activity trend** · prompts per {period}")
        to_period = (lambda s: s.dt.to_period("W").dt.start_time) if period == "week" else (lambda s: s.dt.normalize())
        act = P.assign(period=to_period(P["time"])).groupby(["period", "decision"]).size().reset_index(name="prompts")
        # every day/week in the range gets a point, so quiet days show as zero rather than disappearing
        slots = pd.date_range(to_period(pd.Series([pd.Timestamp(start)]))[0], pd.Timestamp(end),
                              freq="W-MON" if period == "week" else "D")
        act = act.pivot(index="period", columns="decision", values="prompts").reindex(slots, fill_value=0).fillna(0)
        act = act.rename_axis("period").reset_index().melt("period", var_name="decision", value_name="prompts")
        trend = alt.Chart(act).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=45, filled=True)).encode(
            x=alt.X("period:T", title=None, axis=alt.Axis(format="%d %b", labelAngle=0, grid=False,
                                                         labelOverlap="greedy")),
            y=alt.Y("prompts:Q", title="Prompts", axis=alt.Axis(tickMinStep=1)),
            color=alt.Color("decision:N", scale=DECISION_SCALE),
            tooltip=[alt.Tooltip("period:T", title="Week of" if period == "week" else "Day", format="%d %b %Y"),
                     alt.Tooltip("decision:N", title="Decision"), alt.Tooltip("prompts:Q", title="Prompts")],
        )
        show(trend, 250)

    with o4, st.container(border=True):
        routed = P[P["routes"].notna()]
        st.markdown(f"**What the router sent them to** · share of {len(routed):,} routed prompts")
        if routed.empty:
            st.caption("No routing decisions for these filters. Blocked prompts never reach the router.")
        else:
            counts = {c: int(routed["routes"].map(lambda r, c=c: c in r).sum()) for c in cd.ROUTE_FLAGS.values()}
            counts["Direct answer only"] = int(routed["routes"].map(len).eq(0).sum())
            cap_df = pd.DataFrame({"capability": list(counts), "prompts": list(counts.values())})
            cap_df["share"] = cap_df["prompts"] / len(routed)
            chart, h = hbar(cap_df, "capability", "share", BLUE, "Share of routed prompts", fmt=".0%",
                            axis_fmt=".0%", tooltip=[alt.Tooltip("capability:N", title="Capability"),
                                                     alt.Tooltip("prompts:Q", title="Prompts"),
                                                     alt.Tooltip("share:Q", title="Share", format=".0%")])
            show(chart, h)
            st.caption("A prompt can need more than one capability.")


# =========================================================================== 2. Security & policy
with tab_security:
    k = st.columns(3)
    tile(k[0], "Allowed", fmt_int(len(allowed)), f"{len(allowed) / n:.0%} of prompts")
    tile(k[1], "Blocked", fmt_int(blocked), f"{blocked / n:.0%} of prompts")
    tile(k[2], "High-risk labels", fmt_int(len(high)), high_note)
    st.markdown("")

    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(border=True):
        st.markdown("**Risk level** · from the decision gate")
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
    with c2, st.container(border=True):
        st.markdown("**By policy category** · allowed vs blocked")
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

    c3, _ = st.columns(2, gap="medium")
    with c3, st.container(border=True):
        st.markdown("**High risk · top 10 users** · users with the most high-risk prompts")
        if not has_users:
            st.caption("Can't be shown: user_id and session_id are empty in this export.")
        else:
            users = (P.groupby("user_id").agg(high=("risk", lambda s: int((s == "High").sum())),
                                              blocked=("decision", lambda s: int((s == "Blocked").sum())),
                                              prompts=("event_id", "size"), sessions=("session_id", "nunique"))
                     .reset_index())
            users = users[users["high"] > 0].sort_values(["high", "blocked"], ascending=False).head(10)
            if users.empty:
                st.caption("No high-risk prompts for these filters.")
            else:
                chart, h = hbar(users, "user_id", "high", RISK_RANGE[0], "High-risk prompts",
                                tooltip=[alt.Tooltip("user_id:N", title="User"),
                                         alt.Tooltip("high:Q", title="High-risk prompts"),
                                         alt.Tooltip("blocked:Q", title="Blocked"),
                                         alt.Tooltip("prompts:Q", title="All prompts"),
                                         alt.Tooltip("sessions:Q", title="Sessions")])
                show(chart, h)
                st.caption("Several high-risk prompts from one user, especially in one session, can point to "
                           "deliberate probing.")


# =========================================================================== 3. Usage intelligence
with tab_usage:
    if C.empty:
        st.caption("No model calls for these filters.")
    else:
        C = C.assign(tier=[cd.model_tier(m, s) for m, s in zip(C["llm_name"], C["submodule"])])
        tiers = [t for t in ("SLM", "LLM") if t in set(C["tier"])]
        cols = st.columns(len(tiers), gap="medium")
        for col, tier in zip(cols, tiers):
            T = C[C["tier"] == tier]
            with col, st.container(border=True):
                st.markdown(f'<div class="tier-head">{tier}</div>', unsafe_allow_html=True)
                a, b = st.columns(2)
                tile(a, f"{tier} calls", fmt_int(len(T)), f"{len(T) / n:.1f} per prompt")
                tile(b, "Latency", f"{T['duration_ms'].median() / 1000:.1f} s",
                     f"median · 95th percentile {T['duration_ms'].quantile(0.95) / 1000:.1f} s")
                st.markdown("")
                a, b = st.columns(2)
                tile(a, "Input tokens", fmt_int(T["input_tokens"].sum()))
                tile(b, "Output tokens", fmt_int(T["output_tokens"].sum()))
                st.markdown("")

        st.markdown("")
        cols = st.columns(len(tiers), gap="medium")
        for col, tier in zip(cols, tiers):
            T = C[C["tier"] == tier]
            with col, st.container(border=True):
                st.markdown(f"**{tier} tokens by pipeline step** · input + output")
                steps = (T.groupby("submodule")
                         .agg(inp=("input_tokens", "sum"), out=("output_tokens", "sum"), calls=("event_id", "size"))
                         .reset_index())
                steps["tokens"] = steps["inp"] + steps["out"]
                steps["step"] = steps["submodule"].map(lambda x: STEP_NAMES.get(x, x.replace("_", " ").capitalize()))
                chart, h = hbar(steps, "step", "tokens", VIOLET, "Tokens", fmt=",", axis_fmt="~s",
                                tooltip=[alt.Tooltip("step:N", title="Step"),
                                         alt.Tooltip("inp:Q", title="Input tokens", format=","),
                                         alt.Tooltip("out:Q", title="Output tokens", format=","),
                                         alt.Tooltip("calls:Q", title="Calls")])
                show(chart, h)

    st.markdown("")
    with st.container(border=True):
        st.markdown("**Pipeline errors** · raised inside Cortexa for allowed prompts")
        errors = cd.error_table(P)
        if errors.empty:
            st.success("No pipeline errors for these filters.")
        else:
            st.dataframe(errors[["Module", "Error code", "Occurrences", "Last seen (UTC)", "Message"]],
                         hide_index=True,
                         column_config={"Last seen (UTC)": st.column_config.DatetimeColumn(format="DD MMM, HH:mm"),
                                        "Message": st.column_config.TextColumn(width="large")})
            st.caption(f"{failed} of {len(allowed)} allowed prompts ended in a failed run. "
                       "A failure in one module can cause errors in the modules after it.")


# =========================================================================== 4. Prompt explorer
with tab_explorer:
    detail = st.container()  # the selected prompt is drawn here, above the table, once we know which row it is

    st.markdown("")
    st.markdown("**All prompts** · filter by column or search, then click a row to show it above")
    # Excel-style filters for the columns that hold a fixed set of values. Options come from the whole
    # dataset so a choice stays valid when the sidebar filters change.
    filter_cols = [("app", "Application"), ("decision", "Decision"), ("risk", "Risk"), ("category", "Category"),
                   ("policy", "Policy"), ("intent", "Intent"), ("outcome", "Outcome"), ("entrypoint", "Entrypoint")]
    blank = "(blank)"
    as_text = lambda series: series.astype(object).where(series.notna(), blank).astype(str)
    picks = {}
    fcols = st.columns(4)
    for i, (col, label) in enumerate(filter_cols):
        options = sorted(as_text(prompts_all[col]).unique())
        picks[col] = fcols[i % 4].multiselect(label, options, placeholder="All", key=f"xf_{DATASET}_{col}")
    query = st.text_input("Search prompts, users, sessions or event IDs", placeholder="e.g. password, USR-007, S13")

    audit = P.copy()
    audit["capabilities"] = audit["routes"].map(lambda r: ", ".join(r) if isinstance(r, list) else None)
    cols = ["time", "app", "user_id", "session_id", "prompt", "decision", "risk", "category", "policy", "intent",
            "capabilities", "outcome", "error_codes", "response", "entrypoint", "event_id"]
    audit = audit[cols + ["routes", "gate_reason", "errors"]]
    for col, chosen in picks.items():
        if chosen:
            audit = audit[as_text(audit[col]).isin(chosen)]
    if query:
        hay = audit[cols].astype(object).where(audit[cols].notna(), "").astype(str).agg(" ".join, axis=1).str.lower()
        audit = audit[hay.str.contains(query.lower(), regex=False)]
    audit = audit.reset_index(drop=True)

    view_key = "|".join([DATASET, app_pick, decision_pick, str(start), str(end), query] +
                        [",".join(v) for v in picks.values()])
    picked_rows = st.dataframe(
        audit[cols], hide_index=True, height=380, on_select="rerun", selection_mode="single-row",
        key=f"explorer_{abs(hash(view_key))}",  # any filter change resets the clicked row
        column_order=cols if has_users else [c for c in cols if c not in ("user_id", "session_id")],
        column_config={
            "time": st.column_config.DatetimeColumn("Time (UTC)", format="DD MMM YYYY, HH:mm:ss"),
            "app": "Application", "user_id": "User", "session_id": "Session",
            "prompt": st.column_config.TextColumn("Prompt", width="large"),
            "decision": "Decision", "risk": "Risk", "category": "Category", "policy": "Policy", "intent": "Intent",
            "capabilities": "Capabilities", "outcome": "Outcome", "error_codes": "Errors",
            "response": st.column_config.TextColumn("Response", width="medium"), "entrypoint": "Entrypoint",
            "event_id": "Event ID",
        })
    st.download_button(
        f"Download {len(audit):,} rows as CSV",
        audit[cols].to_csv(index=False).encode("utf-8"),
        file_name=f"cortexa_audit_{DATASET}_{start:%Y%m%d}_{end:%Y%m%d}.csv", mime="text/csv")

    with detail:
        if audit.empty:
            st.info("No prompts match these filters.")
        else:
            rows = picked_rows.selection.rows if picked_rows is not None else []
            i = rows[0] if rows and rows[0] < len(audit) else 0
            r = audit.iloc[i]
            st.markdown(f"**Selected prompt** · "
                        f"{'row you clicked' if rows else 'latest prompt (click a row in the table below to change)'}")
            with st.container(border=True):
                st.markdown(f'<div class="meta">User prompt</div>'
                            f'<div class="prompt-text">{html.escape(text_or(r["prompt"], "(no prompt text)"))}</div>'
                            f'<div class="meta">{r["time"]:%d %b %Y, %H:%M:%S} UTC · {html.escape(r["app"])} · '
                            f'User {html.escape(str(text_or(r["user_id"])))} · '
                            f'Session {html.escape(str(text_or(r["session_id"])))} · '
                            f'{html.escape(str(text_or(r["entrypoint"])))} · Event {r["event_id"]}</div>',
                            unsafe_allow_html=True)
            d = st.columns(5)
            tile(d[0], "Decision", r["decision"], small=True)
            tile(d[1], "Risk", r["risk"], small=True)
            tile(d[2], "Policy", text_or(r["policy"]), html.escape(text_or(r["category"], "")), small=True)
            tile(d[3], "Intent", text_or(r["intent"]), "" if text_or(r["intent"], "") else "not classified", small=True)
            tile(d[4], "Outcome", r["outcome"], text_or(r["error_codes"], ""), small=True)
            st.markdown("")
            e1, e2 = st.columns(2, gap="medium")
            with e1, st.container(border=True):
                st.markdown("**Decision explanation**")
                st.write(text_or(r["gate_reason"], "No explanation recorded."))
                if r["errors"]:
                    st.markdown("**Errors**")
                    for module, code, message, _ in r["errors"]:
                        st.caption(f"{module} · {code}: {str(message).splitlines()[0][:200]}")
            with e2, st.container(border=True):
                st.markdown("**Capabilities the router asked for**")
                if isinstance(r["routes"], list):
                    marks = "".join(f'<div>✓ {c}</div>' if c in r["routes"] else f'<div class="off">– {c}</div>'
                                    for c in cd.ROUTE_FLAGS.values())
                    st.markdown(f'<div class="caps">{marks}</div>', unsafe_allow_html=True)
                else:
                    st.write("Not routed. The prompt was blocked before it reached the router.")
                st.caption("Router flags show what was requested; they don't prove a tool or dataset was used.")
            with st.expander("Response returned to the user"):
                st.write(text_or(r["response"], "No response recorded."))
