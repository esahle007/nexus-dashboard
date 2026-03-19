"""
app.py — Project Nexus · Human-first Dashboard
30-day baselines, today vs average, plain-English lifestyle impact cards.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone

import synthetic as _syn
import impact_windows as _iw

generate                = _syn.generate
IMPACT_WINDOW_REGISTRY  = _iw.IMPACT_WINDOW_REGISTRY
ImpactWindow            = _iw.ImpactWindow
compute_weighted_signal = _iw.compute_weighted_signal

def load_biometrics(days=90):
    try:
        import whoop_client as _wc
        return _wc.load_biometrics(days=days)
    except Exception:
        bio_df, _ = generate(days=days)
        return bio_df, "synthetic"

def hex_to_rgba(hex_color, alpha=0.15):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f"rgba({r},{g},{b},{alpha})"

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Nexus Health", page_icon="🧬",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

/* ── Metric hero cards ── */
.metric-hero {
    background: #111318;
    border: 1px solid #1e2130;
    border-radius: 20px;
    padding: 22px 20px 18px;
    position: relative;
    overflow: hidden;
    min-height: 168px;
}
.metric-hero-glow {
    position: absolute;
    top: -40px; right: -40px;
    width: 130px; height: 130px;
    border-radius: 50%;
    filter: blur(40px);
    opacity: 0.18;
}
.metric-hero-label {
    font-size: 0.68rem; font-weight: 600;
    letter-spacing: 0.1em; text-transform: uppercase;
    color: #4b5563; margin-bottom: 8px;
}
.metric-hero-value {
    font-size: 3rem; font-weight: 700;
    line-height: 1; letter-spacing: -0.02em;
    margin-bottom: 2px;
}
.metric-hero-unit {
    font-size: 1.1rem; font-weight: 400;
    color: #6b7280; margin-left: 3px;
}
.metric-hero-avg {
    font-size: 0.78rem; color: #4b5563;
    margin-bottom: 14px; margin-top: 4px;
}
.metric-hero-avg b { color: #9ca3af; font-weight: 500; }
.delta-chip {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 5px 12px; border-radius: 30px;
    font-size: 0.76rem; font-weight: 600;
    letter-spacing: 0.02em;
}
.chip-good { background: rgba(16,185,129,0.12); color: #34d399; border: 1px solid rgba(16,185,129,0.2); }
.chip-bad  { background: rgba(244,63,94,0.12);  color: #fb7185; border: 1px solid rgba(244,63,94,0.2);  }
.chip-flat { background: rgba(107,114,128,0.12);color: #9ca3af; border: 1px solid rgba(107,114,128,0.2);}

/* ── Section label ── */
.sec-label {
    font-size: 0.65rem; font-weight: 700;
    letter-spacing: 0.14em; text-transform: uppercase;
    color: #374151; margin: 0 0 18px;
}

/* ── Impact factor cards ── */
.impact-wrap {
    background: #111318;
    border: 1px solid #1e2130;
    border-radius: 16px;
    padding: 20px 18px;
    height: 100%;
}
.impact-top {
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 12px;
}
.impact-icon-wrap {
    width: 44px; height: 44px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.3rem; flex-shrink: 0;
}
.impact-name { font-size: 0.95rem; font-weight: 600; color: #e5e7eb; }
.impact-sub  { font-size: 0.75rem; color: #6b7280; margin-top: 1px; }
.impact-body { font-size: 0.82rem; color: #9ca3af; line-height: 1.6; margin-bottom: 12px; }
.tag {
    display: inline-block; padding: 3px 9px;
    border-radius: 6px; font-size: 0.68rem; font-weight: 600;
    margin-right: 5px; margin-top: 2px;
}
.tag-neg { background: rgba(244,63,94,0.1);  color: #fb7185; }
.tag-pos { background: rgba(16,185,129,0.1); color: #34d399; }
.tag-neu { background: rgba(107,114,128,0.1);color: #9ca3af; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #0c0e14;
    border-right: 1px solid #1a1d26;
}
[data-testid="stSidebar"] .stSlider label { font-size: 0.82rem; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] { gap: 4px; background: transparent; }
.stTabs [data-baseweb="tab"] {
    background: #111318; border: 1px solid #1e2130;
    border-radius: 10px; padding: 6px 16px;
    font-size: 0.82rem; font-weight: 500;
}
.stTabs [aria-selected="true"] { background: #1e2130; border-color: #374151; }

/* ── Badges ── */
.badge-live  { display:inline-block; padding:3px 10px; border-radius:20px;
    font-size:0.68rem; font-weight:700; letter-spacing:0.06em;
    background:rgba(16,185,129,0.1); color:#34d399; border:1px solid rgba(16,185,129,0.2); }
.badge-demo  { display:inline-block; padding:3px 10px; border-radius:20px;
    font-size:0.68rem; font-weight:700; letter-spacing:0.06em;
    background:rgba(139,92,246,0.1); color:#a78bfa; border:1px solid rgba(139,92,246,0.2); }

/* Ring chart container */
.ring-row { display:flex; gap:16px; flex-wrap:wrap; }
</style>
""", unsafe_allow_html=True)

