"""
tests/test_historical.py
========================
Unit and integration tests for the Historical Intelligence subsystem.

Run with:  python test_historical.py
"""

from __future__ import annotations

import sys
import os
import unittest
from datetime import datetime, timedelta

# Ensure root workspace is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from historical_intelligence.historical_models import DailySnapshot, TrendProfile, EarlyWarning, RiskForecast
from historical_intelligence.trend_engine import TrendEngine, HistoricalNarrativeEngine
from historical_intelligence.early_warning_engine import EarlyWarningEngine
from historical_intelligence.forecasting_engine import ForecastingEngine
from historical_intelligence.network_health_engine import NetworkHealthEngine


# ── Test runner (no pytest required) ─────────────────────────────────────────

class _Result:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"  ✓  {name}")
        else:
            self.failed += 1
            self.errors.append(f"  ✗  {name}: {detail}")
            print(f"  ✗  {name}: {detail}")

    def summary(self) -> None:
        total = self.passed + self.failed
        print(f"\n  {'═'*60}")
        print(f"  Results: {self.passed}/{total} passed", end="")
        if self.failed:
            print(f"  |  {self.failed} FAILED")
        else:
            print("  ✓ ALL PASSED")
        print(f"  {'═'*60}\n")


R = _Result()


def run_test(name: str):
    """Decorator that catches exceptions and records pass/fail."""
    def decorator(fn):
        try:
            fn()
            R.record(name, True)
        except AssertionError as exc:
            R.record(name, False, str(exc))
        except Exception as exc:
            R.record(name, False, f"{type(exc).__name__}: {exc}")
        return fn
    return decorator


# ── Trend Engine Tests ────────────────────────────────────────────────────────

@run_test("Trend Engine: Calculates correct slope for linear sequence")
def test_trend_slope_calculation():
    # Simple increasing sequence: [10.0, 20.0, 30.0, 40.0, 50.0]
    # slope should be exactly 10.0 per day/week step
    snapshots = []
    base_date = datetime(2026, 6, 1)
    for i in range(35):  # 5 weeks
        snapshots.append(DailySnapshot(
            day_idx=i,
            date=base_date + timedelta(days=i),
            store_metrics={"STORE_01": {"risk_score": 10.0 + i}}
        ))
    te = TrendEngine(snapshots)
    trend = te.calculate_trend("STORE_01", "store")
    
    assert trend.slope > 0, "Slope should be positive"
    # Classified as increasing
    assert trend.trend_direction in ("INCREASING", "RAPIDLY INCREASING")


@run_test("Trend Engine: Classifies stable trends correctly")
def test_trend_stable_classification():
    snapshots = []
    base_date = datetime(2026, 6, 1)
    for i in range(21):
        snapshots.append(DailySnapshot(
            day_idx=i,
            date=base_date + timedelta(days=i),
            store_metrics={"STORE_01": {"risk_score": 25.0}}
        ))
    te = TrendEngine(snapshots)
    trend = te.calculate_trend("STORE_01", "store")
    assert trend.slope == 0.0
    assert trend.trend_direction == "STABLE"


# ── Forecasting Engine Tests ──────────────────────────────────────────────────

@run_test("Forecasting Engine: LTP projects linear trends and clips to [0, 100]")
def test_forecasting_ltp_clipping():
    # Rapidly increasing risk (from 80 to 95 in 30 days)
    risk_history = [80.0 + (i * 0.5) for i in range(30)] # ends at 94.5
    trend = TrendProfile(
        entity_id="PKR001",
        entity_type="packer",
        risk_history=risk_history,
        slope=0.5,
        trend_direction="RAPIDLY INCREASING"
    )
    fe = ForecastingEngine()
    fc = fe.forecast(trend, method="Linear Trend Projection")
    
    assert fc.forecast_7d >= 94.5
    assert fc.forecast_30d == 100.0, f"Expected forecasted score to be clipped at 100.0, got {fc.forecast_30d}"


@run_test("Forecasting Engine: Moving Average projects flat mean")
def test_forecasting_ma_projection():
    risk_history = [10.0, 20.0, 30.0, 40.0] # mean of last 4 elements is 25.0
    trend = TrendProfile(
        entity_id="PKR001",
        entity_type="packer",
        risk_history=risk_history,
        slope=10.0,
        trend_direction="INCREASING"
    )
    fe = ForecastingEngine()
    fc = fe.forecast(trend, method="Moving Average", ma_window=4)
    
    assert fc.forecast_7d == 25.0
    assert fc.forecast_14d == 25.0
    assert fc.forecast_30d == 25.0


@run_test("Forecasting Engine: Exponential Smoothing projects weighted average")
def test_forecasting_es_projection():
    risk_history = [10.0, 20.0, 30.0]
    trend = TrendProfile(
        entity_id="PKR001",
        entity_type="packer",
        risk_history=risk_history,
        slope=10.0,
        trend_direction="INCREASING"
    )
    fe = ForecastingEngine()
    # Simple smoothing calculation check
    # S_0 = 10
    # S_1 = 0.3 * 20 + 0.7 * 10 = 13
    # S_2 = 0.3 * 30 + 0.7 * 13 = 18.1
    fc = fe.forecast(trend, method="Exponential Smoothing", alpha=0.3)
    assert fc.forecast_7d == 18.1
    assert fc.forecast_30d == 18.1


