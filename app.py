"""
app.py — Project Nexus Prototype Dashboard
Streamlit entry point. Run with: streamlit run app.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta, timezone

from data.synthetic import generate
from data.whoop_client import load_biometrics
from core.impact_windows import (
    IMPACT_WINDOW_REGISTRY, ImpactWindow, compute_weighted_signal
)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Project Nexus",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme tweaks ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 600; }
[data-testid="stMetricLabel"] { font-size: 0.78rem; letter-spacing: 0.04em; text-transform: uppercase; color: #888; }
.insight-card {
    background: #0e1117; border: 1px solid #1f2937;
    border-left: 3px solid #6366f1; border-radius: 8px;
    padding: 14px 18px; margin: 6px 0; font-size: 0.88rem; line-height: 1.6;
}
.data-badge {
    display:inline-block; padding: 2px 8px; border-radius: 12px;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.05em;
    background: #1a2744; color: #60a5fa;
}
.synth-badge {
    display:inline-block; padding: 2px 8px; border-radius: 12px;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.05em;
    background: #1e1a2e; color: #a78bfa;
}
</style>
""", unsafe_allow_html=True)

# ── Color palette ──────────────────────────────────────────────────────────────
METRIC_COLORS = {
    "HRV":        "#6366f1",
    "RHR":        "#f43f5e",
    "DEEP_SLEEP": "#10b981",
    "TEMP_SHIFT": "#f59e0b",
}
CONTEXT_COLORS = {
    "caffeine":       "#f59e0b",
    "alcohol":        "#f43f5e",
    "social_conflict":"#8b5cf6",
    "blue_light":     "#3b82f6",
    "morning_light":  "#10b981",
}

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — Controls
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("🧬 Project Nexus")
    st.caption("Lifestyle · Biometric Correlation Engine")
    st.divider()

    days_back = st.slider("Analysis window", 14, 90, 60, step=7, format="%d days")

    st.markdown("**Biometric metric**")
    selected_metric = st.radio(
        "", ["HRV", "RHR", "DEEP_SLEEP", "TEMP_SHIFT"],
        format_func=lambda x: {"HRV":"HRV (ms)", "RHR":"Resting HR (bpm)",
                               "DEEP_SLEEP":"Deep Sleep (min)", "TEMP_SHIFT":"Temp Shift (°C)"}[x],
        label_visibility="collapsed",
    )

    st.markdown("**Context input**")
    selected_context = st.radio(
        "", list(IMPACT_WINDOW_REGISTRY.keys()),
        format_func=lambda x: x.replace("_", " ").title(),
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown("**Log a context event**")
    log_qty = st.slider("Intensity / amount", 0.1, 3.0, 1.0, step=0.1)
    log_hour = st.slider("Hour of day", 0, 23, 8)
    if st.button("➕ Log today", use_container_width=True):
        st.session_state["logged_event"] = {
            "sub_type": selected_context,
            "quantity": log_qty,
            "hour":     log_hour,
        }
        st.success(f"Logged {selected_context.replace('_',' ')} @ {log_hour}:00")

# ══════════════════════════════════════════════════════════════════════════════
# DATA LOAD
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def get_data(days):
    bio_df, source = load_biometrics(days=days)
    _, ctx_df = generate(days=days)   # synthetic context always for prototype
    return bio_df, ctx_df, source

bio_df, ctx_df, data_source = get_data(days_back)

# Inject any manually logged event into context
if "logged_event" in st.session_state:
    ev = st.session_state["logged_event"]
    now = datetime.now(timezone.utc)
    new_row = pd.DataFrame([{
        "category":     "INGESTION",
        "sub_type":     ev["sub_type"],
        "quantity":     ev["quantity"],
        "impact_start": now.replace(hour=ev["hour"], minute=0),
        "tags":         [],
        "date":         now.date(),
    }])
    ctx_df = pd.concat([ctx_df, new_row], ignore_index=True)

# Filter to selected metric
bio_metric = bio_df[bio_df["metric_type"] == selected_metric].copy()
bio_metric = bio_metric.sort_values("recorded_at")

# Filter context to selected sub_type
ctx_sub = ctx_df[ctx_df["sub_type"] == selected_context].copy()

# ── CCF computation ────────────────────────────────────────────────────────────
def run_ccf(sub_type, ctx, bio, max_lag_h=None):
    iw = ImpactWindow.from_registry(sub_type)
    max_lag = max_lag_h or iw.window_hours
    lags_h  = np.arange(0, max_lag + 0.5, 0.5)
    r_vals  = []
    bio_ts  = bio["recorded_at"].tolist()
    bio_vals= bio["value"].to_numpy(float)
    events  = [{"timestamp": row["impact_start"], "quantity": row["quantity"]}
               for _, row in ctx.iterrows()]
    if not events or len(bio_ts) < 10:
        return lags_h, np.zeros(len(lags_h)), 0.0, 0.0

    from datetime import timedelta as td
    for lag in lags_h:
        shifted = [{"timestamp": e["timestamp"] - td(hours=float(lag)),
                    "quantity": e["quantity"]} for e in events]
        sig = compute_weighted_signal(sub_type, shifted, bio_ts)
        mask = sig > 0
        if mask.sum() < 8:
            r_vals.append(0.0)
            continue
        corr = np.corrcoef(sig[mask], bio_vals[mask])[0,1]
        r_vals.append(0.0 if not np.isfinite(corr) else corr)

    r_arr   = np.array(r_vals)
    best_idx= int(np.argmax(np.abs(r_arr)))
    return lags_h, r_arr, float(lags_h[best_idx]), float(r_arr[best_idx])

lags, r_vals, best_lag, best_r = run_ccf(selected_context, ctx_sub, bio_metric)

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
badge_html = (
    '<span class="data-badge">⚡ WHOOP LIVE</span>'
    if data_source == "whoop_live"
    else '<span class="synth-badge">◉ SYNTHETIC DATA</span>'
)
st.markdown(f"## Project Nexus &nbsp; {badge_html}", unsafe_allow_html=True)
st.caption(f"Last {days_back} days · {selected_metric} vs {selected_context.replace('_',' ').title()}")
st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# KPI CARDS
# ══════════════════════════════════════════════════════════════════════════════
col1, col2, col3, col4 = st.columns(4)
metric_vals = bio_metric["value"]
col1.metric("Mean " + selected_metric, f"{metric_vals.mean():.1f}")
col2.metric("Best correlation r", f"{best_r:+.2f}")
col3.metric("Optimal lag", f"{best_lag:.1f} h")
iw_spec = IMPACT_WINDOW_REGISTRY[selected_context]
col4.metric("Impact window", f"{iw_spec['window_hours']:.0f} h")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# INSIGHT CARD
# ══════════════════════════════════════════════════════════════════════════════
direction = "positively" if best_r > 0 else "negatively"
strength  = "strong" if abs(best_r) > 0.5 else ("moderate" if abs(best_r) > 0.3 else "weak")
n_obs     = int((run_ccf(selected_context, ctx_sub, bio_metric)[0] != 0).sum())

insight_text = (
    f"📊 &nbsp; Data shows <b>{selected_context.replace('_',' ')}</b> "
    f"<b>{direction}</b> correlates with <b>{selected_metric}</b> "
    f"with a lag of <b>{best_lag:.1f} hours</b> "
    f"(r = {best_r:+.2f}, {strength} correlation, n ≈ {len(bio_metric)} observations). "
    f"Decay model: <b>{iw_spec['decay_model']}</b> · "
    f"Peak impact at <b>{iw_spec['peak_lag_hours']:.2g}h</b> post-exposure."
)
st.markdown(f'<div class="insight-card">{insight_text}</div>', unsafe_allow_html=True)
st.markdown("")

# ══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════════════════════════════
left_col, right_col = st.columns([3, 2])

# ── Left: Biometric time-series with context overlay ──────────────────────────
with left_col:
    st.markdown(f"##### {selected_metric} over time")
    fig = go.Figure()

    # Biometric line
    fig.add_trace(go.Scatter(
        x=bio_metric["recorded_at"], y=bio_metric["value"],
        name=selected_metric,
        line=dict(color=METRIC_COLORS[selected_metric], width=2),
        mode="lines+markers", marker=dict(size=4),
    ))

    # Context event markers on secondary y-axis
    if not ctx_sub.empty:
        fig.add_trace(go.Bar(
            x=ctx_sub["impact_start"], y=ctx_sub["quantity"],
            name=selected_context.replace("_"," ").title(),
            marker_color=CONTEXT_COLORS.get(selected_context, "#888"),
            opacity=0.35, yaxis="y2",
        ))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(title=selected_metric, gridcolor="#1f2937"),
        yaxis2=dict(title="Context quantity", overlaying="y", side="right",
                    showgrid=False, range=[0, ctx_sub["quantity"].max()*4 if not ctx_sub.empty else 4]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=0, r=0, t=10, b=0), height=320,
        xaxis=dict(gridcolor="#1f2937"),
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Right: CCF lag chart ───────────────────────────────────────────────────────
with right_col:
    st.markdown("##### Cross-correlation by lag (CCF)")
    fig2 = go.Figure()

    bar_colors = [
        METRIC_COLORS[selected_metric] if abs(r) == max(abs(r_vals)) else "#374151"
        for r in r_vals
    ]
    fig2.add_trace(go.Bar(
        x=lags, y=r_vals,
        marker_color=bar_colors, name="Pearson r",
    ))
    fig2.add_hline(y=0, line_color="#4b5563", line_width=1)
    fig2.add_vline(x=best_lag, line_dash="dash",
                   line_color=METRIC_COLORS[selected_metric], opacity=0.6)
    fig2.add_annotation(
        x=best_lag, y=best_r, text=f" peak r={best_r:+.2f}",
        showarrow=False, font=dict(color=METRIC_COLORS[selected_metric], size=11),
        xanchor="left",
    )
    fig2.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="Lag (hours)", gridcolor="#1f2937"),
        yaxis=dict(title="r", range=[-1, 1], gridcolor="#1f2937"),
        margin=dict(l=0, r=0, t=10, b=0), height=320,
        showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# DECAY CURVE VISUALISER
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.markdown("##### Impact window decay model")
iw      = ImpactWindow.from_registry(selected_context)
t_range = np.linspace(0, iw.window_hours, 200)
weights = [iw.weight(t) for t in t_range]

