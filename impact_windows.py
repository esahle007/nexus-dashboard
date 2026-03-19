"""
nexus/core/impact_windows.py
============================
Project Nexus — Impact Window Engine

Implements the five research-based decay/lag models defined in the system spec.
All analysis scripts MUST use compute_weighted_signal() before running CCF.

Decay models:
  - EXPONENTIAL  : caffeine, blue_light       → e^(-λt), peak at lag
  - LINEAR       : alcohol                    → max(0, 1 - t/window)
  - LOGARITHMIC  : social_conflict            → rapid initial drop, slow tail
  - ZEITGEBER    : morning_light              → 24-h sinusoidal entrainment

Usage
-----
    from nexus.core.impact_windows import ImpactWindow, compute_weighted_signal

    events = [{"timestamp": ..., "quantity": 2.5}]  # e.g. two espressos
    signal = compute_weighted_signal("caffeine", events, target_timestamps)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Sequence

import numpy as np

# ─────────────────────────────────────────────────────────────
# Constants — mirrors migration 002 seed data (IMMUTABLE)
# ─────────────────────────────────────────────────────────────

DecayModel = Literal["EXPONENTIAL", "LINEAR", "LOGARITHMIC", "ZEITGEBER"]

IMPACT_WINDOW_REGISTRY: dict[str, dict] = {
    "caffeine": {
        "window_hours":   12.0,
        "decay_model":    "EXPONENTIAL",
        "peak_lag_hours":  0.75,   # 45 minutes
    },
    "alcohol": {
        "window_hours":   10.0,
        "decay_model":    "LINEAR",
        "peak_lag_hours":  0.5,
    },
    "social_conflict": {
        "window_hours":   6.0,
        "decay_model":    "LOGARITHMIC",
        "peak_lag_hours":  0.0,
    },
    "blue_light": {
        "window_hours":   4.0,
        "decay_model":    "EXPONENTIAL",
        "peak_lag_hours":  0.0,
    },
    "morning_light": {
        "window_hours":   24.0,
        "decay_model":    "ZEITGEBER",
        "peak_lag_hours":  0.0,
    },
}


# ─────────────────────────────────────────────────────────────
# Dataclass
# ─────────────────────────────────────────────────────────────

@dataclass
class ImpactWindow:
    sub_type:        str
    window_hours:    float
    decay_model:     DecayModel
    peak_lag_hours:  float

    # Derived: half-life used for EXPONENTIAL decay
    @property
    def half_life_hours(self) -> float:
        """Effective half-life so that weight ≈ 0.01 at t=window_hours."""
        if self.decay_model == "EXPONENTIAL":
            return self.window_hours / math.log(100)
        return self.window_hours / 2  # fallback, not used for non-exp models

    @classmethod
    def from_registry(cls, sub_type: str) -> "ImpactWindow":
        key = sub_type.lower().replace(" ", "_")
        if key not in IMPACT_WINDOW_REGISTRY:
            raise ValueError(
                f"Unknown sub_type '{sub_type}'. "
                f"Valid options: {list(IMPACT_WINDOW_REGISTRY)}"
            )
        params = IMPACT_WINDOW_REGISTRY[key]
        return cls(sub_type=key, **params)

    def weight(self, elapsed_hours: float) -> float:
        """
        Return the biological impact weight [0.0, 1.0] for an event
        that occurred `elapsed_hours` ago.

        Returns 0.0 if outside the impact window.
        """
        t = elapsed_hours - self.peak_lag_hours  # shift by lag

        # Outside window entirely
        if elapsed_hours < 0 or elapsed_hours > self.window_hours:
            return 0.0

        # Before peak (ramp-up phase)
        if t < 0:
            # Linear ramp from 0 → 1 over the peak_lag_hours window
            return max(0.0, elapsed_hours / self.peak_lag_hours) if self.peak_lag_hours > 0 else 1.0

        # Post-peak decay
        match self.decay_model:
            case "EXPONENTIAL":
                λ = math.log(100) / self.window_hours
                return math.exp(-λ * t)

            case "LINEAR":
                remaining = self.window_hours - self.peak_lag_hours
                return max(0.0, 1.0 - t / remaining) if remaining > 0 else 0.0

            case "LOGARITHMIC":
                # Rapid initial drop: w = 1 - log(1 + t) / log(1 + window)
                denom = math.log(1 + self.window_hours)
                return max(0.0, 1.0 - math.log(1 + t) / denom) if denom > 0 else 0.0

            case "ZEITGEBER":
                # 24-h cosine — captures the circadian/melatonin entrainment cycle
                # Weight peaks at t=0 (morning exposure), troughs at t=12h, recovers at t=24h
                return (1 + math.cos(2 * math.pi * t / 24.0)) / 2.0

            case _:
                raise ValueError(f"Unsupported decay model: {self.decay_model}")


# ─────────────────────────────────────────────────────────────
# Feature Engineering
# ─────────────────────────────────────────────────────────────

def compute_weighted_signal(
    sub_type: str,
    events: Sequence[dict],      # [{"timestamp": datetime, "quantity": float}, ...]
    target_timestamps: Sequence[datetime],
) -> np.ndarray:
    """
    For each target timestamp, sum the weighted impact of all preceding events.

    This is the core feature engineering step. Every CCF analysis script
    MUST call this before correlating with biometric data.

    Parameters
    ----------
    sub_type            : e.g. "caffeine", "alcohol"
    events              : list of context log entries with timestamp + quantity
    target_timestamps   : biometric measurement timestamps to align with

    Returns
    -------
    np.ndarray of shape (len(target_timestamps),)
        Weighted signal values aligned to each target timestamp.
    """
    iw = ImpactWindow.from_registry(sub_type)
    signal = np.zeros(len(target_timestamps))

    for i, target_ts in enumerate(target_timestamps):
        cumulative = 0.0
        for event in events:
            event_ts = event["timestamp"]
            if not isinstance(event_ts, datetime):
                raise TypeError(f"timestamp must be datetime, got {type(event_ts)}")

            # Ensure timezone-aware comparison
            if event_ts.tzinfo is None:
                event_ts = event_ts.replace(tzinfo=timezone.utc)
            if target_ts.tzinfo is None:
                target_ts = target_ts.replace(tzinfo=timezone.utc)

            elapsed_hours = (target_ts - event_ts).total_seconds() / 3600.0
            w = iw.weight(elapsed_hours)
            cumulative += w * event["quantity"]

        signal[i] = cumulative

    return signal


def compute_impact_end(sub_type: str, impact_start: datetime) -> datetime:
    """
    Convenience: compute the impact_end timestamp for a context log entry
    so it can be stored in human_context_log.impact_end.
    """
    from datetime import timedelta
    iw = ImpactWindow.from_registry(sub_type)
    return impact_start + timedelta(hours=iw.window_hours)
