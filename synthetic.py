"""
data/synthetic.py
=================
Generates 90 days of realistic synthetic data for Nexus prototype.

Biometrics follow plausible human patterns with injected correlations:
  - Late caffeine  → suppressed HRV next morning  (lag ~8h)
  - Alcohol        → elevated RHR next day         (lag ~6h)
  - Social conflict→ poor mood score same evening  (lag ~2h)
  - Morning light  → better deep sleep that night  (lag ~14h)
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone

RNG = np.random.default_rng(42)

def generate(days: int = 90) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (biometrics_df, context_df)."""
    base = datetime(2024, 10, 1, tzinfo=timezone.utc)
    dates = [base + timedelta(days=i) for i in range(days)]

    # ── Context events (human inputs) ──────────────────────────────
    rows_ctx = []

    for d in dates:
        # Caffeine — 1-3 coffees per day, mostly morning, sometimes late
        n_coffees = RNG.integers(1, 4)
        for _ in range(n_coffees):
            hour = RNG.choice([7, 8, 9, 10, 13, 15, 17], p=[0.2,0.25,0.2,0.1,0.1,0.1,0.05])
            rows_ctx.append({
                "category":     "INGESTION",
                "sub_type":     "caffeine",
                "quantity":     RNG.uniform(0.8, 1.5),   # normalised dose
                "impact_start": d.replace(hour=int(hour), minute=RNG.integers(0,60)),
                "tags":         ["coffee"],
            })

        # Alcohol — ~3x/week, evenings
        if RNG.random() < 0.43:
            drinks = RNG.integers(1, 4)
            rows_ctx.append({
                "category":     "INGESTION",
                "sub_type":     "alcohol",
                "quantity":     float(drinks),
                "impact_start": d.replace(hour=RNG.integers(19, 23), minute=RNG.integers(0,60)),
                "tags":         ["drinks"],
            })

        # Social conflict — ~1.5x/week
        if RNG.random() < 0.21:
            rows_ctx.append({
                "category":     "SOCIAL",
                "sub_type":     "social_conflict",
                "quantity":     RNG.uniform(0.3, 1.0),
                "impact_start": d.replace(hour=RNG.integers(14, 20), minute=RNG.integers(0,60)),
                "tags":         ["stress", "conflict"],
            })

        # Blue light — screen use before bed, most nights
        if RNG.random() < 0.75:
            rows_ctx.append({
                "category":     "ENVIRONMENT",
                "sub_type":     "blue_light",
                "quantity":     RNG.uniform(0.5, 1.0),
                "impact_start": d.replace(hour=RNG.integers(21, 24), minute=RNG.integers(0,60)),
                "tags":         ["screen", "phone"],
            })

        # Morning light — ~60% of days
        if RNG.random() < 0.60:
            rows_ctx.append({
                "category":     "ENVIRONMENT",
                "sub_type":     "morning_light",
                "quantity":     RNG.uniform(0.6, 1.0),
                "impact_start": d.replace(hour=RNG.integers(6, 9), minute=RNG.integers(0,30)),
                "tags":         ["sunlight", "outdoors"],
            })

    ctx_df = pd.DataFrame(rows_ctx)
    ctx_df["impact_start"] = pd.to_datetime(ctx_df["impact_start"], utc=True)

    # ── Biometrics — inject true correlations ──────────────────────
    # Baseline trends
    hrv_base      = 52.0 + RNG.normal(0, 1, days)        # ms
    rhr_base      = 58.0 + RNG.normal(0, 0.5, days)      # bpm
    deep_base     = 85.0 + RNG.normal(0, 5, days)        # minutes
    temp_base     = 36.6 + RNG.normal(0, 0.05, days)     # °C

    # Compute daily context loads (simple sum of quantities per day)
    ctx_df["date"] = ctx_df["impact_start"].dt.date

    def daily_load(sub: str) -> np.ndarray:
        mask = ctx_df["sub_type"] == sub
        daily = ctx_df[mask].groupby("date")["quantity"].sum()
        return np.array([daily.get(d.date(), 0.0) for d in dates])

    caff_load     = daily_load("caffeine")
    alc_load      = daily_load("alcohol")
    conflict_load = daily_load("social_conflict")
    light_load    = daily_load("morning_light")

    # Lagged effects (shift arrays to inject real lags)
    def lag(arr, n=1):
        out = np.zeros_like(arr)
        out[n:] = arr[:-n]
        return out

    # HRV: suppressed by caffeine (lag 1 day ~8-10h overnight) and alcohol
    hrv = hrv_base - 3.5 * lag(caff_load) - 5.0 * lag(alc_load) + 2.0 * lag(light_load)

    # RHR: elevated by alcohol night-before, slightly by conflict
    rhr = rhr_base + 2.8 * lag(alc_load) + 0.8 * lag(conflict_load)

    # Deep sleep: hurt by blue light same night, helped by morning light
    blue_load = daily_load("blue_light")
    deep = deep_base - 12.0 * blue_load + 8.0 * light_load

    # Temp shift: subtle — elevated by alcohol
    temp = temp_base + 0.08 * lag(alc_load) + RNG.normal(0, 0.02, days)

    rows_bio = []
    for i, d in enumerate(dates):
        sleep_end = d.replace(hour=7, minute=RNG.integers(0, 60))
        rows_bio += [
            {"source": "WHOOP", "metric_type": "HRV",        "value": round(float(max(20, hrv[i] + RNG.normal(0,2))), 1),  "recorded_at": sleep_end},
            {"source": "WHOOP", "metric_type": "RHR",        "value": round(float(max(40, rhr[i] + RNG.normal(0,1))), 1),  "recorded_at": sleep_end},
            {"source": "WHOOP", "metric_type": "DEEP_SLEEP",  "value": round(float(max(10, deep[i] + RNG.normal(0,5))), 1), "recorded_at": sleep_end},
            {"source": "OURA",  "metric_type": "TEMP_SHIFT",  "value": round(float(temp[i]), 3),                            "recorded_at": sleep_end},
        ]

    bio_df = pd.DataFrame(rows_bio)
    bio_df["recorded_at"] = pd.to_datetime(bio_df["recorded_at"], utc=True)
    return bio_df, ctx_df
