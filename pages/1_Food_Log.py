"""
page_food.py — Food Logging Page for Project Nexus
===================================================
Streamlit page: camera capture → Claude Vision → food database → charts.
Add to your repo and it appears automatically as a sidebar page.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta
from PIL import Image
from io import BytesIO

import food_logger as fl

st.set_page_config(page_title="Food Log · Nexus", page_icon="🍽️",
                   layout="wide", initial_sidebar_state="expanded")

# ── Styles (match main dashboard) ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

.food-card {
    background: #111318; border: 1px solid #1e2130;
    border-radius: 16px; padding: 20px 18px; margin-bottom: 12px;
}
.meal-badge {
    display: inline-block; padding: 3px 10px; border-radius: 20px;
    font-size: 0.7rem; font-weight: 700; letter-spacing: 0.06em;
    text-transform: uppercase; margin-bottom: 10px;
}
.badge-breakfast { background: rgba(251,191,36,0.15); color: #fbbf24; }
.badge-lunch     { background: rgba(52,211,153,0.15); color: #34d399; }
.badge-dinner    { background: rgba(129,140,248,0.15);color: #818cf8; }
.badge-snack     { background: rgba(251,113,133,0.15);color: #fb7185; }

.food-item-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 0; border-bottom: 1px solid #1e2130; font-size: 0.85rem;
}
.food-item-row:last-child { border-bottom: none; }
.macro-chip {
    display: inline-block; padding: 2px 8px; border-radius: 6px;
    font-size: 0.7rem; font-weight: 600; margin-left: 6px;
}
.chip-cal  { background: rgba(251,191,36,0.12); color: #fbbf24; }
.chip-pro  { background: rgba(52,211,153,0.12); color: #34d399; }
.chip-carb { background: rgba(129,140,248,0.12);color: #818cf8; }
.chip-fat  { background: rgba(251,113,133,0.12);color: #fb7185; }

.sec-label {
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.14em;
    text-transform: uppercase; color: #374151; margin: 0 0 16px;
}
.conf-high { color: #34d399; } .conf-medium { color: #fbbf24; } .conf-low { color: #fb7185; }
</style>
""", unsafe_allow_html=True)

