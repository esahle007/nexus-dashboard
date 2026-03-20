"""
food_logger.py — Project Nexus Food Vision Module
==================================================
Captures food photos, sends to Claude Vision API for analysis,
stores results in Supabase food_log table, and exposes the
food log as a DataFrame for the correlation engine.

Dependencies: anthropic, supabase-py, Pillow (already in requirements)
"""

from __future__ import annotations
import base64, json, os
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

# ── Vision analysis ────────────────────────────────────────────────────────────

FOOD_ANALYSIS_PROMPT = """
You are a nutrition analyst. Analyze this food photo and return ONLY a JSON object
with no extra text, markdown, or explanation. Use this exact structure:

{
  "meal_type": "breakfast|lunch|dinner|snack",
  "foods": [
    {
      "name": "food item name",
      "portion": "estimated portion e.g. 1 cup, 200g, 1 medium",
      "calories": estimated_integer,
      "protein_g": estimated_float,
      "carbs_g": estimated_float,
      "fat_g": estimated_float,
      "sugar_g": estimated_float,
      "fiber_g": estimated_float
    }
  ],
  "total_calories": integer,
  "total_protein_g": float,
  "total_carbs_g": float,
  "total_fat_g": float,
  "confidence": "high|medium|low",
  "notes": "brief note about the meal e.g. high-carb breakfast, balanced plate"
}

Be realistic with estimates. If you cannot identify something, use your best guess
and set confidence to low. Always return valid JSON.
"""