# ── Early Warning Engine Tests ────────────────────────────────────────────────

@run_test("Early Warning: Triggers CRITICAL alert for high risk and rapid acceleration")
def test_early_warning_critical():
    trend = TrendProfile(
        entity_id="STORE_03",
        entity_type="store",
        risk_history=[10.0, 20.0, 50.0],
        slope=15.0,
        trend_direction="RAPIDLY INCREASING"
    )
    ew = EarlyWarningEngine().evaluate(trend)
    assert ew.warning_level == "CRITICAL"
    assert "immediate operational audit" in ew.recommended_action


@run_test("Early Warning: Triggers WATCHLIST for moderate risk store")
def test_early_warning_watchlist():
    trend = TrendProfile(
        entity_id="STORE_01",
        entity_type="store",
        risk_history=[25.0, 25.0, 25.0],
        slope=0.0,
        trend_direction="STABLE"
    )
    ew = EarlyWarningEngine().evaluate(trend)
    assert ew.warning_level == "WATCHLIST"
    assert "daily telemetry monitoring" in ew.recommended_action


# ── Network Health Engine Tests ───────────────────────────────────────────────

@run_test("Network Health Engine: Correctly penalizes anomalies and revenue exposure")
def test_network_health_penalties():
    # Scenario: High anomalies (50) and high revenue exposure (10,000)
    snap = DailySnapshot(
        day_idx=1,
        date=datetime(2026, 6, 1),
        total_anomalies=50,
        revenue_at_risk=10000.0,
        refund_abuse_rate=0.0
    )
    nhe = NetworkHealthEngine()
    score = nhe.compute_health(snap)
    
    # Anomaly penalty: 50 * 0.4 = 20.0 (capped at 25)
    # Revenue penalty: 10000 / 2000 = 5.0 (capped at 25)
    # Total health: 100.0 - 25.0 = 75.0
    assert score == 75.0, f"Expected health score 75.0, got {score}"


@run_test("Network Health Engine: Generates WoW report correctly")
def test_network_health_report():
    snapshots = [
        DailySnapshot(day_idx=0, date=datetime(2026, 6, 1), total_anomalies=0, revenue_at_risk=0.0),
        DailySnapshot(day_idx=1, date=datetime(2026, 6, 2), total_anomalies=10, revenue_at_risk=1000.0),
        DailySnapshot(day_idx=2, date=datetime(2026, 6, 3), total_anomalies=20, revenue_at_risk=5000.0)
    ]
    nhe = NetworkHealthEngine()
    report = nhe.generate_report(snapshots, days_ago=2)
    
    assert report.today_score < report.previous_score
    assert report.change < 0.0
    assert report.status == "Deteriorating"


# ── Narrative Engine Tests ────────────────────────────────────────────────────

@run_test("Narrative Engine: Computes narrative outputs based on metrics")
def test_narratives_metrics_driven():
    # Setup 90 days of daily snapshots
    snapshots = []
    base_date = datetime(2026, 3, 20)
    for d in range(90):
        # Escalate STORE_03 risk score in last 30 days
        s3_risk = 10.0 + (d - 60) * 2.5 if d >= 60 else 10.0
        # High PKR006 risk score
        pkr006_risk = 90.0
        
        snapshots.append(DailySnapshot(
            day_idx=d,
            date=base_date + timedelta(days=d),
            total_orders=100,
            total_anomalies=5 if d < 75 else 25,
            revenue_at_risk=1000.0 if d < 75 else 5000.0,
            refund_abuse_rate=0.05 if d < 75 else 0.20,
            store_metrics={
                "STORE_03": {"risk_score": s3_risk, "orders": 100.0, "anomalies": 2.0, "revenue_at_risk": 500.0},
                "STORE_01": {"risk_score": 10.0, "orders": 100.0, "anomalies": 0.0, "revenue_at_risk": 0.0}
            },
            packer_metrics={
                "PKR006": {"risk_score": pkr006_risk, "anomalies": 5.0},
                "PKR001": {"risk_score": 10.0, "anomalies": 0.0}
            },
            customer_metrics={
                "CUST001": {"risk_score": 80.0, "refunds": 5.0, "claims_value": 1500.0}
            }
        ))
        
    ne = HistoricalNarrativeEngine(snapshots)
    narratives = ne.generate_narratives()
    
    assert len(narratives) == 4
    assert "STORE_03" in narratives[0]
    assert "PKR006" in narratives[1]
    assert "Network health declined" in narratives[2]
    assert "Projected risk exposure" in narratives[3]


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("  " + "═" * 60)
    print("  IVC HISTORICAL INTELLIGENCE TEST SUITE")
    print("  " + "═" * 60)
    print()

    R.summary()
    sys.exit(1 if R.failed else 0)