fig3 = go.Figure()
fig3.add_trace(go.Scatter(
    x=t_range, y=weights,
    fill="tozeroy",
    fillcolor=CONTEXT_COLORS.get(selected_context, "#888") + "33",
    line=dict(color=CONTEXT_COLORS.get(selected_context, "#888"), width=2),
    name="Biological weight",
))
fig3.add_vline(
    x=iw.peak_lag_hours, line_dash="dot",
    annotation_text=f"Peak @ {iw.peak_lag_hours}h",
    line_color="#9ca3af",
)
fig3.update_layout(
    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(title="Hours since exposure", gridcolor="#1f2937"),
    yaxis=dict(title="Biological impact weight", range=[0, 1.05], gridcolor="#1f2937"),
    margin=dict(l=0, r=0, t=10, b=0), height=220,
    showlegend=False,
)
st.plotly_chart(fig3, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# ALL-INPUTS CORRELATION SUMMARY TABLE
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.markdown("##### All-inputs correlation summary")

summary_rows = []
for sub in IMPACT_WINDOW_REGISTRY:
    ctx_s = ctx_df[ctx_df["sub_type"] == sub]
    if ctx_s.empty:
        continue
    _, r_a, lag_a, r_best = run_ccf(sub, ctx_s, bio_metric)
    iw_info = IMPACT_WINDOW_REGISTRY[sub]
    summary_rows.append({
        "Context input":    sub.replace("_"," ").title(),
        "Best r":           round(r_best, 3),
        "Optimal lag (h)":  round(lag_a, 1),
        "Decay model":      iw_info["decay_model"],
        "Window (h)":       iw_info["window_hours"],
    })

if summary_rows:
    summary_df = pd.DataFrame(summary_rows).sort_values("Best r", key=abs, ascending=False)
    st.dataframe(
        summary_df.style.background_gradient(subset=["Best r"], cmap="RdYlGn", vmin=-1, vmax=1),
        use_container_width=True, hide_index=True,
    )

st.divider()
st.caption("Project Nexus · Prototype · Synthetic data · Switch to live Whoop data by adding credentials to Streamlit secrets.")
