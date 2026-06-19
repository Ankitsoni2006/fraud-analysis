"""
database/db_models.py
====================
SQLAlchemy models for all entities in the IVC system.
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, JSON, ForeignKey
from database.db_setup import Base


class DBOrder(Base):
    __tablename__ = "orders"

    order_id = Column(String, primary_key=True, index=True)
    customer_id = Column(String, nullable=False, index=True)
    store_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)


class DBScanEvent(Base):
    __tablename__ = "scan_events"

    log_id = Column(String, primary_key=True, index=True)
    order_id = Column(String, nullable=False, index=True)
    packer_id = Column(String, nullable=False, index=True)
    item_id = Column(String, nullable=False, index=True)
    shelf_aisle = Column(String, nullable=False)
    shelf_num = Column(Integer, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    store_id = Column(String, nullable=False, default="STORE_01", index=True)
    
    # Enrichment fields from detectors
    anomaly_type = Column(String, nullable=True)
    anomaly_detail = Column(String, nullable=True)
    computed_velocity_ms = Column(Float, nullable=True)
    distance_from_prev_m = Column(Float, nullable=True)
    speed_flag = Column(Boolean, nullable=False, default=False)
    gap_seconds = Column(Float, nullable=True)
    hesitation_flag = Column(Boolean, nullable=False, default=False)


class DBRefundClaim(Base):
    __tablename__ = "refund_claims"

    refund_id = Column(String, primary_key=True, index=True)
    order_id = Column(String, nullable=False, index=True)
    customer_id = Column(String, nullable=False, index=True)
    item_id = Column(String, nullable=False)
    claimed_value_inr = Column(Float, nullable=False)
    claim_reason = Column(String, nullable=False)
    request_ts = Column(DateTime, nullable=False)
    injected_fraud = Column(Boolean, nullable=False, default=False)


class DBAuditResult(Base):
    __tablename__ = "audit_results"

    refund_id = Column(String, primary_key=True, index=True)
    order_id = Column(String, nullable=False, index=True)
    item_id = Column(String, nullable=False)
    claimed_value_inr = Column(Float, nullable=False)
    verdict = Column(String, nullable=False)
    audit_reason = Column(String, nullable=False)
    was_injected_fraud = Column(Boolean, nullable=False, default=False)


class DBPackerRiskProfile(Base):
    __tablename__ = "packer_risk_profiles"

    packer_id = Column(String, primary_key=True, index=True)
    type_a_count = Column(Integer, nullable=False, default=0)
    type_b_count = Column(Integer, nullable=False, default=0)
    total_score = Column(Integer, nullable=False, default=0)
    risk_level = Column(String, nullable=False, default="LOW")


class DBCustomerRiskProfile(Base):
    __tablename__ = "customer_risk_profiles"

    customer_id = Column(String, primary_key=True, index=True)
    refund_count = Column(Integer, nullable=False, default=0)
    high_value_refund_count = Column(Integer, nullable=False, default=0)
    total_orders = Column(Integer, nullable=False, default=0)
    refund_rate = Column(Float, nullable=False, default=0.0)
    total_claim_value = Column(Float, nullable=False, default=0.0)
    average_claim_value = Column(Float, nullable=False, default=0.0)
    risk_score = Column(Float, nullable=False, default=0.0)
    risk_level = Column(String, nullable=False, default="LOW")


class DBStoreRiskProfile(Base):
    __tablename__ = "store_risk_profiles"

    store_id = Column(String, primary_key=True, index=True)
    orders_processed = Column(Integer, nullable=False, default=0)
    refund_claims = Column(Integer, nullable=False, default=0)
    type_a_events = Column(Integer, nullable=False, default=0)
    type_b_events = Column(Integer, nullable=False, default=0)
    revenue_at_risk = Column(Float, nullable=False, default=0.0)
    store_risk_score = Column(Float, nullable=False, default=0.0)
    risk_level = Column(String, nullable=False, default="LOW")


class DBOperationalAnalyticsSnapshot(Base):
    __tablename__ = "operational_analytics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    total_orders = Column(Integer, nullable=False, default=0)
    total_scans = Column(Integer, nullable=False, default=0)
    total_revenue_processed = Column(Float, nullable=False, default=0.0)
    revenue_leakage_estimate = Column(Float, nullable=False, default=0.0)
    average_order_value = Column(Float, nullable=False, default=0.0)
    average_pack_time_s = Column(Float, nullable=False, default=0.0)
    anomaly_rate_overall = Column(Float, nullable=False, default=0.0)
    refund_abuse_rate = Column(Float, nullable=False, default=0.0)
    high_value_anomaly_rate = Column(Float, nullable=False, default=0.0)

    # Complex metrics mapped as JSON columns
    anomaly_rate_by_store = Column(JSON, nullable=False, default=dict)
    anomaly_rate_by_packer = Column(JSON, nullable=False, default=dict)
    top_risky_skus = Column(JSON, nullable=False, default=list)  # list of [sku, count]
    top_risky_categories = Column(JSON, nullable=False, default=list)  # list of [cat, count]
    revenue_by_category = Column(JSON, nullable=False, default=dict)