# ── Metric + context config ────────────────────────────────────────────────────
METRICS = {
    "HRV":        {"label":"Recovery",       "unit":"ms",  "color":"#818cf8", "higher_is_better":True},
    "RHR":        {"label":"Resting HR",     "unit":"bpm", "color":"#fb7185", "higher_is_better":False},
    "DEEP_SLEEP": {"label":"Deep Sleep",     "unit":"min", "color":"#34d399", "higher_is_better":True},
    "TEMP_SHIFT": {"label":"Body Temp",      "unit":"°C",  "color":"#fbbf24", "higher_is_better":None},
}
CONTEXT_META = {
    "caffeine":        {"icon":"☕","label":"Caffeine",          "color":"#fbbf24","bg":"rgba(251,191,36,0.1)"},
    "alcohol":         {"icon":"🍷","label":"Alcohol",           "color":"#fb7185","bg":"rgba(251,113,133,0.1)"},
    "social_conflict": {"icon":"⚡","label":"Stress",            "color":"#c084fc","bg":"rgba(192,132,252,0.1)"},
    "blue_light":      {"icon":"📱","label":"Screen Time",       "color":"#60a5fa","bg":"rgba(96,165,250,0.1)"},
    "morning_light":   {"icon":"🌅","label":"Morning Sunlight",  "color":"#34d399","bg":"rgba(52,211,153,0.1)"},
}

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧬 Nexus")
    st.markdown("<p style='color:#4b5563;font-size:0.8rem;margin-top:-8px'>Personal health intelligence</p>", unsafe_allow_html=True)
    st.divider()
    st.markdown("**Log today's habits**")
    selected_context = st.selectbox(
        "What are you logging?",
        list(CONTEXT_META.keys()),
        format_func=lambda x: f"{CONTEXT_META[x]['icon']}  {CONTEXT_META[x]['label']}"
    )
    log_qty  = st.slider("Amount / Intensity", 0.1, 3.0, 1.0, step=0.1,
                          help="1 = one cup of coffee, one drink, moderate stress, etc.")
    log_hour = st.slider("What time?", 0, 23, 8, format="%d:00")
    if st.button("➕  Log this", use_container_width=True):
        st.session_state["logged_event"] = {
            "sub_type": selected_context, "quantity": log_qty, "hour": log_hour}
        meta = CONTEXT_META[selected_context]
        st.success(f"{meta['icon']} {meta['label']} logged at {log_hour}:00")
    st.divider()
    st.caption("Nexus Prototype · v0.2")

# ── Data load ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_data():
    bio_df, source = load_biometrics(days=90)
    _, ctx_df = generate(days=90)
    return bio_df, ctx_df, source

bio_df, ctx_df, data_source = get_data()