def analyze_food_image(image_bytes: bytes, api_key: str) -> dict:
    """
    Send image to Claude Vision and return structured food analysis.
    Falls back to mock data if API call fails.
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": FOOD_ANALYSIS_PROMPT}
                ],
            }]
        )

        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    except Exception as e:
        # Return mock data but preserve full error for display
        result = _mock_analysis(str(e))
        result["_error"] = str(e)
        return result


def _mock_analysis(error_note: str = "") -> dict:
    """Mock response for development / when API key is not yet set."""
    return {
        "meal_type": "lunch",
        "foods": [
            {"name": "Grilled chicken breast", "portion": "150g",
             "calories": 248, "protein_g": 46.5, "carbs_g": 0.0,
             "fat_g": 5.4, "sugar_g": 0.0, "fiber_g": 0.0},
            {"name": "Mixed salad", "portion": "2 cups",
             "calories": 35, "protein_g": 2.5, "carbs_g": 6.0,
             "fat_g": 0.5, "sugar_g": 3.0, "fiber_g": 2.5},
            {"name": "Olive oil dressing", "portion": "1 tbsp",
             "calories": 119, "protein_g": 0.0, "carbs_g": 0.0,
             "fat_g": 13.5, "sugar_g": 0.0, "fiber_g": 0.0},
        ],
        "total_calories": 402,
        "total_protein_g": 49.0,
        "total_carbs_g": 6.0,
        "total_fat_g": 19.4,
        "confidence": "high",
        "notes": f"Demo data — set ANTHROPIC_API_KEY to enable real analysis. {error_note}".strip()
    }


# ── Supabase storage ───────────────────────────────────────────────────────────

SUPABASE_SCHEMA = """
-- Run this once in Supabase SQL Editor
CREATE TABLE IF NOT EXISTS food_log (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       TEXT        NOT NULL DEFAULT 'default_user',
    logged_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    meal_type     TEXT        NOT NULL,
    foods_json    JSONB       NOT NULL,
    total_calories  FLOAT,
    total_protein_g FLOAT,
    total_carbs_g   FLOAT,
    total_fat_g     FLOAT,
    total_sugar_g   FLOAT,
    total_fiber_g   FLOAT,
    confidence    TEXT,
    notes         TEXT,
    image_url     TEXT
);
CREATE INDEX IF NOT EXISTS idx_food_log_time ON food_log (logged_at DESC);
"""


def get_supabase_client():
    """Return a Supabase client using Streamlit secrets or env vars."""
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_ANON_KEY", "")
    except Exception:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_ANON_KEY", "")

    if not url or not key:
        return None

    from supabase import create_client
    return create_client(url, key)


def save_food_log(analysis: dict, logged_at: datetime | None = None) -> bool:
    """
    Persist a food analysis result to Supabase.
    Returns True on success, False on failure (graceful degradation).
    """
    client = get_supabase_client()
    if client is None:
        return False  # No Supabase configured — silently skip

    ts = (logged_at or datetime.now(timezone.utc)).isoformat()

    # Sum sugar/fiber across all food items
    foods = analysis.get("foods", [])
    total_sugar = sum(f.get("sugar_g", 0) for f in foods)
    total_fiber = sum(f.get("fiber_g", 0) for f in foods)

    row = {
        "logged_at":      ts,
        "meal_type":      analysis.get("meal_type", "unknown"),
        "foods_json":     json.dumps(foods),
        "total_calories": analysis.get("total_calories"),
        "total_protein_g":analysis.get("total_protein_g"),
        "total_carbs_g":  analysis.get("total_carbs_g"),
        "total_fat_g":    analysis.get("total_fat_g"),
        "total_sugar_g":  total_sugar,
        "total_fiber_g":  total_fiber,
        "confidence":     analysis.get("confidence"),
        "notes":          analysis.get("notes"),
    }

    try:
        client.table("food_log").insert(row).execute()
        return True
    except Exception:
        return False


def load_food_log(days: int = 30) -> "pd.DataFrame":
    """
    Load food log from Supabase for the past N days.
    Falls back to synthetic demo data if Supabase is not configured.
    """
    import pandas as pd
    from datetime import timedelta

    client = get_supabase_client()

    if client:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            resp = (client.table("food_log")
                    .select("*")
                    .gte("logged_at", cutoff)
                    .order("logged_at", desc=False)
                    .execute())
            if resp.data:
                df = pd.DataFrame(resp.data)
                df["logged_at"] = pd.to_datetime(df["logged_at"], utc=True)
                return df
        except Exception:
            pass

    # Fallback: synthetic demo food data
    return _synthetic_food_log(days=days)


def _synthetic_food_log(days: int = 30) -> "pd.DataFrame":
    """Generate realistic synthetic food log for demo purposes."""
    import numpy as np
    import pandas as pd
    from datetime import timedelta

    rng = np.random.default_rng(42)
    base = datetime.now(timezone.utc)
    rows = []

    meal_templates = [
        {"meal_type":"breakfast","total_calories":380,"total_protein_g":22,"total_carbs_g":48,"total_fat_g":10,"notes":"Oatmeal with berries"},
        {"meal_type":"breakfast","total_calories":520,"total_protein_g":28,"total_carbs_g":35,"total_fat_g":22,"notes":"Eggs and avocado toast"},
        {"meal_type":"lunch",    "total_calories":620,"total_protein_g":42,"total_carbs_g":55,"total_fat_g":18,"notes":"Chicken salad bowl"},
        {"meal_type":"lunch",    "total_calories":780,"total_protein_g":32,"total_carbs_g":95,"total_fat_g":24,"notes":"Pasta with tomato sauce"},
        {"meal_type":"dinner",   "total_calories":740,"total_protein_g":52,"total_carbs_g":45,"total_fat_g":28,"notes":"Salmon with vegetables"},
        {"meal_type":"dinner",   "total_calories":890,"total_protein_g":45,"total_carbs_g":85,"total_fat_g":32,"notes":"Steak with fries"},
        {"meal_type":"snack",    "total_calories":180,"total_protein_g":8, "total_carbs_g":22,"total_fat_g":6, "notes":"Greek yogurt"},
        {"meal_type":"snack",    "total_calories":240,"total_protein_g":4, "total_carbs_g":38,"total_fat_g":9, "notes":"Mixed nuts and fruit"},
    ]

    for d in range(days):
        day = base - timedelta(days=days-d-1)
        n_meals = rng.integers(3, 5)
        chosen = rng.choice(meal_templates, n_meals, replace=False)
        for meal in chosen:
            hour = {"breakfast":7,"lunch":12,"dinner":19,"snack":15}[meal["meal_type"]]
            ts = day.replace(hour=hour, minute=int(rng.integers(0,30)))
            row = {**meal}
            row["logged_at"] = ts
            row["total_sugar_g"] = float(rng.uniform(8, 24))
            row["total_fiber_g"] = float(rng.uniform(3, 12))
            row["confidence"] = "high"
            row["foods_json"] = "[]"
            rows.append(row)

    df = pd.DataFrame(rows)
    df["logged_at"] = pd.to_datetime(df["logged_at"], utc=True)
    return df.sort_values("logged_at").reset_index(drop=True)


def get_api_key() -> str:
    """Retrieve Anthropic API key from Streamlit secrets or env."""
    try:
        import streamlit as st
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return os.getenv("ANTHROPIC_API_KEY", "")
