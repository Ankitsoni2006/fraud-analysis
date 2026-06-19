"""
historical_intelligence/early_warning_engine.py
===============================================
Triggers early warning alerts and actions for high-risk or accelerating entities.
"""

from __future__ import annotations

from typing import Optional
from historical_intelligence.historical_models import EarlyWarning, TrendProfile


class EarlyWarningEngine:
    """
    Evaluates current risk levels and trends to flag anomalies before major leakage occurs.
    """

    def __init__(self) -> None:
        pass

    def evaluate(self, trend: TrendProfile) -> EarlyWarning:
        """
        Calculates risk acceleration and maps it to a WarningLevel and recommendation.
        """
        history = trend.risk_history
        current_risk = round(history[-1], 1) if history else 0.0

        # Calculate trend percentage over the last 30 days (or all available days if < 30)
        window = min(30, len(history))
        if window > 1:
            baseline = history[-window]
            if baseline > 0:
                trend_pct = round(((current_risk - baseline) / baseline) * 100.0, 1)
            else:
                trend_pct = round(current_risk * 100.0, 1) if current_risk > 0 else 0.0
        else:
            trend_pct = 0.0

        # Determine Warning Level
        if current_risk >= 75.0 or (current_risk >= 45.0 and trend.trend_direction == "RAPIDLY INCREASING"):
            warning_level = "CRITICAL"
            if trend.entity_type == "store":
                recommended_action = "Schedule immediate operational audit within 48 hours and restrict high-value inventory"
            elif trend.entity_type == "packer":
                recommended_action = "Restrict packer barcode scan access and review all shift video logs"
            else:
                recommended_action = "Suspend account privileges and trigger security verification"
        elif current_risk >= 45.0 or (current_risk >= 20.0 and trend.trend_direction in ("RAPIDLY INCREASING", "INCREASING")):
            warning_level = "HIGH_RISK"
            if trend.entity_type == "store":
                recommended_action = "Schedule operational audit within 7 days"
            elif trend.entity_type == "packer":
                recommended_action = "Review shift logs and shelf movement records within 3 days"
            else:
                recommended_action = "Flag customer for enhanced validation on next order"
        elif current_risk >= 20.0 or trend.trend_direction == "INCREASING":
            warning_level = "WATCHLIST"
            if trend.entity_type == "store":
                recommended_action = "Flag store for daily telemetry monitoring and manager check-in"
            elif trend.entity_type == "packer":
                recommended_action = "Monitor scan velocities and dwell time in subsequent shifts"
            else:
                recommended_action = "Flag account for manual refund audit verification"
        else:
            warning_level = "NORMAL"
            recommended_action = "Maintain standard automated operational surveillance"

        return EarlyWarning(
            entity_id=trend.entity_id,
            entity_type=trend.entity_type,
            warning_level=warning_level,
            current_risk=current_risk,
            trend_pct=trend_pct,
            recommended_action=recommended_action
        )