if "logged_event" in st.session_state:
    ev = st.session_state["logged_event"]
    now = datetime.now(timezone.utc)
    ctx_df = pd.concat([ctx_df, pd.DataFrame([{
        "category":"INGESTION","sub_type":ev["sub_type"],"quantity":ev["quantity"],
        "impact_start":now.replace(hour=ev["hour"],minute=0),"tags":[],"date":now.date()
    }])], ignore_index=True)

today     = bio_df["recorded_at"].max()
cutoff_30 = today - timedelta(days=30)

def metric_stats(mk):
    df    = bio_df[bio_df["metric_type"]==mk].sort_values("recorded_at")
    last  = float(df.iloc[-1]["value"]) if len(df) else None
    s30   = df[df["recorded_at"]>=cutoff_30]
    avg30 = float(s30["value"].mean()) if len(s30) else None
    return last, avg30, s30

# ── Quick CCF for impact factors ───────────────────────────────────────────────
def quick_ccf(sub_type, primary_metric="HRV"):
    bio = bio_df[bio_df["metric_type"]==primary_metric].sort_values("recorded_at")
    bio = bio[bio["recorded_at"]>=cutoff_30]
    if len(bio) < 10: return 0.0, 0.0
    iw     = ImpactWindow.from_registry(sub_type)
    lags_h = np.arange(0, iw.window_hours+1, 1.0)
    bio_ts = bio["recorded_at"].tolist()
    bio_v  = bio["value"].to_numpy(float)
    events = [{"timestamp":r["impact_start"],"quantity":r["quantity"]}
               for _,r in ctx_df[ctx_df["sub_type"]==sub_type].iterrows()]
    if not events: return 0.0, 0.0
    best_r, best_lag = 0.0, 0.0
    for lag in lags_h:
        shifted = [{"timestamp":e["timestamp"]-timedelta(hours=float(lag)),
                    "quantity":e["quantity"]} for e in events]
        sig  = compute_weighted_signal(sub_type, shifted, bio_ts)
        mask = sig > 0
        if mask.sum() < 6: continue
        corr = np.corrcoef(sig[mask], bio_v[mask])[0,1]
        if np.isfinite(corr) and abs(corr) > abs(best_r):
            best_r, best_lag = float(corr), float(lag)
    return best_r, best_lag

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
badge = ('<span class="badge-live">● LIVE</span>' if data_source=="whoop_live"
         else '<span class="badge-demo">◉ DEMO</span>')
try:
    day_str = today.strftime("%A, %B %-d")
except:
    day_str = "Today"

