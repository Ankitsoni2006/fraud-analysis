"""
api/app.py
==========
FastAPI application for the IVC Operational Risk Intelligence Platform.
"""

from __future__ import annotations

import time
import os
from typing import Dict, Any, List
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database.db_setup import Base, engine, get_db
from database.repositories import IVCRepository
from orchestrator import IVCOrchestrator
from logging_config import get_logger
from models import PipelineResult
from historical_intelligence.historical_simulator import HistoricalSimulator
from historical_intelligence.network_health_engine import NetworkHealthEngine
from historical_intelligence.trend_engine import TrendEngine
from historical_intelligence.forecasting_engine import ForecastingEngine

log = get_logger(__name__)

app = FastAPI(
    title="IVC Operational Risk Intelligence API",
    description="Enterprise-grade risk and fraud analytics API for quick-commerce operational control.",
    version="2.0.0"
)

# Enable CORS for frontend components
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup metrics and state
START_TIME = time.time()
SYSTEM_METRICS = {
    "pipeline_runs": 0,
    "last_run_duration_ms": 0.0,
}

# Middleware for measuring response latency and logging request details
@app.middleware("http")
async def add_process_time_header(request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    log.info("Request processed", path=request.url.path, duration_ms=round(process_time * 1000, 2))
    return response


@app.on_event("startup")
def startup_event():
    """Ensure database schema exists and runs an initial simulation run if empty."""
    log.info("Starting up IVC API Server")
    Base.metadata.create_all(bind=engine)
    
    # Check if there is already data in the database
    db = next(get_db())
    repo = IVCRepository(db)
    events = repo.get_scan_events()
    if not events:
        log.info("Database empty on startup. Triggering initial baseline simulation.")
        try:
            orch = IVCOrchestrator(num_orders=100)
            result = orch.run(render_dashboard=False)
            repo.save_pipeline_result(result)
            SYSTEM_METRICS["pipeline_runs"] += 1
            log.info("Initial baseline simulation database seeding successful.")
        except Exception as exc:
            log.error("Failed to seed database during startup", error=str(exc))
    else:
        log.info("Database contains existing records. Startup seed skipped.", record_count=len(events))


# ── REST Endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["System"])
def get_health(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieves operational health, configuration modes, and database connection status."""
    db_connected = False
    db_type = "unknown"
    record_count = 0
    
    try:
        # Simple query test
        repo = IVCRepository(db)
        record_count = len(repo.get_scan_events())
        db_connected = True
        db_type = "sqlite" if "sqlite" in engine.url.drivername else "postgresql"
    except Exception as exc:
        log.error("Database health check failed", error=str(exc))
        
    return {
        "status": "healthy" if db_connected else "degraded",
        "mode": os.getenv("IVC_MODE", "SIMULATION"),
        "database": {
            "connected": db_connected,
            "type": db_type,
            "records_count": record_count
        },
        "system": {
            "uptime_seconds": round(time.time() - START_TIME, 2),
            "pipeline_runs": SYSTEM_METRICS["pipeline_runs"],
            "last_run_duration_ms": SYSTEM_METRICS["last_run_duration_ms"]
        }
    }


@app.post("/api/run", tags=["Pipeline"])
def trigger_pipeline(
    num_orders: int = Query(100, ge=10, le=1000), 
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Triggers an end-to-end pipeline run in Simulation mode, saving outputs to database."""
    t0 = time.perf_counter()
    try:
        orch = IVCOrchestrator(num_orders=num_orders)
        result = orch.run(render_dashboard=False)
        
        repo = IVCRepository(db)
        repo.save_pipeline_result(result)
        
        duration = round((time.perf_counter() - t0) * 1000, 2)
        SYSTEM_METRICS["pipeline_runs"] += 1
        SYSTEM_METRICS["last_run_duration_ms"] = duration
        
        return {
            "status": "success",
            "elapsed_ms": duration,
            "scan_events_count": len(result.validated_logs),
            "refund_claims_count": len(result.refund_claims),
            "speed_violations_count": len(result.speed_violations),
            "hesitation_violations_count": len(result.hesitation_violations)
        }
    except Exception as exc:
        log.error("Failed to run pipeline through API", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Pipeline run failed: {exc}")


@app.get("/api/stores", tags=["Profiles"])
def get_stores(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Retrieves all dark store risk profiles from the latest pipeline run."""
    repo = IVCRepository(db)
    profiles = repo.get_store_profiles()
    return [
        {
            "store_id": k,
            "orders_processed": p.orders_processed,
            "refund_claims": p.refund_claims,
            "type_a_events": p.type_a_events,
            "type_b_events": p.type_b_events,
            "revenue_at_risk": p.revenue_at_risk,
            "store_risk_score": p.store_risk_score,
            "risk_level": p.risk_level.value
        }
        for k, p in profiles.items()
    ]


@app.get("/api/customers", tags=["Profiles"])
def get_customers(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Retrieves customer risk profiles."""
    repo = IVCRepository(db)
    profiles = repo.get_customer_profiles()
    return [
        {
            "customer_id": k,
            "refund_count": p.refund_count,
            "high_value_refund_count": p.high_value_refund_count,
            "total_orders": p.total_orders,
            "refund_rate": p.refund_rate,
            "total_claim_value": p.total_claim_value,
            "average_claim_value": p.average_claim_value,
            "risk_score": p.risk_score,
            "risk_level": p.risk_level.value
        }
        for k, p in profiles.items()
    ]


@app.get("/api/packers", tags=["Profiles"])
def get_packers(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Retrieves packer risk profiles."""
    repo = IVCRepository(db)
    profiles = repo.get_packer_profiles()
    return [
        {
            "packer_id": k,
            "type_a_count": p.type_a_count,
            "type_b_count": p.type_b_count,
            "total_score": p.total_score,
            "risk_level": p.risk_level.value
        }
        for k, p in profiles.items()
    ]


@app.get("/api/refunds", tags=["Refunds"])
def get_refunds(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Retrieves refund claims and matching audit verdicts."""
    repo = IVCRepository(db)
    claims = repo.get_refund_claims()
    audits = {a.refund_id: a for a in repo.get_audit_results()}
    
    results = []
    for c in claims:
        audit = audits.get(c.refund_id)
        results.append({
            "refund_id": c.refund_id,
            "order_id": c.order_id,
            "customer_id": c.customer_id,
            "item_id": c.item_id,
            "claimed_value_inr": c.claimed_value_inr,
            "claim_reason": c.claim_reason,
            "request_ts": c.request_ts,
            "verdict": audit.verdict.value if audit else None,
            "audit_reason": audit.audit_reason if audit else None
        })
    return results


@app.get("/api/risk", tags=["Alerts"])
def get_risk_alerts(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Aggregates alert thresholds and returns high-risk counts across stores, packers, customers."""
    repo = IVCRepository(db)
    stores = repo.get_store_profiles()
    packers = repo.get_packer_profiles()
    customers = repo.get_customer_profiles()
    
    crit_stores = [k for k, p in stores.items() if p.store_risk_score >= 70.0]
    high_stores = [k for k, p in stores.items() if 45.0 <= p.store_risk_score < 70.0]
    
    crit_packers = [k for k, p in packers.items() if p.total_score >= 10]
    high_packers = [k for k, p in packers.items() if 5 <= p.total_score < 10]
    
    crit_customers = [k for k, p in customers.items() if p.risk_score >= 75.0]
    high_customers = [k for k, p in customers.items() if 50.0 <= p.risk_score < 75.0]
    
    return {
        "critical_count": len(crit_stores) + len(crit_packers) + len(crit_customers),
        "high_count": len(high_stores) + len(high_packers) + len(high_customers),
        "entities": {
            "stores": {
                "critical": crit_stores,
                "high": high_stores
            },
            "packers": {
                "critical": crit_packers,
                "high": high_packers
            },
            "customers": {
                "critical": crit_customers,
                "high": high_customers
            }
        }
    }


# ── Historical Analytics Endpoints ─────────────────────────────────────────────

@app.get("/api/network-health", tags=["Analytics"])
def get_network_health() -> Dict[str, Any]:
    """Generates the overall Network Health scorecard using historical snapshots."""
    # We load standard historical simulation snapshots
    history = HistoricalSimulator(orders_per_day=40).generate_history()
    nhe = NetworkHealthEngine()
    report = nhe.generate_report(history)
    
    return {
        "today_score": report.today_score,
        "previous_score": report.previous_score,
        "change": report.change,
        "status": report.status,
        "history": report.history
    }


@app.get("/api/trends", tags=["Analytics"])
def get_trends() -> List[Dict[str, Any]]:
    """Calculates Trend Profiles for all stores based on historical score drift."""
    history = HistoricalSimulator(orders_per_day=40).generate_history()
    te = TrendEngine(history)
    
    profiles = []
    # Build trends for all 10 stores
    from simulator import STORE_IDS
    for store_id in STORE_IDS:
        profile = te.analyze_store_trend(store_id)
        profiles.append({
            "entity_id": profile.entity_id,
            "entity_type": profile.entity_type,
            "risk_history": profile.risk_history,
            "slope": round(profile.slope, 4),
            "trend_direction": profile.trend_direction
        })
    return profiles


@app.get("/api/forecast", tags=["Analytics"])
def get_forecast(method: str = "Linear Trend Projection") -> List[Dict[str, Any]]:
    """Generates risk score forecasts for stores."""
    history = HistoricalSimulator(orders_per_day=40).generate_history()
    te = TrendEngine(history)
    fe = ForecastingEngine()
    
    forecasts = []
    from simulator import STORE_IDS
    for store_id in STORE_IDS:
        trend = te.analyze_store_trend(store_id)
        forecast = fe.forecast(trend, method=method)
        forecasts.append({
            "entity_id": forecast.entity_id,
            "entity_type": forecast.entity_type,
            "current_risk": forecast.current_risk,
            "forecast_7d": round(forecast.forecast_7d, 2),
            "forecast_14d": round(forecast.forecast_14d, 2),
            "forecast_30d": round(forecast.forecast_30d, 2),
            "method": forecast.method,
            "forecast_curve": forecast.forecast_curve
        })
    return forecasts
