"""
historical_intelligence/forecasting_engine.py
=============================================
Provides deterministic risk score forecasting without machine learning.
"""

from __future__ import annotations

import math
from historical_intelligence.historical_models import RiskForecast, TrendProfile


class ForecastingEngine:
    """
    Computes 7, 14, and 30-day risk score projections using:
      - Moving Average (MA)
      - Exponential Smoothing (ES)
      - Linear Trend Projection (LTP)
    """

    def __init__(self) -> None:
        pass

    def forecast(
        self,
        trend: TrendProfile,
        method: str = "Linear Trend Projection",
        alpha: float = 0.3,
        ma_window: int = 14
    ) -> RiskForecast:
        """
        Computes forward projections for risk score based on historical scores.
        Clips all outputs to [0.0, 100.0] range.
        """
        history = trend.risk_history
        if not history:
            return RiskForecast(
                entity_id=trend.entity_id,
                entity_type=trend.entity_type,
                current_risk=0.0,
                forecast_7d=0.0,
                forecast_14d=0.0,
                forecast_30d=0.0,
                method=method,
                historical_scores=[],
                forecast_curve=[]
            )

        current_risk = float(history[-1])
        t_len = len(history)

        forecast_7d = current_risk
        forecast_14d = current_risk
        forecast_30d = current_risk
        forecast_curve: list[float] = []

        if method == "Moving Average":
            # Flat projection using rolling mean of last ma_window days
            window = min(ma_window, t_len)
            ma_val = sum(history[-window:]) / window
            forecast_7d = ma_val
            forecast_14d = ma_val
            forecast_30d = ma_val
            # Curve is just flat line from current risk to ma_val
            forecast_curve = [current_risk] + [ma_val] * 30

        elif method == "Exponential Smoothing":
            # Simple exponential smoothing S_t = alpha * Y_t + (1-alpha)*S_{t-1}
            s = history[0]
            for val in history[1:]:
                s = alpha * val + (1 - alpha) * s
            forecast_7d = s
            forecast_14d = s
            forecast_30d = s
            forecast_curve = [current_risk] + [s] * 30

        elif method == "Linear Trend Projection":
            # Fit line y = m * x + c using last 30 days of data (or all if < 30)
            window = min(30, t_len)
            y = history[-window:]
            x = list(range(window))
            
            mean_x = sum(x) / window
            mean_y = sum(y) / window
            
            num = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(window))
            den = sum((x[i] - mean_x) ** 2 for i in range(window))
            
            m = num / den if den > 0 else 0.0
            c = mean_y - m * mean_x
            
            # Forecast curve for the next 30 days
            forecast_curve = [current_risk]
            for day in range(1, 31):
                # x coordinate in our fit line is: (window - 1) + day
                projected_x = (window - 1) + day
                pred = m * projected_x + c
                # Clip to valid risk score range
                pred = max(0.0, min(100.0, pred))
                forecast_curve.append(round(pred, 1))

            forecast_7d = forecast_curve[7]
            forecast_14d = forecast_curve[14]
            forecast_30d = forecast_curve[30]

        # Clip final scalar forecast values
        forecast_7d = max(0.0, min(100.0, round(forecast_7d, 1)))
        forecast_14d = max(0.0, min(100.0, round(forecast_14d, 1)))
        forecast_30d = max(0.0, min(100.0, round(forecast_30d, 1)))

        return RiskForecast(
            entity_id=trend.entity_id,
            entity_type=trend.entity_type,
            current_risk=current_risk,
            forecast_7d=forecast_7d,
            forecast_14d=forecast_14d,
            forecast_30d=forecast_30d,
            method=method,
            historical_scores=history,
            forecast_curve=forecast_curve
        )