def hex_to_rgba(h, a=0.15):
    h = h.lstrip("#")
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f"rgba({r},{g},{b},{a})"

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🍽️ Food Log")
    st.caption("Camera → AI → database")
    st.divider()
    api_key = fl.get_api_key()
    if api_key:
        st.success("✓ Vision API connected")
    else:
        st.warning("⚠ No API key — demo mode")
        st.caption("Add ANTHROPIC_API_KEY to Streamlit secrets to enable real food analysis.")

    supabase = fl.get_supabase_client()
    if supabase:
        st.success("✓ Supabase connected")
    else:
        st.warning("⚠ No Supabase — data won't persist")
        st.caption("Add SUPABASE_URL and SUPABASE_ANON_KEY to Streamlit secrets.")
    st.divider()
    days_back = st.slider("History window", 7, 30, 14, format="%d days")
    st.page_link("app.py", label="← Back to dashboard")

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("# 🍽️ Food log")
st.markdown("<p style='color:#4b5563;font-size:0.88rem;margin-top:-8px;margin-bottom:24px'>"
            "Take a photo of your meal — AI identifies what's on the plate</p>",
            unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — CAPTURE
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="sec-label">Log a meal</p>', unsafe_allow_html=True)

cap_col, result_col = st.columns([1, 1], gap="large")

with cap_col:
    input_mode = st.radio("Input method", ["📷  Camera", "📁  Upload photo"],
                           horizontal=True, label_visibility="collapsed")

    img_bytes = None
    if "Camera" in input_mode:
        camera_img = st.camera_input("Point at your food and capture",
                                      label_visibility="collapsed")
        if camera_img:
            img_bytes = camera_img.getvalue()
    else:
        uploaded = st.file_uploader("Upload a food photo",
                                     type=["jpg","jpeg","png","webp"],
                                     label_visibility="collapsed")
        if uploaded:
            img_bytes = uploaded.read()

    meal_time_override = st.time_input("Meal time", value=datetime.now().time())

    analyze_btn = st.button("🔍  Analyze this meal",
                             use_container_width=True,
                             disabled=(img_bytes is None))

with result_col:
    if img_bytes and analyze_btn:
        with st.spinner("Analyzing your meal..."):
            analysis = fl.analyze_food_image(img_bytes, api_key)

        st.session_state["last_analysis"] = analysis
        st.session_state["last_img"] = img_bytes

        # Save to DB
        now = datetime.now(timezone.utc)
        logged_at = now.replace(
            hour=meal_time_override.hour,
            minute=meal_time_override.minute,
            second=0, microsecond=0
        )
        saved = fl.save_food_log(analysis, logged_at=logged_at)
        if saved:
            st.success("Saved to your food log!")
        else:
            st.info("Analyzed! (Connect Supabase to persist across sessions)")

    if "last_analysis" in st.session_state:
        a = st.session_state["last_analysis"]
        conf = a.get("confidence","medium")
        badge_cls = f"badge-{a.get('meal_type','snack')}"
        conf_cls  = f"conf-{conf}"

        st.markdown(f"""
        <div class="food-card">
            <span class="meal-badge {badge_cls}">{a.get('meal_type','meal')}</span>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
                <span class="macro-chip chip-cal">🔥 {a.get('total_calories',0):.0f} kcal</span>
                <span class="macro-chip chip-pro">P {a.get('total_protein_g',0):.0f}g</span>
                <span class="macro-chip chip-carb">C {a.get('total_carbs_g',0):.0f}g</span>
                <span class="macro-chip chip-fat">F {a.get('total_fat_g',0):.0f}g</span>
            </div>
        """, unsafe_allow_html=True)

        for food in a.get("foods", []):
            st.markdown(f"""
            <div class="food-item-row">
                <span style="color:#e5e7eb">{food.get('name','?')}</span>
                <span style="color:#6b7280;font-size:0.78rem">{food.get('portion','')}</span>
                <span style="color:#9ca3af;font-size:0.78rem">{food.get('calories',0):.0f} kcal</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown(f"""
            <div style="margin-top:12px;font-size:0.78rem;color:#6b7280">
                {a.get('notes','')}
                &nbsp;·&nbsp; Confidence: <span class="{conf_cls}">{conf}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    elif img_bytes is None:
        st.markdown("""
        <div style="background:#111318;border:1px solid #1e2130;border-radius:16px;
             padding:40px 24px;text-align:center;margin-top:8px">
            <p style="font-size:2rem;margin:0 0 8px">📸</p>
            <p style="color:#6b7280;font-size:0.88rem;margin:0">
                Take a photo or upload an image to get started
            </p>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — NUTRITION OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="sec-label">Nutrition overview</p>', unsafe_allow_html=True)

@st.cache_data(ttl=120)
def get_food_data(days):
    return fl.load_food_log(days=days)

food_df = get_food_data(days_back)

if food_df.empty:
    st.info("No food logs yet. Capture your first meal above.")
else:
    # Daily totals
    food_df["date"] = food_df["logged_at"].dt.date
    daily = food_df.groupby("date").agg(
        calories=("total_calories","sum"),
        protein=("total_protein_g","sum"),
        carbs=("total_carbs_g","sum"),
        fat=("total_fat_g","sum"),
    ).reset_index()

    # KPI row
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Avg daily calories",  f"{daily['calories'].mean():.0f} kcal")
    k2.metric("Avg daily protein",   f"{daily['protein'].mean():.0f} g")
    k3.metric("Avg daily carbs",     f"{daily['carbs'].mean():.0f} g")
    k4.metric("Avg daily fat",       f"{daily['fat'].mean():.0f} g")

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Calorie trend + macro stacked bar
    chart_l, chart_r = st.columns([3, 2], gap="large")

    with chart_l:
        st.markdown("##### Daily calories")
        fig = go.Figure()
        avg_cal = daily["calories"].mean()
        fig.add_hline(y=avg_cal,
            line_dash="dot", line_color="rgba(251,191,36,0.4)", line_width=1)
        fig.add_trace(go.Bar(
            x=daily["date"], y=daily["calories"],
            marker_color="#fbbf24", opacity=0.8, name="Calories",
        ))
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(gridcolor="#1a1d26"),
            yaxis=dict(gridcolor="#1a1d26", title="kcal"),
            margin=dict(l=0,r=0,t=8,b=0), height=240,
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})

    with chart_r:
        st.markdown("##### Macro split (avg)")
        avg_p = daily["protein"].mean()
        avg_c = daily["carbs"].mean()
        avg_f = daily["fat"].mean()
        total_g = avg_p + avg_c + avg_f

        fig2 = go.Figure(go.Pie(
            labels=["Protein", "Carbs", "Fat"],
            values=[avg_p, avg_c, avg_f],
            hole=0.55,
            marker_colors=["#34d399","#818cf8","#fb7185"],
            textinfo="percent",
            textfont=dict(size=12, color="#e5e7eb"),
        ))
        fig2.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0,r=0,t=8,b=0), height=240,
            showlegend=True,
            legend=dict(orientation="v", font=dict(size=11, color="#9ca3af"),
                        yanchor="middle", y=0.5, x=1.05),
            annotations=[dict(text=f"{total_g:.0f}g<br>total",
                              x=0.5, y=0.5, font_size=12,
                              font_color="#9ca3af", showarrow=False)]
        )
        st.plotly_chart(fig2, use_container_width=True,
                        config={"displayModeBar": False})

    st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)

    # ── Meal type breakdown ───────────────────────────────────────────────────
    st.markdown('<p class="sec-label">Meals this period</p>', unsafe_allow_html=True)

    meal_colors = {"breakfast":"#fbbf24","lunch":"#34d399",
                   "dinner":"#818cf8","snack":"#fb7185"}

    for _, row in food_df.sort_values("logged_at", ascending=False).head(10).iterrows():
        meal = row.get("meal_type","snack")
        badge_cls = f"badge-{meal}"
        ts_str = row["logged_at"].strftime("%-I:%M %p · %b %-d")
        cal = row.get("total_calories", 0) or 0
        pro = row.get("total_protein_g", 0) or 0
        carb = row.get("total_carbs_g", 0) or 0
        fat = row.get("total_fat_g", 0) or 0
        notes = row.get("notes","") or ""

        st.markdown(f"""
        <div class="food-card" style="margin-bottom:8px">
            <div style="display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <span class="meal-badge {badge_cls}">{meal}</span>
                    <span style="color:#6b7280;font-size:0.78rem;margin-left:8px">{ts_str}</span>
                </div>
                <div>
                    <span class="macro-chip chip-cal">{cal:.0f} kcal</span>
                </div>
            </div>
            <div style="display:flex;gap:6px;margin-top:6px">
                <span class="macro-chip chip-pro">P {pro:.0f}g</span>
                <span class="macro-chip chip-carb">C {carb:.0f}g</span>
                <span class="macro-chip chip-fat">F {fat:.0f}g</span>
            </div>
            {f'<div style="color:#6b7280;font-size:0.78rem;margin-top:8px">{notes}</div>' if notes else ''}
        </div>
        """, unsafe_allow_html=True)

st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
st.markdown(
    '<p style="color:#1f2937;font-size:0.7rem;text-align:center">'
    'Nexus · Food log · Powered by Claude Vision</p>',
    unsafe_allow_html=True)

