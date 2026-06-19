"""
historical_intelligence/historical_models.py
============================================
Domain models for the historical intelligence subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DailySnapshot:
    """A single day's operational metrics aggregated across the platform."""
    day_idx:             int
    date:                datetime
    total_orders:        int = 0
    total_anomalies:     int = 0
    total_refund_claims: int = 0
    total_revenue:       float = 0.0
    revenue_leakage:     float = 0.0
    revenue_at_risk:     float = 0.0
    refund_abuse_rate:   float = 0.0
    anomaly_rate:        float = 0.0
    network_health_score: float = 0.0

    # Entity-specific summaries for this day (key -> metric_dict)
    # store_metrics: store_id -> {"risk_score": X, "orders": Y, "anomalies": Z, "revenue_at_risk": W}
    store_metrics:       dict[str, dict[str, float]] = field(default_factory=dict)
    # packer_metrics: packer_id -> {"risk_score": X, "anomalies": Y, "refund_exposure": Z}
    packer_metrics:      dict[str, dict[str, float]] = field(default_factory=dict)
    # customer_metrics: customer_id -> {"risk_score": X, "refunds": Y, "claims_value": Z}
    customer_metrics:    dict[str, dict[str, float]] = field(default_factory=dict)
    # category_metrics: category -> {"anomalies": X, "revenue": Y}
    category_metrics:    dict[str, dict[str, float]] = field(default_factory=dict)
    # sku_metrics: sku -> {"anomalies": X}
    sku_metrics:         dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class TrendProfile:
    """Historical risk evolution profile for an entity."""
    entity_id:       str
    entity_type:     str         # "store" | "packer" | "customer" | "category" | "sku"
    risk_history:    list[float] # historical scores (daily or weekly)
    slope:           float       # direction and magnitude of drift
    trend_direction: str         # "RAPIDLY INCREASING" | "INCREASING" | "STABLE" | "DECREASING" | "RAPIDLY DECREASING"


@dataclass
class EarlyWarning:
    """Triggered warning for a high-risk entity."""
    entity_id:          str
    entity_type:        str
    warning_level:      str      # "NORMAL" | "WATCHLIST" | "HIGH_RISK" | "CRITICAL"
    current_risk:       float
    trend_pct:          float    # e.g., +48.0
    recommended_action: str


@dataclass
class RiskForecast:
    """Forecasted risk scores using deterministic models."""
    entity_id:         str
    entity_type:       str
    current_risk:      float
    forecast_7d:       float
    forecast_14d:      float
    forecast_30d:      float
    method:            str       # "Moving Average" | "Exponential Smoothing" | "Linear Trend Projection"
    historical_scores: list[float]
    forecast_curve:    list[float] # Projected curve values for plotting


@dataclass
class NetworkHealthReport:
    """Network-level health metrics scorecard."""
    today_score:     float
    previous_score:  float
    change:          float
    status:          str         # "Improving" | "Stable" | "Deteriorating"
    history:         list[float] # Timeline of health scores