st.markdown(f"""
<div style='margin-bottom:6px'>
    <span style='font-size:1.9rem;font-weight:700;letter-spacing:-0.03em'>Good morning</span>
    &nbsp;&nbsp;{badge}
</div>
<p style='color:#4b5563;font-size:0.88rem;margin-top:0;margin-bottom:28px'>
    {day_str} · Here's how your body is tracking
</p>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — 30-DAY BASELINE + TODAY VS AVG HERO CARDS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="sec-label">Your vitals today vs 30-day baseline</p>', unsafe_allow_html=True)

hero_cols = st.columns(4, gap="medium")
for col, mk in zip(hero_cols, list(METRICS.keys())):
    cfg          = METRICS[mk]
    last, avg30, s30 = metric_stats(mk)
    color        = cfg["color"]

    if last is None or avg30 is None:
        col.markdown(f'<div class="metric-hero"><div class="metric-hero-label">{cfg["label"]}</div><p style="color:#374151">No data yet</p></div>', unsafe_allow_html=True)
        continue

    delta   = last - avg30
    pct     = (delta / avg30 * 100) if avg30 else 0
    hib     = cfg["higher_is_better"]
    sign    = "+" if delta >= 0 else ""
    arr     = "↑" if delta >= 0 else "↓"

    if hib is None:
        chip_cls = "chip-flat"; chip_txt = f"↔ {sign}{delta:.1f} {cfg['unit']}"
    elif (delta >= 0 and hib) or (delta < 0 and not hib):
        chip_cls = "chip-good"; chip_txt = f"{arr} {sign}{delta:.1f} {cfg['unit']} · {sign}{pct:.0f}%"
    else:
        chip_cls = "chip-bad";  chip_txt = f"{arr} {sign}{delta:.1f} {cfg['unit']} · {sign}{pct:.0f}%"

    col.markdown(f"""
    <div class="metric-hero">
        <div class="metric-hero-glow" style="background:{color}"></div>
        <div class="metric-hero-label">{cfg['label']}</div>
        <div class="metric-hero-value" style="color:{color}">{last:.1f}<span class="metric-hero-unit">{cfg['unit']}</span></div>
        <div class="metric-hero-avg">30-day avg &nbsp;<b>{avg30:.1f} {cfg['unit']}</b></div>
        <span class="delta-chip {chip_cls}">{chip_txt}</span>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — TREND SPARKLINES (30 days, avg band)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="sec-label">30-day trends</p>', unsafe_allow_html=True)

spark_cols = st.columns(4, gap="medium")
for col, mk in zip(spark_cols, list(METRICS.keys())):
    cfg = METRICS[mk]
    last, avg30, s30 = metric_stats(mk)
    if s30.empty or avg30 is None:
        continue

    fig = go.Figure()

    # Avg band (±3%)
    fig.add_hrect(y0=avg30*0.97, y1=avg30*1.03,
        fillcolor=hex_to_rgba(cfg["color"], 0.06), line_width=0)

    # Avg line
    fig.add_hline(y=avg30, line_color=hex_to_rgba(cfg["color"], 0.35),
        line_width=1, line_dash="dot")

    # Trend fill + line
    fig.add_trace(go.Scatter(
        x=s30["recorded_at"], y=s30["value"],
        mode="lines",
        line=dict(color=cfg["color"], width=1.8),
        fill="tozeroy",
        fillcolor=hex_to_rgba(cfg["color"], 0.05),
    ))

    # Today dot
    last_row = s30.iloc[-1]
    fig.add_trace(go.Scatter(
        x=[last_row["recorded_at"]], y=[last_row["value"]],
        mode="markers",
        marker=dict(color=cfg["color"], size=9,
                    line=dict(color="#111318", width=2)),
    ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0,r=0,t=4,b=0), height=90,
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=True, gridcolor="#1a1d26",
                   tickfont=dict(size=9, color="#374151"),
                   tickformat=".0f"),
    )
    col.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})

st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — WHAT'S AFFECTING YOU (visual impact cards)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="sec-label">What\'s been shaping your recovery</p>', unsafe_allow_html=True)

_, avg30_hrv, _ = metric_stats("HRV")

impact_data = []
for sub, meta in CONTEXT_META.items():
    r, lag = quick_ccf(sub, "HRV")
    if abs(r) < 0.08:
        continue
    direction   = "lowers" if r < 0 else "boosts"
    lag_txt     = f"effect shows up ~{lag:.0f}h later" if lag > 0.5 else "effect is immediate"
    strength    = "Strong influence" if abs(r)>0.45 else ("Moderate influence" if abs(r)>0.25 else "Mild influence")
    tag_cls     = "tag-neg" if r < 0 else "tag-pos"
    est_effect  = r * (avg30_hrv or 50) * 0.5
    effect_txt  = f"{est_effect:+.1f} ms on avg"
    impact_data.append((abs(r), meta, direction, lag_txt, strength, tag_cls, effect_txt, r))

impact_data.sort(reverse=True, key=lambda x: x[0])

