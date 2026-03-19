"""
data/whoop_client.py
====================
Whoop API v1 integration for Project Nexus.

Requires WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET in .streamlit/secrets.toml
(or Streamlit Cloud secrets). Falls back to synthetic data if credentials
are absent — useful during prototype phase before API access is approved.

Whoop API docs: https://developer.whoop.com/api
Auth model: OAuth 2.0 Authorization Code Flow
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests

# ── Auth ─────────────────────────────────────────────────────────

WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE  = "https://api.prod.whoop.com/developer/v1"


def _get_token(client_id: str, client_secret: str) -> str:
    """
    Client Credentials grant — suitable for single-user prototype.
    For multi-user: implement full Authorization Code flow.
    """
    resp = requests.post(
        WHOOP_TOKEN_URL,
        data={
            "grant_type":    "client_credentials",
            "client_id":     client_id,
            "client_secret": client_secret,
            "scope":         "read:recovery read:sleep read:workout read:profile",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


# ── Data fetchers ────────────────────────────────────────────────

def _paginate(url: str, headers: dict, params: dict) -> list[dict]:
    """Follow Whoop's next_token pagination to exhaustion."""
    results = []
    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        body = resp.json()
        results.extend(body.get("records", []))
        next_token = body.get("next_token")
        if not next_token:
            break
        params = {**params, "nextToken": next_token}
    return results


def fetch_biometrics(
    client_id: str,
    client_secret: str,
    days: int = 90,
) -> pd.DataFrame:
    """
    Pull HRV, RHR, and deep sleep from Whoop recovery + sleep endpoints.
    Returns a DataFrame matching the biometrics_log schema.
    """
    token   = _get_token(client_id, client_secret)
    headers = {"Authorization": f"Bearer {token}"}
    start   = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    rows = []

    # Recovery (HRV + RHR)
    records = _paginate(
        f"{WHOOP_API_BASE}/recovery",
        headers,
        {"start": start, "limit": 25},
    )
    for r in records:
        ts = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        score = r.get("score", {})
        if "hrv_rmssd_milli" in score:
            rows.append({"source": "WHOOP", "metric_type": "HRV",
                         "value": score["hrv_rmssd_milli"], "recorded_at": ts})
        if "resting_heart_rate" in score:
            rows.append({"source": "WHOOP", "metric_type": "RHR",
                         "value": score["resting_heart_rate"], "recorded_at": ts})

    # Sleep (deep sleep minutes)
    sleep_records = _paginate(
        f"{WHOOP_API_BASE}/activity/sleep",
        headers,
        {"start": start, "limit": 25},
    )
    for s in sleep_records:
        ts    = datetime.fromisoformat(s["end"].replace("Z", "+00:00"))
        stage = s.get("score", {}).get("stage_summary", {})
        deep  = stage.get("total_slow_wave_sleep_time_milli", 0) / 60000  # → minutes
        if deep > 0:
            rows.append({"source": "WHOOP", "metric_type": "DEEP_SLEEP",
                         "value": round(deep, 1), "recorded_at": ts})

    df = pd.DataFrame(rows)
    if not df.empty:
        df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
    return df


# ── Public entry point ────────────────────────────────────────────

def load_biometrics(days: int = 90) -> tuple[pd.DataFrame, str]:
    """
    Returns (biometrics_df, source_label).
    Tries Whoop API first; falls back to synthetic data with a warning label.
    """
    try:
        import streamlit as st
        cid    = st.secrets.get("WHOOP_CLIENT_ID", "")
        csecret = st.secrets.get("WHOOP_CLIENT_SECRET", "")
    except Exception:
        cid = os.getenv("WHOOP_CLIENT_ID", "")
        csecret = os.getenv("WHOOP_CLIENT_SECRET", "")

    if cid and csecret:
        try:
            df = fetch_biometrics(cid, csecret, days=days)
            if not df.empty:
                return df, "whoop_live"
        except Exception as e:
            pass  # Fall through to synthetic

    # Graceful fallback
    from data.synthetic import generate
    bio_df, _ = generate(days=days)
    return bio_df, "synthetic"