if impact_data:
    n = min(len(impact_data), 3)
    imp_cols = st.columns(n, gap="medium")
    for i, (_, meta, direction, lag_txt, strength, tag_cls, effect_txt, r) in enumerate(impact_data[:n]):
        with imp_cols[i]:
            # Mini bar showing correlation strength
            bar_pct = int(abs(r) * 100)
            bar_color = meta["color"]
            st.markdown(f"""
            <div class="impact-wrap">
                <div class="impact-top">
                    <div class="impact-icon-wrap" style="background:{meta['bg']}">
                        {meta['icon']}
                    </div>
                    <div>
                        <div class="impact-name">{meta['label']}</div>
                        <div class="impact-sub">{strength}</div>
                    </div>
                </div>
                <div class="impact-body">
                    {meta['label']} <b style="color:{bar_color}">{direction}</b> your Recovery Score.
                    {lag_txt.capitalize()}.
                </div>
                <div style="background:#1a1d26;border-radius:6px;height:6px;margin-bottom:10px;overflow:hidden">
                    <div style="background:{bar_color};width:{bar_pct}%;height:100%;border-radius:6px;opacity:0.8"></div>
                </div>
                <span class="tag {tag_cls}">{strength}</span>
                <span class="tag tag-neu">{effect_txt}</span>
            </div>
            """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div style='background:#111318;border:1px solid #1e2130;border-radius:16px;padding:28px 24px;text-align:center'>
        <p style='font-size:1.5rem;margin:0 0 8px'>📋</p>
        <p style='color:#6b7280;font-size:0.88rem;margin:0'>
            Log your habits for a few days and patterns will appear here automatically.
        </p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — DETAILED METRIC TABS (clean, no jargon)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="sec-label">Deep dive</p>', unsafe_allow_html=True)

tab_labels = ["💜  Recovery", "❤️  Heart Rate", "💚  Sleep", "🟡  Body Temp"]
tabs = st.tabs(tab_labels)

for tab, mk in zip(tabs, list(METRICS.keys())):
    cfg = METRICS[mk]
    last, avg30, s30 = metric_stats(mk)
    with tab:
        if s30.empty or avg30 is None:
            st.write("No data available yet.")
            continue

        # Context overlay — pick most impactful context for this tab
        ctx_overlay = ctx_df.copy()

        fig = go.Figure()

        # Avg band
        fig.add_hrect(
            y0=avg30*0.97, y1=avg30*1.03,
            fillcolor=hex_to_rgba(cfg["color"], 0.06), line_width=0,
            annotation_text="30-day avg ±3%",
            annotation_position="top left",
            annotation_font=dict(size=10, color="#374151")
        )
        fig.add_hline(y=avg30,
            line_color=hex_to_rgba(cfg["color"], 0.4),
            line_width=1, line_dash="dot")

        # Main metric line
        fig.add_trace(go.Scatter(
            x=s30["recorded_at"], y=s30["value"],
            mode="lines+markers",
            line=dict(color=cfg["color"], width=2),
            marker=dict(size=5, color=cfg["color"],
                        line=dict(color="#111318", width=1.5)),
            fill="tozeroy",
            fillcolor=hex_to_rgba(cfg["color"], 0.06),
            name=cfg["label"],
            hovertemplate=f"<b>%{{y:.1f}} {cfg['unit']}</b><br>%{{x|%b %d}}<extra></extra>",
        ))

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(gridcolor="#1a1d26",
                       title=f"{cfg['label']} ({cfg['unit']})",
                       titlefont=dict(size=11, color="#4b5563")),
            xaxis=dict(gridcolor="#1a1d26"),
            margin=dict(l=0, r=0, t=20, b=0),
            height=300,
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})

        # Stat row below chart
        s_col1, s_col2, s_col3, s_col4 = st.columns(4)
        s_col1.metric("Today",    f"{last:.1f} {cfg['unit']}")
        s_col2.metric("30-day avg", f"{avg30:.1f} {cfg['unit']}")
        s_col3.metric("30-day high", f"{s30['value'].max():.1f} {cfg['unit']}")
        s_col4.metric("30-day low",  f"{s30['value'].min():.1f} {cfg['unit']}")

st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
st.markdown(
    f'<p style="color:#1f2937;font-size:0.7rem;text-align:center">'
    f'Nexus · {"Live Whoop data" if data_source=="whoop_live" else "Demo mode — connect Whoop in sidebar to see your real data"}'
    f'</p>', unsafe_allow_html=True)
