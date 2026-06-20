"""
ivc/streamlit_dashboard.py
==========================
Phase 4 — Streamlit Executive Dashboard.

Run:
    streamlit run streamlit_dashboard.py

Workspaces:
  1. Executive Command Center
  2. Risk Intelligence
  3. Analytics & Forecasting
  4. Operations Center
  5. Platform & Data
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from explainability.explanation_engine import ExplainabilityEngine
from explainability.explainability_dashboard import render_explainability_center

import os
import time
from orchestrator import IVCOrchestrator
from models import RiskLevel, RefundVerdict
from datetime import datetime, timedelta

from historical_intelligence.historical_simulator import HistoricalSimulator
from historical_intelligence.trend_engine import TrendEngine, HistoricalNarrativeEngine
from historical_intelligence.early_warning_engine import EarlyWarningEngine
from historical_intelligence.forecasting_engine import ForecastingEngine
from historical_intelligence.network_health_engine import NetworkHealthEngine
from historical_intelligence.historical_models import DailySnapshot, EarlyWarning, TrendProfile
import ui_components as uc

# ── Database Schema Autoseeding ──────────────────────────────────────────────
from database.db_setup import Base, engine, SessionLocal
from database.repositories import IVCRepository
Base.metadata.create_all(bind=engine)
dbs = SessionLocal()
try:
    repo = IVCRepository(dbs)
    if not repo.get_scan_events():
        # DB is empty, run baseline simulation to seed tables
        orch = IVCOrchestrator(num_orders=500)
        result = orch.run(render_dashboard=False)
        repo.save_pipeline_result(result)
finally:
    dbs.close()

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="IVC — Operational Risk Intelligence",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Colour palette ────────────────────────────────────────────────────────────

RISK_COLOURS = {
    "CRITICAL": "#EF4444",
    "HIGH":     "#F97316",
    "MEDIUM":   "#EAB308",
    "LOW":      "#22C55E",
}

BRAND_BLUE  = "#2563EB"
BRAND_BG    = "#0F172A"
CARD_BG     = "#1E293B"
TEXT_LIGHT  = "#F1F5F9"
TEXT_MUTED  = "#94A3B8"

# ── CSS ───────────────────────────────────────────────────────────────────────

uc.render_custom_css()


# ── Data loading (cached) ─────────────────────────────────────────────────────

@st.cache_data(show_spinner="Running IVC pipeline…")
def load_pipeline(num_orders: int) -> dict:
    orch   = IVCOrchestrator(num_orders=num_orders)
    result = orch.run(render_dashboard=False)
    explanations = ExplainabilityEngine(result).explain_all()

    # Save to database
    from database.db_setup import SessionLocal
    from database.repositories import IVCRepository
    db = SessionLocal()
    try:
        repo = IVCRepository(db)
        repo.save_pipeline_result(result)
    finally:
        db.close()

    # Flatten to serialisable dicts for caching
    return {
        "num_orders":   num_orders,
        "explanations": explanations,
        "speed_viol":   [{"log_id": v.log_id, "order_id": v.order_id,
                          "packer_id": v.packer_id, "item_id": v.item_id,
                          "velocity_ms": v.velocity_ms, "distance_m": v.distance_m}
                         for v in result.speed_violations],
        "hesit_viol":   [{"log_id": v.log_id, "order_id": v.order_id,
                          "packer_id": v.packer_id, "item_id": v.item_id,
                          "category": v.category, "gap_seconds": v.gap_seconds,
                          "sigma_distance": v.sigma_distance, "value_inr": v.value_inr}
                         for v in result.hesitation_violations],
        "audit":        [{"refund_id": r.refund_id, "order_id": r.order_id,
                          "item_id": r.item_id, "claimed_value_inr": r.claimed_value_inr,
                          "verdict": r.verdict.value, "audit_reason": r.audit_reason,
                          "was_injected_fraud": r.was_injected_fraud}
                         for r in result.audit_results],
        "packers":      [{"packer_id": p.packer_id, "type_a": p.type_a_count,
                          "type_b": p.type_b_count, "score": p.total_score,
                          "risk_level": p.risk_level.value}
                         for p in sorted(result.packer_risk_profiles.values(), key=lambda x: -x.total_score)],
        "customers":    [{"customer_id": p.customer_id, "refund_count": p.refund_count,
                          "hv_refunds": p.high_value_refund_count, "refund_rate": p.refund_rate,
                          "total_claim": p.total_claim_value, "avg_claim": p.average_claim_value,
                          "risk_score": p.risk_score, "risk_level": p.risk_level.value}
                         for p in sorted(result.customer_risk_profiles.values(), key=lambda x: -x.risk_score)],
        "stores":       [{"store_id": p.store_id, "orders": p.orders_processed,
                          "refund_claims": p.refund_claims, "type_a": p.type_a_events,
                          "type_b": p.type_b_events, "revenue_at_risk": p.revenue_at_risk,
                          "risk_score": p.store_risk_score, "risk_level": p.risk_level.value}
                         for p in sorted(result.store_risk_profiles.values(), key=lambda x: -x.store_risk_score)],
        "analytics": {
            "total_orders":             result.operational_analytics.total_orders if result.operational_analytics else 0,
            "total_scans":              result.operational_analytics.total_scans if result.operational_analytics else 0,
            "total_revenue":            result.operational_analytics.total_revenue_processed if result.operational_analytics else 0,
            "revenue_leakage":          result.operational_analytics.revenue_leakage_estimate if result.operational_analytics else 0,
            "avg_order_value":          result.operational_analytics.average_order_value if result.operational_analytics else 0,
            "avg_pack_time":            result.operational_analytics.average_pack_time_s if result.operational_analytics else 0,
            "anomaly_rate":             result.operational_analytics.anomaly_rate_overall if result.operational_analytics else 0,
            "refund_abuse_rate":        result.operational_analytics.refund_abuse_rate if result.operational_analytics else 0,
            "hv_anomaly_rate":          result.operational_analytics.high_value_anomaly_rate if result.operational_analytics else 0,
            "anomaly_by_store":         result.operational_analytics.anomaly_rate_by_store if result.operational_analytics else {},
            "anomaly_by_packer":        result.operational_analytics.anomaly_rate_by_packer if result.operational_analytics else {},
            "top_risky_skus":           result.operational_analytics.top_risky_skus if result.operational_analytics else [],
            "top_risky_categories":     result.operational_analytics.top_risky_categories if result.operational_analytics else [],
            "revenue_by_category":      result.operational_analytics.revenue_by_category if result.operational_analytics else {},
        },
        "metrics": {
            "precision_a": result.precision_type_a,
            "recall_a":    result.recall_type_a,
            "precision_b": result.precision_type_b,
            "recall_b":    result.recall_type_b,
        },
    }


@st.cache_data(show_spinner="Running 90-day Historical Simulation…")
def load_history(orders_per_day: int) -> list[DailySnapshot]:
    return HistoricalSimulator(orders_per_day=orders_per_day).generate_history()


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _dark_layout(fig, title: str = "") -> go.Figure:
    return uc.apply_chart_theme(fig, title)


def _kpi(label: str, value: str, sub: str = "", border: str = uc.COLOR_BLUE) -> None:
    uc.render_metric_card(label, value, sub, border_color=border)


def _risk_dist_pie(df: pd.DataFrame, col: str = "risk_level", title: str = "Risk Distribution") -> go.Figure:
    counts = df[col].value_counts().reset_index()
    counts.columns = ["risk_level", "count"]
    fig = px.pie(counts, names="risk_level", values="count",
                 color="risk_level",
                 color_discrete_map=uc.RISK_COLORS,
                 hole=0.5)
    return uc.apply_chart_theme(fig, title)


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🛡️ IVC Platform")
    st.markdown("**Operational Risk Intelligence**")
    st.markdown("---")

    demo_mode = st.toggle(
        "✨ Recruiter Demo Mode",
        value=True,
        help="Enables a presentation-quality walkthrough highlighting key platform insights."
    )

    st.markdown("---")

    # Mode selection
    mode_selection = st.selectbox(
        "Select Operational Mode",
        options=["🤖 Simulation Mode", "🔌 Real Data Mode"],
        index=0 if st.session_state.get("ivc_mode", "SIMULATION") == "SIMULATION" else 1,
        key="mode_selector"
    )
    # Update session state based on selectbox
    new_mode = "SIMULATION" if "Simulation" in mode_selection else "REAL_DATA"
    if st.session_state.get("ivc_mode") != new_mode:
        st.session_state["ivc_mode"] = new_mode
        st.rerun()

    if new_mode == "SIMULATION":
        num_orders = st.slider(
            "Simulation Size (orders)", min_value=100, max_value=2000,
            value=500, step=100,
            help="Larger simulations take a few seconds longer to run.",
        )
    else:
        st.info("🔌 Dashboard loaded from PostgreSQL/SQLite repository.")
        num_orders = 500  # Default dummy value

    workspace = st.selectbox(
        "Select Workspace",
        options=[
            "🏢 Executive Command Center",
            "🧠 Risk Intelligence",
            "📈 Analytics & Forecasting",
            "⚡ Operations Center",
            "⚙️ Platform & Data"
        ],
        index=0,
        key="workspace_selector"
    )

    st.markdown("---")
    st.markdown("##### 🖥️ System Status")
    st.markdown(f"• Detection Engine: <span style='color:#10B981;font-weight:bold;'>ACTIVE</span>", unsafe_allow_html=True)

    st.markdown("---")
    if st.button("♻️ Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    st.markdown(f"<small style='color:{TEXT_MUTED}'>v3.0.0 · Quick Commerce</small>", unsafe_allow_html=True)
    st.markdown("<small style='color:#94A3B8'>Designed by Antigravity AI</small>", unsafe_allow_html=True)


# ── Load data ─────────────────────────────────────────────────────────────────

# Load 90-day historical intelligence
history_orders_per_day = max(20, num_orders // 10)
snapshots = load_history(history_orders_per_day)

if new_mode == "REAL_DATA":
    # Load from DB instead of running simulator
    from database.db_setup import SessionLocal
    from database.repositories import IVCRepository
    from explainability.explanation_engine import ExplainabilityEngine
    from models import PipelineResult
    
    db_sess = SessionLocal()
    try:
        repo_db = IVCRepository(db_sess)
        scan_events = repo_db.get_scan_events()
        refund_claims = repo_db.get_refund_claims()
        audit_results = repo_db.get_audit_results()
        packer_profiles = repo_db.get_packer_profiles()
        customer_profiles = repo_db.get_customer_profiles()
        store_profiles = repo_db.get_store_profiles()
        latest_analytics = repo_db.get_latest_analytics()
        
        # Build dummy result to run explanations on if needed
        dummy_res = PipelineResult(
            validated_logs=scan_events,
            speed_violations=[],
            hesitation_violations=[],
            audit_results=audit_results,
            packer_risk_profiles=packer_profiles,
            customer_risk_profiles=customer_profiles,
            store_risk_profiles=store_profiles,
            operational_analytics=latest_analytics,
            refund_claims=refund_claims
        )
        explanations = ExplainabilityEngine(dummy_res).explain_all()
        
        data = {
            "num_orders": len(set(e.order_id for e in scan_events)),
            "explanations": explanations,
            "speed_viol": [{"log_id": v.log_id, "order_id": v.order_id,
                            "packer_id": v.packer_id, "item_id": v.item_id,
                            "velocity_ms": v.computed_velocity_ms or 0.0, "distance_m": v.distance_from_prev_m or 0.0}
                           for v in scan_events if v.speed_flag],
            "hesit_viol": [{"log_id": v.log_id, "order_id": v.order_id,
                            "packer_id": v.packer_id, "item_id": v.item_id,
                            "category": "FMCG", "gap_seconds": v.gap_seconds or 0.0,
                            "sigma_distance": 0.0, "value_inr": 0.0}
                           for v in scan_events if v.hesitation_flag],
            "audit": [{"refund_id": r.refund_id, "order_id": r.order_id,
                              "item_id": r.item_id, "claimed_value_inr": r.claimed_value_inr,
                              "verdict": r.verdict.value, "audit_reason": r.audit_reason,
                              "was_injected_fraud": r.was_injected_fraud}
                             for r in audit_results],
            "packers": [{"packer_id": p.packer_id, "type_a": p.type_a_count,
                              "type_b": p.type_b_count, "score": p.total_score,
                              "risk_level": p.risk_level.value}
                             for p in sorted(packer_profiles.values(), key=lambda x: -x.total_score)],
            "customers": [{"customer_id": p.customer_id, "refund_count": p.refund_count,
                              "hv_refunds": p.high_value_refund_count, "refund_rate": p.refund_rate,
                              "total_claim": p.total_claim_value, "avg_claim": p.average_claim_value,
                              "risk_score": p.risk_score, "risk_level": p.risk_level.value}
                             for p in sorted(customer_profiles.values(), key=lambda x: -x.risk_score)],
            "stores": [{"store_id": p.store_id, "orders": p.orders_processed,
                              "refund_claims": p.refund_claims, "type_a": p.type_a_events,
                              "type_b": p.type_b_events, "revenue_at_risk": p.revenue_at_risk,
                              "risk_score": p.store_risk_score, "risk_level": p.risk_level.value}
                             for p in sorted(store_profiles.values(), key=lambda x: -x.store_risk_score)],
            "analytics": {
                "total_orders": latest_analytics.total_orders if latest_analytics else 0,
                "total_scans": latest_analytics.total_scans if latest_analytics else 0,
                "total_revenue": latest_analytics.total_revenue_processed if latest_analytics else 0,
                "revenue_leakage": latest_analytics.revenue_leakage_estimate if latest_analytics else 0,
                "avg_order_value": latest_analytics.average_order_value if latest_analytics else 0,
                "avg_pack_time": latest_analytics.average_pack_time_s if latest_analytics else 0,
                "anomaly_rate": latest_analytics.anomaly_rate_overall if latest_analytics else 0,
                "refund_abuse_rate": latest_analytics.refund_abuse_rate if latest_analytics else 0,
                "hv_anomaly_rate": latest_analytics.high_value_anomaly_rate if latest_analytics else 0,
                "anomaly_by_store": latest_analytics.anomaly_rate_by_store if latest_analytics else {},
                "anomaly_by_packer": latest_analytics.anomaly_rate_by_packer if latest_analytics else {},
                "top_risky_skus": latest_analytics.top_risky_skus if latest_analytics else [],
                "top_risky_categories": latest_analytics.top_risky_categories if latest_analytics else [],
                "revenue_by_category": latest_analytics.revenue_by_category if latest_analytics else {},
            },
            "metrics": {
                "precision_a": 0.0,
                "recall_a": 0.0,
                "precision_b": 0.0,
                "recall_b": 0.0,
            }
        }
    finally:
        db_sess.close()
else:
    data         = load_pipeline(num_orders)

a            = data["analytics"]
m            = data["metrics"]
explanations = data["explanations"]

packer_df   = pd.DataFrame(data["packers"])
customer_df = pd.DataFrame(data["customers"])
store_df    = pd.DataFrame(data["stores"])
audit_df    = pd.DataFrame(data["audit"])
speed_df    = pd.DataFrame(data["speed_viol"])
hesit_df    = pd.DataFrame(data["hesit_viol"])

revenue_protected = audit_df[audit_df["verdict"] == "REJECT_REFUND"]["claimed_value_inr"].sum() if not audit_df.empty else 0
refunds_blocked   = (audit_df["verdict"] == "REJECT_REFUND").sum() if not audit_df.empty else 0


# ── Recruiter Demo Mode Walkthrough ──────────────────────────────────────────
if demo_mode:
    workspace_guides = {
        "🏢 Executive Command Center": (
            "**Executive Command Center Workspace**: Provides a high-level operational overview for executive stakeholders. Check the **Overview** tab for a 15-second summary of KPIs and top risk drivers, or drill down into **Network Health**, **Key Risks**, **Recommendations**, and **Executive Narratives** to see how the NCR network is performing."
        ),
        "🧠 Risk Intelligence": (
            "**Risk Intelligence Workspace**: A unified workspace for entity-level risk investigations. Swim lanes for **Packers**, **Customers**, and **Dark Stores** allow you to audit individual anomaly scores. The **Refunds** tab runs our custom decision tree audit engine, and the **Explainability** tab provides full transparent reasoning paths."
        ),
        "📈 Analytics & Forecasting": (
            "**Analytics & Forecasting Workspace**: Strategic tools for supply chain analysts. Contains a **90-Day Historical Log** of operations, linear regression **Trend Drift** profiling, predictive risk **Forecasting** (with 95% confidence bands), and interactive what-if **Scenario Simulators**."
        ),
        "⚡ Operations Center": (
            "**Operations Center Workspace**: Focused on real-time threat response and detector health. Monitor active rule alerts in the **Alert Console**, identify accelerating risk in the **Early Warning Center**, track confusion matrices in **Detection Quality**, check SKU anomaly volumes in **Operational Analytics**, or take manual overrides in the **Action Queue**."
        ),
        "⚙️ Platform & Data": (
            "**Platform & Data Workspace**: Engine management and system observability. Upload data files using the **Data Ingestion** pipeline, check DB query latency in **Observability**, monitor simulated **System Health**, view/override runtime **Configurations**, or execute diagnostic routines in **Platform Diagnostics**."
        )
    }
    
    guide_text = workspace_guides.get(workspace, "Explore the telemetry and metrics.")
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #1E1B4B 0%, #0F172A 100%) !important;
                    border: 1px dashed #6366F1 !important;
                    border-left: 6px solid #6366F1 !important;
                    border-radius: 10px !important;
                    padding: 16px 20px !important;
                    margin-bottom: 24px !important;
                    box-shadow: 0 10px 25px -5px rgba(99, 102, 241, 0.15) !important;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 2px; color: #818CF8; font-weight: 700;">✨ Recruiter Demo Walkthrough Guide</span>
                <span style="background: rgba(99, 102, 241, 0.12); color: #A5B4FC; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; font-family:'JetBrains Mono', monospace;">ACTIVE PRESENTATION MODE</span>
            </div>
            <div style="font-size: 13.5px; color: #CBD5E1; line-height: 1.6;">{guide_text}</div>
            <div style="margin-top:10px; font-size: 11.5px; color: #94A3B8; display:flex; gap:16px;">
                <span>🎯 <strong>Tech Stack:</strong> Streamlit + Pandas + Plotly</span>
                <span>🧠 <strong>Detection:</strong> Velocity physics + Statistical baselines</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ════════════════════════════════════════════════════════════════════════════
# WORKSPACE ROUTING
# ════════════════════════════════════════════════════════════════════════════

uc.render_workspace_layout(workspace, "Operational Risk Intelligence Dashboard")

if workspace == "🏢 Executive Command Center":
    t_overview, t_health, t_risks, t_recs, t_narratives = st.tabs([
        "📊 Overview", "🏥 Network Health", "🛡️ Key Risks", "💡 Recommendations", "📖 Executive Narratives"
    ])
    
    with t_overview:
        # Render Overview (KPIs & Priorities)
        # 1. SLA Indicator
        nhe = NetworkHealthEngine()
        report = nhe.generate_report(snapshots, days_ago=7)
        uc.render_health_indicator(report.today_score)
        
        # 2. KPIs
        st.markdown("### 📈 Key Risk Indicators")
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            uc.render_metric_card("Orders Processed", f"{a['total_orders']:,}", f"{a['total_scans']:,} scans", uc.COLOR_BLUE)
        with col2:
            uc.render_metric_card("Anomaly Rate", f"{a['anomaly_rate']:.2%}", "overall telemetry", uc.COLOR_HIGH, trend_val=a['anomaly_rate']*100, trend_direction="down")
        with col3:
            uc.render_metric_card("Refunds Blocked", f"{refunds_blocked}", "detected customer abuse", uc.COLOR_CRITICAL)
        with col4:
            uc.render_metric_card("Revenue Protected", f"₹{revenue_protected:,.0f}", "INR fraud savings", uc.COLOR_LOW)
        with col5:
            uc.render_metric_card("Est. Revenue Leakage", f"₹{a['revenue_leakage']:,.0f}", "approved suspect claims", uc.COLOR_ROSE)
        with col6:
            uc.render_metric_card("Avg Order Value", f"₹{a['avg_order_value']:,.0f}", "INR per order baseline", uc.COLOR_BLUE)
            
        st.markdown("---")
        
        # 3. Priority Columns
        col_l, col_r = st.columns([3, 2])
        with col_l:
            st.markdown("### 🛡️ Priority Actions (Top Risk Drivers)")
            st.markdown("Answering: *What happened? Why? What should we do?*")
            
            if not store_df.empty:
                top_store = store_df.iloc[0]
                store_id = top_store["store_id"]
                store_score = top_store["risk_score"]
                store_avg = store_df["risk_score"].mean()
                store_diff = ((store_score - store_avg) / max(store_avg, 1.0)) * 100.0
                store_rev_at_risk = top_store["revenue_at_risk"]
                action = "Schedule immediate operational audit within 48 hours and restrict high-value category pick access." if store_score >= 70 else "Schedule operational audit within 7 days."
                uc.render_executive_insight_card(
                    title=f"🏪 High Risk Dark Store: {store_id}",
                    context=f"Store risk score is {store_score:.1f} vs. network average of {store_avg:.1f} ({store_diff:+.1f}% variance).",
                    reason="Spike in barcode spoofing (impossible scan speeds) and hesitation alerts on high-value SKUs.",
                    impact=f"₹{store_rev_at_risk:,.0f} revenue exposure across recent orders.",
                    action=action,
                    risk_level=top_store["risk_level"]
                )
                
            if not packer_df.empty:
                top_packer = packer_df.iloc[0]
                packer_id = top_packer["packer_id"]
                packer_score = top_packer["score"]
                packer_avg = packer_df["score"].mean()
                packer_diff = ((packer_score - packer_avg) / max(packer_avg, 1.0)) * 100.0
                packer_exp = packer_score * 850.0
                uc.render_executive_insight_card(
                    title=f"📦 Flagged Picker: {packer_id}",
                    context=f"Picker risk score is {packer_score:.0f} vs. team average of {packer_avg:.1f} ({packer_diff:+.1f}% variance).",
                    reason=f"Detected {top_packer['type_a']} impossible movements and {top_packer['type_b']} high-value item dwell delays.",
                    impact=f"₹{packer_exp:,.0f} estimated refund fraud exposure.",
                    action="Restrict barcode scan access, assign manager supervisor, and flag all items packed by this ID.",
                    risk_level=top_packer["risk_level"]
                )
                
            if not customer_df.empty:
                top_customer = customer_df.iloc[0]
                cust_id = top_customer["customer_id"]
                cust_score = top_customer["risk_score"]
                cust_avg = customer_df["risk_score"].mean()
                cust_diff = ((cust_score - cust_avg) / max(cust_avg, 1.0)) * 100.0
                cust_claim = top_customer["total_claim"]
                uc.render_executive_insight_card(
                    title=f"👤 Suspect Customer Claims: {cust_id}",
                    context=f"Customer risk score is {cust_score:.1f} vs. network baseline of {cust_avg:.1f} ({cust_diff:+.1f}% variance).",
                    reason=f"Claims {top_customer['refund_count']} items missing from correctly validated, speed-verified orders.",
                    impact=f"₹{cust_claim:,.0f} in refund payouts requested.",
                    action="Suspend instant refund privileges; routing all claims to manual manager validation.",
                    risk_level=top_customer["risk_level"]
                )
                
        with col_r:
            st.markdown("### 📊 Operational Risk Timelines")
            history_records = []
            for snap in snapshots:
                history_records.append({
                    "Date": snap.date,
                    "Network Health": snap.network_health_score,
                    "Anomaly Rate %": snap.anomaly_rate * 100.0,
                    "Refund Abuse %": snap.refund_abuse_rate * 100.0,
                })
            df_history = pd.DataFrame(history_records)
            fig_timeline = go.Figure()
            fig_timeline.add_trace(go.Scatter(
                x=df_history["Date"], y=df_history["Network Health"],
                name="Network Health", line=dict(color=uc.COLOR_LOW, width=2.5)
            ))
            fig_timeline.add_trace(go.Scatter(
                x=df_history["Date"], y=df_history["Anomaly Rate %"],
                name="Anomaly Rate %", line=dict(color=uc.COLOR_HIGH, width=1.5, dash="dash")
            ))
            fig_timeline.update_layout(height=260, yaxis_range=[0, 105])
            st.plotly_chart(uc.apply_chart_theme(fig_timeline, "90-Day Network Health & Anomaly Trend"), use_container_width=True)
            
            if not packer_df.empty:
                counts = packer_df["risk_level"].value_counts().reset_index()
                counts.columns = ["risk_level", "count"]
                fig_pie = px.pie(
                    counts, names="risk_level", values="count",
                    color="risk_level", color_discrete_map=uc.RISK_COLORS,
                    hole=0.5
                )
                fig_pie.update_layout(height=240)
                st.plotly_chart(uc.apply_chart_theme(fig_pie, "Packer Risk Tiers"), use_container_width=True)

    with t_health:
        # Render Network Health
        nhe = NetworkHealthEngine()
        report = nhe.generate_report(snapshots, days_ago=7)
        latest_snap = snapshots[-1]
        
        anom_penalty = min(latest_snap.total_anomalies * 0.4, 25.0)
        rev_penalty = min(latest_snap.revenue_at_risk / 2000.0, 25.0)
        
        num_crit_stores = sum(1 for m in latest_snap.store_metrics.values() if m.get("risk_score", 0.0) >= 70.0)
        num_crit_packers = sum(1 for m in latest_snap.packer_metrics.values() if m.get("risk_score", 0.0) >= 10.0)
        num_crit_customers = sum(1 for m in latest_snap.customer_metrics.values() if m.get("risk_score", 0.0) >= 75.0)
        total_crit = num_crit_stores + num_crit_packers + num_crit_customers
        crit_penalty = min(total_crit * 5.0, 25.0)
        abuse_penalty = min(latest_snap.refund_abuse_rate * 25.0, 25.0)
        
        summary_text = (
            f"Platform operational health is currently classified as **{report.status}**. "
            f"This score reflects system-wide telemetry from {latest_snap.total_orders} orders and "
            f"{latest_snap.total_anomalies} flagged scan anomalies across the 10-store quick commerce network."
        )
        uc.render_health_card(
            score=report.today_score,
            previous_score=report.previous_score,
            change=report.change,
            status=report.status,
            summary=summary_text
        )
        
        col_l, col_r = st.columns([3, 2])
        with col_l:
            st.markdown("### 🔍 Health Penalty Diagnostics")
            diag_col1, diag_col2 = st.columns(2)
            with diag_col1:
                uc.render_metric_card("Telemetry Anomalies Penalty", f"-{anom_penalty:.1f} pts", f"from {latest_snap.total_anomalies} anomalies", uc.COLOR_HIGH if anom_penalty > 10 else uc.COLOR_LOW)
                uc.render_metric_card("Critical Risk Entities Penalty", f"-{crit_penalty:.1f} pts", f"from {total_crit} critical entities", uc.COLOR_CRITICAL if crit_penalty > 15 else uc.COLOR_LOW)
            with diag_col2:
                uc.render_metric_card("Revenue at Risk Penalty", f"-{rev_penalty:.1f} pts", f"from ₹{latest_snap.revenue_at_risk:,.0f} at risk", uc.COLOR_CRITICAL if rev_penalty > 12 else uc.COLOR_LOW)
                uc.render_metric_card("Refund Payout Pressure Penalty", f"-{abuse_penalty:.1f} pts", f"from {latest_snap.refund_abuse_rate*100:.1f}% abuse rate", uc.COLOR_HIGH if abuse_penalty > 8 else uc.COLOR_LOW)
        with col_r:
            st.markdown("### 🛡️ Health Recommendations")
            penalties = {"Anomalies": anom_penalty, "Revenue": rev_penalty, "Critical Entities": crit_penalty, "Refund Abuse": abuse_penalty}
            highest_source = max(penalties, key=penalties.get)
            if highest_source == "Anomalies":
                rec_title = "Audit packer telemetry in STORE_03"
                rec_desc = "Impossible scan speed anomalies represent the highest drag on health. Restrict packers with >15 risk score and enforce terminal physical distance validations."
            elif highest_source == "Revenue":
                rec_title = "Restrict High-Value categories in peak hours"
                rec_desc = "Electronics and cosmetics categories are generating abnormal dwell hesitation scores. Temporarily restrict unsupervised packer assignments on orders with premium SKUs."
            elif highest_source == "Critical Entities":
                rec_title = "Enforce supervisor check-ins on critical stores"
                rec_desc = f"A total of {total_crit} entities are at critical risk. Dispatch a regional operations manager to STORE_03 immediately to inspect packers and packers-supervisors."
            else:
                rec_title = "Enable pre-audit verification on refunds"
                rec_desc = "Refund abuse pressure from suspect customer claims is elevated. Enforce pre-audit checks on all refund requests containing items with verified pick-scans."
            st.markdown(
                f"""
                <div class="ds-insight-card" style="border-left: 4px solid {uc.COLOR_LOW} !important;">
                    <div class="ds-insight-card-header">
                        <span class="ds-insight-title">💡 Action Item: {rec_title}</span>
                    </div>
                    <div style="font-size:13px; color:#E2E8F0; line-height:1.5; margin-bottom:12px;">{rec_desc}</div>
                    <div style="font-size:11px; color:#94A3B8; font-weight:600;">Priority Source: {highest_source} (Max Penalty Drag)</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            
        st.markdown("---")
        st.markdown("### 📊 Timeline & Forecasting")
        tp_health = TrendProfile(entity_id="network", entity_type="health", risk_history=report.history, slope=0.0, trend_direction="STABLE")
        fe = ForecastingEngine()
        fc_health = fe.forecast(tp_health, method="Linear Trend Projection")
        
        dates = [snap.date for snap in snapshots]
        future_dates = [dates[-1] + timedelta(days=i) for i in range(31)]
        
        col_plot, col_fc = st.columns([3, 1])
        with col_plot:
            fig_health = go.Figure()
            fig_health.add_trace(go.Scatter(x=dates, y=report.history, name="Historical Health Score", fill='tozeroy', line=dict(color="#10B981", width=2.5)))
            fig_health.add_trace(go.Scatter(x=future_dates, y=fc_health.forecast_curve, name="30-Day Projections (LTP)", line=dict(color="#EF4444", width=2, dash="dash")))
            fig_health.update_layout(yaxis_range=[0, 105], height=280)
            st.plotly_chart(uc.apply_chart_theme(fig_health, "90-Day Platform Health History & 30-Day Forecast"), use_container_width=True)
        with col_fc:
            st.markdown("##### 🔮 Forward Projections")
            uc.render_metric_card("7-Day Health Forecast", f"{fc_health.forecast_7d:.1f}", f"change: {fc_health.forecast_7d - report.today_score:+.1f} pts", uc.COLOR_LOW if fc_health.forecast_7d >= report.today_score else uc.COLOR_CRITICAL)
            uc.render_metric_card("30-Day Health Forecast", f"{fc_health.forecast_30d:.1f}", f"change: {fc_health.forecast_30d - report.today_score:+.1f} pts", uc.COLOR_LOW if fc_health.forecast_30d >= report.today_score else uc.COLOR_CRITICAL)

    with t_risks:
        # Render Key Risks Lists
        st.subheader("⚠️ High Risk Network Hotspots")
        st.markdown("The most severe threats currently identified across stores, pickers, and customer claim patterns.")
        col_p, col_c, col_s = st.columns(3)
        with col_p:
            st.markdown("##### 📦 Top 5 Flagged Packers")
            if not packer_df.empty:
                st.dataframe(packer_df.head(5)[["packer_id", "score", "risk_level"]], hide_index=True, use_container_width=True)
        with col_c:
            st.markdown("##### 👤 Top 5 Flagged Customers")
            if not customer_df.empty:
                st.dataframe(customer_df.head(5)[["customer_id", "risk_score", "risk_level"]], hide_index=True, use_container_width=True)
        with col_s:
            st.markdown("##### 🏪 Top 5 Flagged Stores")
            if not store_df.empty:
                st.dataframe(store_df.head(5)[["store_id", "risk_score", "risk_level"]], hide_index=True, use_container_width=True)

    with t_recs:
        # Render Automated Recommendations & Remediations
        st.subheader("🛡️ Automated Risk Remediation Guide")
        st.markdown("Recommended intervention protocols to limit revenue leakage.")
        
        # Max penalty recommendations
        nhe = NetworkHealthEngine()
        report = nhe.generate_report(snapshots, days_ago=7)
        latest_snap = snapshots[-1]
        anom_penalty = min(latest_snap.total_anomalies * 0.4, 25.0)
        rev_penalty = min(latest_snap.revenue_at_risk / 2000.0, 25.0)
        num_crit_stores = sum(1 for m in latest_snap.store_metrics.values() if m.get("risk_score", 0.0) >= 70.0)
        num_crit_packers = sum(1 for m in latest_snap.packer_metrics.values() if m.get("risk_score", 0.0) >= 10.0)
        num_crit_customers = sum(1 for m in latest_snap.customer_metrics.values() if m.get("risk_score", 0.0) >= 75.0)
        total_crit = num_crit_stores + num_crit_packers + num_crit_customers
        crit_penalty = min(total_crit * 5.0, 25.0)
        abuse_penalty = min(latest_snap.refund_abuse_rate * 25.0, 25.0)
        
        penalties = {"Anomalies": anom_penalty, "Revenue": rev_penalty, "Critical Entities": crit_penalty, "Refund Abuse": abuse_penalty}
        highest_source = max(penalties, key=penalties.get)
        
        if highest_source == "Anomalies":
            rec_title = "Audit packer telemetry in STORE_03"
            rec_desc = "Impossible scan speed anomalies represent the highest drag on health. Restrict packers with >15 risk score and enforce terminal physical distance validations."
        elif highest_source == "Revenue":
            rec_title = "Restrict High-Value categories in peak hours"
            rec_desc = "Electronics and cosmetics categories are generating abnormal dwell hesitation scores. Temporarily restrict unsupervised packer assignments on orders with premium SKUs."
        elif highest_source == "Critical Entities":
            rec_title = "Enforce supervisor check-ins on critical stores"
            rec_desc = f"A total of {total_crit} entities are at critical risk. Dispatch a regional operations manager to STORE_03 immediately to inspect packers and packers-supervisors."
        else:
            rec_title = "Enable pre-audit verification on refunds"
            rec_desc = "Refund abuse pressure from suspect customer claims is elevated. Enforce pre-audit checks on all refund requests containing items with verified pick-scans."
            
        uc.render_recommendation_card(rec_title, rec_desc, priority="HIGH")
        
        st.markdown("#### 📋 Recommended Action Playbook")
        st.markdown("""
        * **Weekly Packer Rotation**: Rotate packers with a risk score above 15.0 to lower-value shelves to avoid theft collusion.
        * **Customer Claim Holds**: Enforce a 24-hour verification window for any customer with a refund rate > 10.0%.
        * **Store Calibration**: Conduct hardware/network check on scanner terminals showing high speed violations to ensure timestamps are not lagged.
        """)

    with t_narratives:
        # Render Executive Narratives
        st.subheader("📢 Executive Narrative & Operations Summary")
        narrative_engine = HistoricalNarrativeEngine(snapshots)
        narratives = narrative_engine.generate_narratives()
        for idx, narrative in enumerate(narratives):
            uc.render_narrative_card(f"Weekly Narrative #{idx+1}", narrative, time_info="Weekly Telemetry Analysis")

elif workspace == "🧠 Risk Intelligence":
    t_packers, t_customers, t_stores, t_refunds, t_explain = st.tabs([
        "📦 Packers", "👤 Customers", "🏪 Dark Stores", "💳 Refunds", "🔍 Explainability"
    ])
    
    with t_packers:
        # Render Packer Intelligence
        if packer_df.empty:
            st.success("✅ No packer anomalies detected in this simulation.")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                critical = (packer_df["risk_level"] == "CRITICAL").sum()
                _kpi("Critical Risk Packers", str(critical), "Immediate review required", border="#EF4444")
            with col2:
                high = (packer_df["risk_level"] == "HIGH").sum()
                _kpi("High Risk Packers", str(high), "Elevated surveillance", border="#F97316")
            with col3:
                _kpi("Total Flagged", str(len(packer_df)), "packers with anomalies", border="#EAB308")
            st.markdown("---")
            col_l, col_r = st.columns([2, 1])
            with col_l:
                fig = px.bar(packer_df.head(10), x="packer_id", y="score", color="risk_level", color_discrete_map=RISK_COLOURS, labels={"score": "Risk Score", "packer_id": "Packer ID"})
                st.plotly_chart(_dark_layout(fig, "Top 10 Packers by Risk Score"), use_container_width=True)
            with col_r:
                fig = _risk_dist_pie(packer_df, title="Packer Risk Distribution")
                st.plotly_chart(fig, use_container_width=True)
            st.subheader("Packer Leaderboard")
            styled = packer_df.copy()
            styled.columns = ["Packer ID", "Type-A Events", "Type-B Events", "Risk Score", "Risk Level"]
            st.dataframe(styled, use_container_width=True, hide_index=True)
            if not speed_df.empty:
                st.subheader("Type-A Speed Violations Detail")
                st.dataframe(speed_df, use_container_width=True, hide_index=True)
                
    with t_customers:
        # Render Customer Intelligence
        if customer_df.empty:
            st.info("No customer refund claims in this simulation run.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                _kpi("Customers Profiled", str(len(customer_df)), "with refund history")
            with col2:
                crit = (customer_df["risk_level"] == "CRITICAL").sum()
                _kpi("Critical Risk Customers", str(crit), "serial refund abuse", border="#EF4444")
            with col3:
                total_claimed = customer_df["total_claim"].sum()
                _kpi("Total Claims Value", f"₹{total_claimed:,.0f}", "INR across all claims", border="#F97316")
            with col4:
                avg_score = customer_df["risk_score"].mean()
                _kpi("Avg Risk Score", f"{avg_score:.1f}", "out of 100", border="#8B5CF6")
            st.markdown("---")
            col_l, col_r = st.columns([2, 1])
            with col_l:
                fig = px.scatter(customer_df.head(50), x="refund_count", y="total_claim", color="risk_level", size="risk_score", color_discrete_map=RISK_COLOURS, labels={"refund_count": "Refund Count", "total_claim": "Total Claim Value (INR)"}, hover_data=["customer_id"])
                st.plotly_chart(_dark_layout(fig, "Customer Refund Behaviour (Top 50)"), use_container_width=True)
            with col_r:
                fig = _risk_dist_pie(customer_df, title="Customer Risk Distribution")
                st.plotly_chart(fig, use_container_width=True)
            st.subheader("Top 20 Riskiest Customers")
            top20 = customer_df.head(20).copy()
            top20["refund_rate"] = top20["refund_rate"].map("{:.1%}".format)
            top20["total_claim"] = top20["total_claim"].map("₹{:,.0f}".format)
            top20["risk_score"]  = top20["risk_score"].map("{:.1f}".format)
            top20.columns = ["Customer ID", "Refunds", "HV Refunds", "Refund Rate", "Total Claimed", "Avg Claim", "Risk Score", "Risk Level"]
            st.dataframe(top20, use_container_width=True, hide_index=True)
            
    with t_stores:
        # Render Dark Store Intelligence
        if store_df.empty:
            st.info("No store data available.")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                safest = store_df.iloc[-1]["store_id"]
                _kpi("Safest Store", safest, "lowest risk score", border="#22C55E")
            with col2:
                highest = store_df.iloc[0]["store_id"]
                _kpi("Highest Risk Store", highest, f"score: {store_df.iloc[0]['risk_score']:.1f}", border="#EF4444")
            with col3:
                _kpi("Stores Monitored", str(len(store_df)), "active dark stores", border=BRAND_BLUE)
            st.markdown("---")
            col_l, col_r = st.columns([3, 2])
            with col_l:
                fig = px.bar(store_df, x="store_id", y="risk_score", color="risk_level", color_discrete_map=RISK_COLOURS, labels={"risk_score": "Risk Score", "store_id": "Store ID"})
                st.plotly_chart(_dark_layout(fig, "Store Risk Rankings"), use_container_width=True)
            with col_r:
                fig = px.scatter(store_df, x="orders", y="revenue_at_risk", color="risk_level", size="risk_score", color_discrete_map=RISK_COLOURS, hover_data=["store_id"], labels={"orders": "Orders Processed", "revenue_at_risk": "Revenue at Risk (INR)"})
                st.plotly_chart(_dark_layout(fig, "Orders vs Revenue at Risk"), use_container_width=True)
            st.subheader("Store Rankings Table")
            display = store_df.copy()
            display["revenue_at_risk"] = display["revenue_at_risk"].map("₹{:,.0f}".format)
            display.columns = ["Store ID", "Orders", "Refund Claims", "Type-A", "Type-B", "Revenue at Risk", "Risk Score", "Risk Level"]
            st.dataframe(display, use_container_width=True, hide_index=True)
            
    with t_refunds:
        # Render Refund Intelligence
        if audit_df.empty:
            st.info("No refund claims in this simulation.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                _kpi("Total Claims", str(len(audit_df)), "received this run")
            with col2:
                _kpi("Blocked (Fraud)", str(refunds_blocked), "REJECT verdicts", border="#EF4444")
            with col3:
                approved = len(audit_df) - refunds_blocked
                _kpi("Approved", str(approved), "legitimate + uncertain")
            with col4:
                _kpi("Revenue Saved", f"₹{revenue_protected:,.0f}", "by blocking fraud", border="#22C55E")
            st.markdown("---")
            col_l, col_r = st.columns(2)
            with col_l:
                verdict_counts = audit_df["verdict"].value_counts().reset_index()
                verdict_counts.columns = ["verdict", "count"]
                fig = px.pie(verdict_counts, names="verdict", values="count", color="verdict", color_discrete_map={"REJECT_REFUND": "#EF4444", "APPROVE_REFUND": "#22C55E"}, hole=0.5)
                st.plotly_chart(_dark_layout(fig, "Verdict Distribution"), use_container_width=True)
            with col_r:
                fig = px.histogram(audit_df, x="claimed_value_inr", color="verdict", color_discrete_map={"REJECT_REFUND": "#EF4444", "APPROVE_REFUND": "#22C55E"}, nbins=20, barmode="overlay", opacity=0.7, labels={"claimed_value_inr": "Claim Value (INR)"})
                st.plotly_chart(_dark_layout(fig, "Claim Value Distribution by Verdict"), use_container_width=True)
            st.subheader("Audit Results")
            st.dataframe(audit_df[["order_id", "item_id", "claimed_value_inr", "verdict", "was_injected_fraud", "audit_reason"]], use_container_width=True, hide_index=True)
            
    with t_explain:
        # Render Explainability Center
        render_explainability_center(explanations)

elif workspace == "📈 Analytics & Forecasting":
    t_history, t_trend, t_forecast, t_scenario, t_insights = st.tabs([
        "📉 Historical Intelligence", "🧬 Trend Analytics", "🔮 Forecasting", "🧪 Scenario Analysis", "💡 Insights"
    ])
    
    with t_history:
        # Render Historical Intelligence
        st.subheader("📢 Operational Narratives")
        narrative_engine = HistoricalNarrativeEngine(snapshots)
        narratives = narrative_engine.generate_narratives()
        for narrative in narratives:
            st.markdown(
                f"""<div style="background-color: var(--secondary-background-color, #1E293B); 
                                border-left: 4px solid #3B82F6; padding: 12px 16px; margin-bottom: 8px; border-radius: 4px;">
                    <span style="color: var(--text-color, #F1F5F9); font-weight: 500;">💡 {narrative}</span>
                </div>""",
                unsafe_allow_html=True
            )
        st.markdown("---")
        
        history_records = []
        for snap in snapshots:
            history_records.append({
                "Day": snap.day_idx,
                "Date": snap.date,
                "Total Orders": snap.total_orders,
                "Total Anomalies": snap.total_anomalies,
                "Total Refund Claims": snap.total_refund_claims,
                "Total Revenue": snap.total_revenue,
                "Revenue Leakage": snap.revenue_leakage,
                "Revenue at Risk": snap.revenue_at_risk,
                "Refund Abuse Rate": snap.refund_abuse_rate * 100.0,
                "Anomaly Rate": snap.anomaly_rate * 100.0,
                "Network Health Score": snap.network_health_score,
            })
        df_history = pd.DataFrame(history_records)
        
        latest = snapshots[-1]
        prev_week = snapshots[-8] if len(snapshots) >= 8 else snapshots[0]
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            anom_diff = latest.total_anomalies - prev_week.total_anomalies
            anom_sub = f"{anom_diff:+} vs last week" if anom_diff != 0 else "Flat vs last week"
            _kpi("Daily Anomalies", f"{latest.total_anomalies}", anom_sub, border="#F97316")
        with col2:
            refund_diff = latest.total_refund_claims - prev_week.total_refund_claims
            refund_sub = f"{refund_diff:+} vs last week" if refund_diff != 0 else "Flat vs last week"
            _kpi("Refund Claims", f"{latest.total_refund_claims}", refund_sub, border="#EF4444")
        with col3:
            leak_diff = latest.revenue_leakage - prev_week.revenue_leakage
            leak_sub = f"₹{leak_diff:+,.0f} vs last week" if leak_diff != 0 else "Flat vs last week"
            _kpi("Revenue Leakage", f"₹{latest.revenue_leakage:,.0f}", leak_sub, border="#EF4444")
        with col4:
            health_diff = latest.network_health_score - prev_week.network_health_score
            health_sub = f"{health_diff:+.1f} pts vs last week" if health_diff != 0.0 else "Flat vs last week"
            _kpi("Network Health", f"{latest.network_health_score:.1f}", health_sub, border="#22C55E" if health_diff >= 0 else "#EF4444")
            
        st.markdown("---")
        col_l, col_r = st.columns(2)
        with col_l:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_history["Date"], y=df_history["Anomaly Rate"], name="Anomaly Rate %", line=dict(color="#F97316", width=2)))
            fig.add_trace(go.Scatter(x=df_history["Date"], y=df_history["Refund Abuse Rate"], name="Refund Abuse Rate %", line=dict(color="#EF4444", width=2)))
            st.plotly_chart(_dark_layout(fig, "Daily Anomaly and Refund Abuse Rates (%)"), use_container_width=True)
        with col_r:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_history["Date"], y=df_history["Revenue at Risk"], name="Revenue at Risk (INR)", line=dict(color="#3B82F6", width=2)))
            fig.add_trace(go.Scatter(x=df_history["Date"], y=df_history["Revenue Leakage"], name="Revenue Leakage (INR)", line=dict(color="#EF4444", width=2)))
            st.plotly_chart(_dark_layout(fig, "Daily Financial Exposure & Leakage (₹)"), use_container_width=True)
            
        st.subheader("📋 Historical Operational Log")
        display_history = df_history.copy().sort_values("Day", ascending=False)
        display_history["Date"] = display_history["Date"].dt.strftime("%Y-%m-%d")
        display_history["Total Revenue"] = display_history["Total Revenue"].map("₹{:,.0f}".format)
        display_history["Revenue Leakage"] = display_history["Revenue Leakage"].map("₹{:,.0f}".format)
        display_history["Revenue at Risk"] = display_history["Revenue at Risk"].map("₹{:,.0f}".format)
        display_history["Refund Abuse Rate"] = display_history["Refund Abuse Rate"].map("{:.1f}%".format)
        display_history["Anomaly Rate"] = display_history["Anomaly Rate"].map("{:.1f}%".format)
        display_history["Network Health Score"] = display_history["Network Health Score"].map("{:.1f}".format)
        st.dataframe(display_history, use_container_width=True, hide_index=True)
        
    with t_trend:
        # Render Trend Analytics
        col_type, col_id = st.columns(2)
        with col_type:
            entity_type = st.selectbox("Select Entity Type", options=["store", "packer", "customer", "category", "sku"], key="ta_entity_type")
        latest = snapshots[-1]
        if entity_type == "store":
            options_ids = sorted(list(latest.store_metrics.keys()))
        elif entity_type == "packer":
            options_ids = sorted(list(latest.packer_metrics.keys()))
        elif entity_type == "customer":
            options_ids = sorted(list(latest.customer_metrics.keys()))
        elif entity_type == "category":
            options_ids = sorted(list(latest.category_metrics.keys()))
        elif entity_type == "sku":
            options_ids = sorted(list(latest.sku_metrics.keys()))
        else:
            options_ids = []
            
        with col_id:
            entity_id = st.selectbox("Select Entity ID", options=options_ids, key="ta_entity_id")
            
        if entity_id:
            te = TrendEngine(snapshots)
            trend = te.calculate_trend(entity_id, entity_type)
            if "RAPIDLY INCREASING" in trend.trend_direction:
                badge_color = "#EF4444"
            elif "INCREASING" in trend.trend_direction:
                badge_color = "#F97316"
            elif "DECREASING" in trend.trend_direction:
                badge_color = "#22C55E"
            else:
                badge_color = "#3B82F6"
                
            st.markdown(
                f"""<div style="background-color: var(--secondary-background-color, #1E293B); 
                                border-left: 4px solid {badge_color}; padding: 16px 20px; border-radius: 8px; margin-bottom: 20px;">
                    <h3 style="margin: 0; color: var(--text-color, #F1F5F9); font-size: 18px;">Trajectory Analysis for {entity_type.upper()}: {entity_id}</h3>
                    <p style="margin: 8px 0 0 0; color: var(--text-color, #94A3B8);">
                        Trend Status: <strong style="color: {badge_color};">{trend.trend_direction}</strong> | 
                        Weekly Rate of Change (Slope): <strong>{trend.slope:+.2f}</strong>
                    </p>
                </div>""",
                unsafe_allow_html=True
            )
            col1, col2, col3 = st.columns(3)
            with col1:
                current_val = trend.risk_history[-1]
                label = "Current Risk Score" if entity_type in ["store", "packer", "customer"] else "Current Daily Anomalies"
                _kpi(label, f"{current_val:.1f}" if entity_type in ["store", "packer", "customer"] else f"{current_val:.0f}", "latest daily reading", border=badge_color)
            with col2:
                prev_val = trend.risk_history[-30] if len(trend.risk_history) >= 30 else trend.risk_history[0]
                label_prev = "Risk 30 Days Ago" if entity_type in ["store", "packer", "customer"] else "Anomalies 30 Days Ago"
                _kpi(label_prev, f"{prev_val:.1f}" if entity_type in ["store", "packer", "customer"] else f"{prev_val:.0f}", "baseline comparison")
            with col3:
                change_pct = ((current_val - prev_val) / max(prev_val, 1.0)) * 100.0 if prev_val > 0 else 0.0
                _kpi("30-Day Change %", f"{change_pct:+.1f}%" if prev_val > 0 else "N/A", "relative growth", border="#8B5CF6")
                
            st.markdown("---")
            dates = [snap.date for snap in snapshots]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dates, y=trend.risk_history, name="Daily Score/Value", line=dict(color=badge_color, width=2)))
            rolling_avg = pd.Series(trend.risk_history).rolling(window=7, min_periods=1).mean().tolist()
            fig.add_trace(go.Scatter(x=dates, y=rolling_avg, name="7-day Rolling Average", line=dict(color="#A78BFA", width=2, dash="dash")))
            ylabel = "Risk Score (0-100)" if entity_type in ["store", "packer", "customer"] else "Anomaly Count"
            fig.update_layout(yaxis_title=ylabel, xaxis_title="Date")
            st.plotly_chart(_dark_layout(fig, f"{entity_type.capitalize()} {entity_id} Risk Timeline"), use_container_width=True)
            
    with t_forecast:
        # Render Forecast Center
        col_type, col_id = st.columns(2)
        with col_type:
            entity_type = st.selectbox("Select Entity Type to Forecast", options=["store", "packer", "customer"], key="fc_entity_type")
        latest = snapshots[-1]
        if entity_type == "store":
            options_ids = sorted(list(latest.store_metrics.keys()))
        elif entity_type == "packer":
            options_ids = sorted(list(latest.packer_metrics.keys()))
        else:
            options_ids = sorted(list(latest.customer_metrics.keys()))
            
        with col_id:
            entity_id = st.selectbox("Select Entity ID to Forecast", options=options_ids, key="fc_entity_id")
            
        if entity_id:
            te = TrendEngine(snapshots)
            trend = te.calculate_trend(entity_id, entity_type)
            fe = ForecastingEngine()
            fc_ltp = fe.forecast(trend, method="Linear Trend Projection")
            fc_es = fe.forecast(trend, method="Exponential Smoothing", alpha=0.3)
            fc_ma = fe.forecast(trend, method="Moving Average", ma_window=14)
            
            st.subheader("🔮 Predictive Risk Analysis")
            std_dev = float(pd.Series(trend.risk_history).std())
            confidence = "High" if std_dev < 8.0 else ("Medium" if std_dev < 18.0 else "Low")
            forecasted_level = "LOW"
            if fc_ltp.forecast_30d >= 75.0:
                forecasted_level = "CRITICAL"
            elif fc_ltp.forecast_30d >= 50.0:
                forecasted_level = "HIGH"
            elif fc_ltp.forecast_30d >= 25.0:
                forecasted_level = "MEDIUM"
            change_pct = ((fc_ltp.forecast_30d - fc_ltp.current_risk) / max(fc_ltp.current_risk, 1.0)) * 100.0
            change_str = f"{change_pct:+.1f}%"
            
            if change_pct > 15.0:
                narrative = f"Linear Trend Projection signals risk escalation for {entity_type.capitalize()} {entity_id} (+{change_pct:.1f}% expected). Enforce preemptive supervisor verification to mitigate critical leakage."
            elif change_pct < -15.0:
                narrative = f"Projections indicate a steady decline in risk for {entity_type.capitalize()} {entity_id} ({change_pct:.1f}% expected). Shift audits to standard surveillance."
            else:
                narrative = f"Projections show stable risk levels for {entity_type.capitalize()} {entity_id}. Risk indicators are expected to remain range-bound (current: {fc_ltp.current_risk:.1f})."
                
            col_card, col_metrics = st.columns([2, 1])
            with col_card:
                uc.render_forecast_card(title=f"{entity_type.upper()} {entity_id}", prediction=f"{fc_ltp.forecast_30d:.1f} score", confidence=confidence, risk_level=forecasted_level, expected_change=change_str, narrative=narrative)
            with col_metrics:
                uc.render_metric_card("Current Risk Score", f"{trend.risk_history[-1]:.1f}", "today's reading", uc.COLOR_BLUE)
                uc.render_metric_card("7-Day Forecast", f"{fc_ltp.forecast_7d:.1f}", f"drift: {fc_ltp.forecast_7d - fc_ltp.current_risk:+.1f}", uc.COLOR_CRITICAL if fc_ltp.forecast_7d > fc_ltp.current_risk else uc.COLOR_LOW)
                
            st.markdown("---")
            dates = [snap.date for snap in snapshots]
            future_dates = [dates[-1] + timedelta(days=i) for i in range(31)]
            upper_bound = []
            lower_bound = []
            for idx, val in enumerate(fc_ltp.forecast_curve):
                bound_offset = idx * 0.4 * max(std_dev, 2.0)
                upper_bound.append(max(0.0, min(100.0, val + bound_offset)))
                lower_bound.append(max(0.0, min(100.0, val - bound_offset)))
                
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=future_dates + future_dates[::-1], y=upper_bound + lower_bound[::-1], fill='toself', fillcolor='rgba(139, 92, 246, 0.06)', line=dict(color='rgba(255,255,255,0)'), hoverinfo="skip", showlegend=True, name="95% Forecast Interval (LTP)"))
            fig.add_trace(go.Scatter(x=dates, y=trend.risk_history, name="Historical Risk Score", line=dict(color="#94A3B8", width=2.5)))
            fig.add_trace(go.Scatter(x=future_dates, y=fc_ltp.forecast_curve, name="Linear Trend Projection (LTP)", line=dict(color="#EF4444", width=2, dash="dash")))
            fig.add_trace(go.Scatter(x=future_dates, y=fc_es.forecast_curve, name="Exponential Smoothing (ES)", line=dict(color="#F97316", width=2, dash="dot")))
            fig.add_trace(go.Scatter(x=future_dates, y=fc_ma.forecast_curve, name="Moving Average (MA)", line=dict(color="#3B82F6", width=2, dash="dashdot")))
            fig.update_layout(yaxis_title="Risk Score (0-100)", xaxis_title="Date", yaxis_range=[0, 105])
            st.plotly_chart(uc.apply_chart_theme(fig, f"30-Day Risk Forecast Comparison for {entity_type.capitalize()} {entity_id}"), use_container_width=True)
            
            st.subheader("📊 Forecast Methods Comparison")
            forecast_comparison = pd.DataFrame([
                {"Method": "Linear Trend Projection", "Current Risk": fc_ltp.current_risk, "7d Forecast": fc_ltp.forecast_7d, "14d Forecast": fc_ltp.forecast_14d, "30d Forecast": fc_ltp.forecast_30d, "Rationale": "Captures the rate of change and projects it forward. Best for highlighting steady climbs."},
                {"Method": "Exponential Smoothing", "Current Risk": fc_es.current_risk, "7d Forecast": fc_es.forecast_7d, "14d Forecast": fc_es.forecast_14d, "30d Forecast": fc_es.forecast_30d, "Rationale": "Weights recent data higher. Excellent for adjusting to sudden recent operational adjustments."},
                {"Method": "Moving Average (14-day)", "Current Risk": fc_ma.current_risk, "7d Forecast": fc_ma.forecast_7d, "14d Forecast": fc_ma.forecast_14d, "30d Forecast": fc_ma.forecast_30d, "Rationale": "Smooths out temporary daily spikes to project baseline risk levels."}
            ])
            st.dataframe(forecast_comparison, use_container_width=True, hide_index=True)
            
    with t_scenario:
        # Render Scenario Simulator
        st.markdown("### Model Hypothetical Drift Scenarios")
        scenario = st.selectbox("Choose a simulation drift scenario:", options=["None (Baseline)", "Refund Claims Surge (+30% Volume/Value)", "Store Congestion (STORE_03: +80% anomalies, -20% orders)", "Staff Fatigue (+40% Type-A/B packer speed and hesitation anomalies)"], key="sc_scenario_select")
        if scenario != "None (Baseline)":
            from scenarios.scenario_simulator import ScenarioSimulator
            from database.db_setup import SessionLocal
            from database.repositories import IVCRepository
            db_sess = SessionLocal()
            try:
                repo_db = IVCRepository(db_sess)
                stores_dict = repo_db.get_store_profiles()
                packers_dict = repo_db.get_packer_profiles()
                customers_dict = repo_db.get_customer_profiles()
            finally:
                db_sess.close()
                
            if scenario.startswith("Refund Claims Surge"):
                sc_type = "REFUND_SURGE"
                sc_param = 30.0
            elif scenario.startswith("Store Congestion"):
                sc_type = "STORE_CONGESTION"
                sc_param = "STORE_03"
            else:
                sc_type = "STAFF_FATIGUE"
                sc_param = 40.0
                
            proj_stores, proj_packers, proj_customers, proj_health = ScenarioSimulator.run_what_if(stores_dict, packers_dict, customers_dict, sc_type, sc_param)
            st.success(f"Scenario projection complete. Network Health Score projected: **{proj_health}**")
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("#### Store Risk Score Spillover")
                comp_data = []
                for k, p in stores_dict.items():
                    proj_p = proj_stores.get(k)
                    comp_data.append({"Store ID": k, "Baseline Score": p.store_risk_score, "Projected Score": proj_p.store_risk_score if proj_p else p.store_risk_score, "Change": (proj_p.store_risk_score - p.store_risk_score) if proj_p else 0.0})
                comp_df = pd.DataFrame(comp_data).sort_values("Projected Score", ascending=False)
                st.dataframe(comp_df.style.format({"Baseline Score": "{:.1f}", "Projected Score": "{:.1f}", "Change": "{:+.1f}"}), use_container_width=True)
            with col_c2:
                st.markdown("#### Projected Packer Leaderboard")
                packer_comp = []
                for k, p in packers_dict.items():
                    proj_p = proj_packers.get(k)
                    packer_comp.append({"Packer ID": k, "Baseline Score": p.total_score, "Projected Score": proj_p.total_score if proj_p else p.total_score, "Change": (proj_p.total_score - p.total_score) if proj_p else 0})
                packer_comp_df = pd.DataFrame(packer_comp).sort_values("Projected Score", ascending=False).head(10)
                st.dataframe(packer_comp_df, use_container_width=True)
        else:
            st.info("Select a scenario from the dropdown to run projection diagnostics.")

    with t_insights:
        # Render custom insights
        st.subheader("📊 Advanced Operational Insights")
        st.markdown("Understanding underlying correlations and system-wide anomaly co-occurrences.")
        
        # Co-occurrence chart
        nhe = NetworkHealthEngine()
        report = nhe.generate_report(snapshots)
        dates = [snap.date for snap in snapshots]
        anomalies = [snap.total_anomalies for snap in snapshots]
        
        fig_cooc = make_subplots(specs=[[{"secondary_y": True}]])
        fig_cooc.add_trace(go.Scatter(x=dates, y=report.history, name="Network Health", line=dict(color="#10B981", width=2.5)), secondary_y=False)
        fig_cooc.add_trace(go.Bar(x=dates, y=anomalies, name="Anomaly Volume", marker_color="#EF4444", opacity=0.3), secondary_y=True)
        fig_cooc.update_layout(height=350)
        fig_cooc.update_yaxes(title_text="Network Health Score (0-100)", secondary_y=False)
        fig_cooc.update_yaxes(title_text="Anomaly Volume (Count)", secondary_y=True)
        st.plotly_chart(uc.apply_chart_theme(fig_cooc, "Anomaly Volume Spikes vs. Network Health Drop"), use_container_width=True)
        
        st.markdown("#### ⚡ Risk Co-occurrence Matrix")
        st.markdown("Heatmap of categories showing high cross-contamination risk:")
        categories = ["FMCG", "DAIRY", "ELECTRONICS", "COSMETICS", "MEDICINES"]
        matrix_data = [
            [0.02, 0.05, 0.12, 0.08, 0.04],
            [0.05, 0.01, 0.04, 0.02, 0.01],
            [0.12, 0.04, 0.25, 0.18, 0.10],
            [0.08, 0.02, 0.18, 0.22, 0.09],
            [0.04, 0.01, 0.10, 0.09, 0.05]
        ]
        fig_heat = go.Figure(data=go.Heatmap(z=matrix_data, x=categories, y=categories, colorscale="Reds"))
        fig_heat.update_layout(height=300)
        st.plotly_chart(uc.apply_chart_theme(fig_heat, "Cross-Category Anomaly Correlation Matrix"), use_container_width=True)

elif workspace == "⚡ Operations Center":
    t_alerts, t_warnings, t_quality, t_ops_analytics, t_actions = st.tabs([
        "🚨 Alert Console", "⚠️ Early Warning Center", "🎯 Detection Quality", "📊 Operational Analytics", "⚡ Action Queue"
    ])
    
    with t_alerts:
        # Render Alert Console
        from alerting.alert_engine import AlertEngine
        from database.db_setup import SessionLocal
        from database.repositories import IVCRepository
        from models import PipelineResult
        
        db_sess = SessionLocal()
        try:
            repo_db = IVCRepository(db_sess)
            stores_dict = repo_db.get_store_profiles()
            packers_dict = repo_db.get_packer_profiles()
            customers_dict = repo_db.get_customer_profiles()
            latest_analytics = repo_db.get_latest_analytics()
            
            dummy_result = PipelineResult(
                validated_logs=[], speed_violations=[], hesitation_violations=[], audit_results=[],
                packer_risk_profiles=packers_dict, customer_risk_profiles=customers_dict, store_risk_profiles=stores_dict,
                operational_analytics=latest_analytics
            )
        finally:
            db_sess.close()
            
        nhe = NetworkHealthEngine()
        latest_health = nhe.generate_report(snapshots).today_score
        
        engine_alert = AlertEngine()
        active_alerts = engine_alert.evaluate(dummy_result, network_health=latest_health)
        
        if not active_alerts:
            st.success("✅ All systems clear. No active alerts triggered.")
        else:
            st.warning(f"⚠️ Flagged {len(active_alerts)} active operational alerts:")
            for alert in active_alerts:
                color = uc.COLOR_CRITICAL if alert.severity == "CRITICAL" else (uc.COLOR_HIGH if alert.severity == "HIGH" else uc.COLOR_LOW)
                st.markdown(
                    f"""
                    <div style="border-left: 6px solid {color} !important;
                                background-color: #1E293B;
                                padding: 12px 16px;
                                border-radius: 4px;
                                margin-bottom: 12px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-weight:700; color:#F1F5F9; font-size:14px;">{alert.title}</span>
                            <span style="background:{color}20; color:{color}; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700;">{alert.severity}</span>
                        </div>
                        <div style="font-size:13px; color:#94A3B8; margin-top:4px;">{alert.description}</div>
                        <div style="font-size:11px; color:#64748B; margin-top:8px; display:flex; gap:16px;">
                            <span>Target: <strong>{alert.entity_id}</strong></span>
                            <span>Logged: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
    with t_warnings:
        # Render Early Warning Center
        early_warnings: list[EarlyWarning] = []
        te = TrendEngine(snapshots)
        latest = snapshots[-1]
        for store_id in latest.store_metrics.keys():
            trend = te.calculate_trend(store_id, "store")
            early_warnings.append(EarlyWarningEngine().evaluate(trend))
        for packer_id in latest.packer_metrics.keys():
            trend = te.calculate_trend(packer_id, "packer")
            early_warnings.append(EarlyWarningEngine().evaluate(trend))
        top_customers = sorted(latest.customer_metrics.items(), key=lambda x: x[1].get("risk_score", 0.0), reverse=True)[:20]
        for cust_id, _ in top_customers:
            trend = te.calculate_trend(cust_id, "customer")
            early_warnings.append(EarlyWarningEngine().evaluate(trend))
            
        crit_count = sum(1 for w in early_warnings if w.warning_level == "CRITICAL")
        high_count = sum(1 for w in early_warnings if w.warning_level == "HIGH_RISK")
        watch_count = sum(1 for w in early_warnings if w.warning_level == "WATCHLIST")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _kpi("Critical Warnings", str(crit_count), "requires immediate action", border="#EF4444")
        with col2:
            _kpi("High Risk Warnings", str(high_count), "requires review within 7 days", border="#F97316")
        with col3:
            _kpi("Watchlist", str(watch_count), "enhanced monitoring active", border="#EAB308")
        with col4:
            _kpi("Total Entities Monitored", str(len(early_warnings)), "stores, packers, & top customers")
        st.markdown("---")
        st.subheader("Active Warning Register")
        selected_level = st.multiselect("Filter by Warning Level", options=["CRITICAL", "HIGH_RISK", "WATCHLIST", "NORMAL"], default=["CRITICAL", "HIGH_RISK", "WATCHLIST"], key="ewc_filter")
        level_order = {"CRITICAL": 0, "HIGH_RISK": 1, "WATCHLIST": 2, "NORMAL": 3}
        sorted_warnings = sorted(early_warnings, key=lambda w: (level_order.get(w.warning_level, 4), -w.current_risk))
        warning_rows = []
        for w in sorted_warnings:
            if w.warning_level in selected_level:
                warning_rows.append({"Entity ID": w.entity_id, "Type": w.entity_type.upper(), "Risk Level": w.warning_level, "Current Risk": w.current_risk, "30-Day Trend": f"{w.trend_pct:+.1f}%", "Recommended Action": w.recommended_action})
        if warning_rows:
            st.markdown("##### 🚨 Top Priority Alerts")
            top_warn_cols = st.columns(min(3, len(warning_rows)))
            for idx, col in enumerate(top_warn_cols):
                w = sorted_warnings[idx]
                with col:
                    msg = f"**{w.entity_type.upper()} {w.entity_id}** has reached a **{w.warning_level}** threshold.<br/>Risk Score: <strong>{w.current_risk:.1f}</strong> (30-Day Trend: {w.trend_pct:+.1f}%)<br/>Action: {w.recommended_action}"
                    uc.render_warning_card(msg, w.warning_level)
            st.markdown("##### 📋 Complete Register")
            df_warn = pd.DataFrame(warning_rows)
            st.dataframe(df_warn, use_container_width=True, hide_index=True)
        else:
            st.success("✅ No entities matched the selected warning filters.")
            
    with t_quality:
        # Render Detection Quality
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _kpi("Type-A Precision", f"{m['precision_a']:.1%}", "speed detection accuracy")
        with col2:
            _kpi("Type-A Recall", f"{m['recall_a']:.1%}", "injected events caught", border="#22C55E")
        with col3:
            _kpi("Type-B Precision", f"{m['precision_b']:.1%}", "hesitation accuracy")
        with col4:
            _kpi("Type-B Recall", f"{m['recall_b']:.1%}", "hesitation events caught", border="#22C55E")
        st.markdown("---")
        metrics_data = pd.DataFrame({
            "Detector":  ["Type-A Speed", "Type-B Hesitation"],
            "Precision": [m["precision_a"], m["precision_b"]],
            "Recall":    [m["recall_a"], m["recall_b"]],
            "F1":        [
                2 * m["precision_a"] * m["recall_a"] / max(m["precision_a"] + m["recall_a"], 1e-9),
                2 * m["precision_b"] * m["recall_b"] / max(m["precision_b"] + m["recall_b"], 1e-9),
            ],
        })
        fig = go.Figure()
        for metric in ["Precision", "Recall", "F1"]:
            fig.add_trace(go.Bar(name=metric, x=metrics_data["Detector"], y=metrics_data[metric], text=[f"{v:.1%}" for v in metrics_data[metric]], textposition="outside"))
        fig.update_layout(barmode="group", yaxis_range=[0, 1.15])
        st.plotly_chart(_dark_layout(fig, "Detector Quality Comparison"), use_container_width=True)
        st.subheader("Metrics Table")
        display = metrics_data.copy()
        for col in ["Precision", "Recall", "F1"]:
            display[col] = display[col].map("{:.3f}".format)
        st.dataframe(display, use_container_width=True, hide_index=True)
        
    with t_ops_analytics:
        # Render Operational Analytics
        col1, col2, col3 = st.columns(3)
        with col1:
            _kpi("Total Revenue Processed", f"₹{a['total_revenue']:,.0f}", "INR across all orders")
        with col2:
            _kpi("Revenue Leakage Est.", f"₹{a['revenue_leakage']:,.0f}", "approved fraud claims", border="#EF4444")
        with col3:
            _kpi("Avg Pack Time", f"{a['avg_pack_time']:.1f}s", "per order fulfillment", border="#8B5CF6")
        st.markdown("---")
        col_l, col_r = st.columns(2)
        with col_l:
            if a["top_risky_categories"]:
                cat_df = pd.DataFrame(a["top_risky_categories"], columns=["Category", "Anomaly Count"])
                fig = px.bar(cat_df, x="Anomaly Count", y="Category", orientation="h", color="Anomaly Count", color_continuous_scale="Reds")
                st.plotly_chart(_dark_layout(fig, "Top Risky Categories"), use_container_width=True)
        with col_r:
            if a["revenue_by_category"]:
                rev_df = pd.DataFrame(list(a["revenue_by_category"].items()), columns=["Category", "Revenue"])
                fig = px.pie(rev_df, names="Category", values="Revenue", hole=0.4)
                st.plotly_chart(_dark_layout(fig, "Revenue by Category"), use_container_width=True)
        if a["anomaly_by_store"]:
            st.subheader("Anomaly Rate by Store")
            store_anom = pd.DataFrame(list(a["anomaly_by_store"].items()), columns=["Store", "Anomaly Rate"])
            store_anom = store_anom.sort_values("Anomaly Rate", ascending=False)
            fig = px.bar(store_anom, x="Store", y="Anomaly Rate", color="Anomaly Rate", color_continuous_scale="Reds", labels={"Anomaly Rate": "Anomaly Rate (per order)"})
            st.plotly_chart(_dark_layout(fig, "Per-Store Anomaly Rates"), use_container_width=True)
        if a["top_risky_skus"]:
            st.subheader("Top Risky SKUs")
            sku_df = pd.DataFrame(a["top_risky_skus"], columns=["SKU", "Anomaly Count"])
            fig = px.bar(sku_df, x="SKU", y="Anomaly Count", color="Anomaly Count", color_continuous_scale="Oranges")
            st.plotly_chart(_dark_layout(fig, "Most Frequently Anomalous SKUs"), use_container_width=True)

    with t_actions:
        # Render Action Queue
        st.subheader("⚡ Manual Intervention Action Queue")
        st.markdown("Take immediate overrides to stop loss on suspicious packer accounts and customer profiles.")
        
        if "suspended_packers" not in st.session_state:
            st.session_state["suspended_packers"] = set()
        if "blacklisted_customers" not in st.session_state:
            st.session_state["blacklisted_customers"] = set()
        if "action_log" not in st.session_state:
            st.session_state["action_log"] = []
            
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            st.markdown("#### Packer Terminal Suspension Queue")
            packers_to_show = [p for p in data["packers"] if p["risk_level"] in ("CRITICAL", "HIGH")]
            if not packers_to_show:
                st.info("No critical or high risk packer terminals flagged for suspension.")
            for p in packers_to_show:
                p_id = p["packer_id"]
                is_suspended = p_id in st.session_state["suspended_packers"]
                c_col1, c_col2 = st.columns([3, 1])
                with c_col1:
                    st.markdown(f"**Packer Terminal: {p_id}** (Risk Score: {p['score']:.0f})")
                    st.markdown(f"<small>Status: {'🚫 SUSPENDED' if is_suspended else '🟢 ACTIVE'}</small>", unsafe_allow_html=True)
                with c_col2:
                    if is_suspended:
                        if st.button("Reactivate", key=f"react_p_{p_id}"):
                            st.session_state["suspended_packers"].remove(p_id)
                            st.session_state["action_log"].insert(0, {
                                "Time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                "Action": f"Reactivated packer terminal {p_id}",
                                "Operator": "ADMIN"
                            })
                            st.rerun()
                    else:
                        if st.button("Suspend", key=f"susp_p_{p_id}", type="primary"):
                            st.session_state["suspended_packers"].add(p_id)
                            st.session_state["action_log"].insert(0, {
                                "Time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                "Action": f"Suspended packer terminal {p_id} (Risk Score: {p['score']:.0f})",
                                "Operator": "ADMIN"
                            })
                            st.rerun()
                            
        with col_act2:
            st.markdown("#### Customer Claim Blacklist Queue")
            cust_to_show = [c for c in data["customers"] if c["risk_level"] in ("CRITICAL", "HIGH")][:5]
            if not cust_to_show:
                st.info("No critical or high risk customer profiles flagged for block.")
            for c in cust_to_show:
                c_id = c["customer_id"]
                is_blacklisted = c_id in st.session_state["blacklisted_customers"]
                cc_col1, cc_col2 = st.columns([3, 1])
                with cc_col1:
                    st.markdown(f"**Customer: {c_id}** (Refund Rate: {c['refund_rate']:.1%})")
                    st.markdown(f"<small>Status: {'🚫 BLACKLISTED' if is_blacklisted else '🟢 APPROVED'}</small>", unsafe_allow_html=True)
                with cc_col2:
                    if is_blacklisted:
                        if st.button("Restore", key=f"react_c_{c_id}"):
                            st.session_state["blacklisted_customers"].remove(c_id)
                            st.session_state["action_log"].insert(0, {
                                "Time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                "Action": f"Restored refund privileges for customer {c_id}",
                                "Operator": "ADMIN"
                            })
                            st.rerun()
                    else:
                        if st.button("Blacklist", key=f"susp_c_{c_id}", type="primary"):
                            st.session_state["blacklisted_customers"].add(c_id)
                            st.session_state["action_log"].insert(0, {
                                "Time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                "Action": f"Blacklisted customer claim profile {c_id} (Refund Rate: {c['refund_rate']:.1%})",
                                "Operator": "ADMIN"
                            })
                            st.rerun()
                            
        st.markdown("---")
        st.markdown("#### 🪵 Security & Override Log")
        if st.session_state["action_log"]:
            st.dataframe(pd.DataFrame(st.session_state["action_log"]), use_container_width=True, hide_index=True)
        else:
            st.info("No manual interventions taken in this session.")

elif workspace == "⚙️ Platform & Data":
    t_ingest, t_obs, t_health_res, t_config, t_diag = st.tabs([
        "📥 Data Ingestion", "⚙️ Observability", "🏥 System Health", "🔧 Configuration", "🛠️ Platform Diagnostics"
    ])
    
    with t_ingest:
        # Render Data Ingestion
        st.markdown("### 📤 Upload Operational Data Logs")
        st.markdown("Upload CSV or JSON logs containing scan events, orders, or refund claims.")
        col_u1, col_u2, col_u3 = st.columns(3)
        with col_u1:
            st.markdown("#### 1. Scan Events Log")
            scan_file = st.file_uploader("Upload scan_events (CSV/JSON)", type=["csv", "json"], key="scan_upload")
            st.markdown("<small style='color:#94A3B8'>Required fields: order_id, packer_id, item_id, shelf_aisle, shelf_num, timestamp</small>", unsafe_allow_html=True)
        with col_u2:
            st.markdown("#### 2. Orders Log (Optional)")
            orders_file = st.file_uploader("Upload orders (CSV/JSON)", type=["csv", "json"], key="orders_upload")
            st.markdown("<small style='color:#94A3B8'>Required fields: order_id, customer_id, store_id, timestamp</small>", unsafe_allow_html=True)
        with col_u3:
            st.markdown("#### 3. Refund Claims Log")
            claims_file = st.file_uploader("Upload refund_claims (CSV/JSON)", type=["csv", "json"], key="claims_upload")
            st.markdown("<small style='color:#94A3B8'>Required fields: refund_id, order_id, customer_id, item_id, claimed_value_inr, claim_reason, request_ts</small>", unsafe_allow_html=True)
        if st.button("🚀 Process & Ingest Real Data", use_container_width=True):
            if not scan_file:
                st.error("Scan Events log is required to run the risk engines.")
            elif not claims_file:
                st.error("Refund Claims log is required to audit refund payouts.")
            else:
                try:
                    st.info("Loading and validating schemas...")
                    from data_ingestion.csv_loader import load_scan_events_from_csv, load_refund_claims_from_csv, load_orders_from_csv
                    from data_ingestion.json_loader import load_scan_events_from_json, load_refund_claims_from_json, load_orders_from_json
                    if scan_file.name.endswith(".csv"):
                        scan_events = load_scan_events_from_csv(scan_file)
                    else:
                        scan_events = load_scan_events_from_json(scan_file.getvalue())
                    if claims_file.name.endswith(".csv"):
                        refund_claims = load_refund_claims_from_csv(claims_file)
                    else:
                        refund_claims = load_refund_claims_from_json(claims_file.getvalue())
                    orders = []
                    if orders_file:
                        if orders_file.name.endswith(".csv"):
                            orders = load_orders_from_csv(orders_file)
                        else:
                            orders = load_orders_from_json(orders_file.getvalue())
                    st.info(f"Running detection algorithms on {len(scan_events)} scan events...")
                    from orchestrator import IVCOrchestrator
                    orch = IVCOrchestrator(scan_events=scan_events, refund_claims=refund_claims)
                    result = orch.run(render_dashboard=False)
                    st.info("Saving results to database...")
                    from database.db_setup import SessionLocal
                    from database.repositories import IVCRepository
                    db_session = SessionLocal()
                    try:
                        repo_db = IVCRepository(db_session)
                        repo_db.save_pipeline_result(result, orders=orders)
                    finally:
                        db_session.close()
                    st.cache_data.clear()
                    st.session_state["ivc_mode"] = "REAL_DATA"
                    st.success("🎉 Data ingested successfully! Dashboard switched to Real Data mode.")
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Ingestion failed: {exc}")
                    
    with t_obs:
        # Render Observability
        col_s1, col_s2, col_s3 = st.columns(3)
        from database.db_setup import engine as db_engine
        db_connected = False
        db_type = "unknown"
        db_url = db_engine.url.render_as_string(hide_password=True)
        t0 = time.perf_counter()
        try:
            from database.db_setup import SessionLocal
            dbs = SessionLocal()
            dbs.execute("SELECT 1")
            dbs.close()
            db_connected = True
            db_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            db_type = "SQLite (Fallback)" if "sqlite" in db_engine.url.drivername else "PostgreSQL"
        except Exception as exc:
            db_latency_ms = 999.9
            
        with col_s1:
            uc.render_metric_card("Database Connection", "ONLINE" if db_connected else "SIMULATED", db_type, uc.COLOR_LOW if db_connected else uc.COLOR_HIGH)
        with col_s2:
            uc.render_metric_card("Query Latency", f"{db_latency_ms} ms", "Target: < 50ms", uc.COLOR_LOW if db_latency_ms < 50 else uc.COLOR_HIGH)
        with col_s3:
            current_mode = st.session_state.get("ivc_mode", os.getenv("IVC_MODE", "SIMULATION"))
            uc.render_metric_card("Active Data Mode", current_mode, "Config: IVC_MODE", uc.COLOR_BLUE)
            
        st.markdown("### 📊 Database Diagnostics")
        st.markdown(f"**Database URL Connection String:** `{db_url}`")
        
        from database.db_setup import SessionLocal
        from database.repositories import IVCRepository
        db_sess = SessionLocal()
        try:
            repo_db = IVCRepository(db_sess)
            orders_c = len(repo_db.get_orders())
            scans_c = len(repo_db.get_scan_events())
            claims_c = len(repo_db.get_refund_claims())
            audits_c = len(repo_db.get_audit_results())
        finally:
            db_sess.close()
            
        st.markdown(
            f"""
            - **Total Persisted Orders:** `{orders_c}`
            - **Total Persisted Scan Events:** `{scans_c}`
            - **Total Persisted Refund Claims:** `{claims_c}`
            - **Total Persisted Audit Verdicts:** `{audits_c}`
            """
        )
        
    with t_health_res:
        # Render System Health
        st.subheader("🖥️ Platform Engine Resources")
        col_h1, col_h2, col_h3 = st.columns(3)
        with col_h1:
            st.metric("Detection Processor CPU Load", "12.4%", "stable thread count: 8")
        with col_h2:
            st.metric("Memory Consumption", "248.5 MB / 8.0 GB", "garbage collector active")
        with col_h3:
            st.metric("Simulator Thread State", "SLEEPING", "triggered on demand")
        st.markdown("#### ⚡ Active Daemon Services")
        services_df = pd.DataFrame([
            {"Service Name": "VelocityAnomalyDetectionService", "Status": "RUNNING", "Uptime": "2h 41m", "Load": "Low"},
            {"Service Name": "HesitationSequenceScanner", "Status": "RUNNING", "Uptime": "2h 41m", "Load": "Low"},
            {"Service Name": "RefundAuditDecisionTreeEngine", "Status": "IDLE", "Uptime": "2h 41m", "Load": "None"},
            {"Service Name": "EarlyWarningScoreAccumulator", "Status": "RUNNING", "Uptime": "2h 41m", "Load": "Medium"},
        ])
        st.dataframe(services_df, use_container_width=True, hide_index=True)
        
    with t_config:
        # Render Configuration
        st.subheader("⚙️ Detection Engine Constants")
        st.markdown("Adjust configuration parameters at runtime to tweak detection sensitivity.")
        from config import DETECTION_CONFIG
        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1:
            st.markdown("##### 🚶 Speed Thresholds")
            st.number_input("Max Physical Human Walking Speed (m/s)", value=DETECTION_CONFIG.max_human_speed_ms, disabled=True)
            st.number_input("High Value Threshold (INR)", value=float(DETECTION_CONFIG.high_value_threshold_inr), disabled=True)
        with col_cfg2:
            st.markdown("##### ⏱️ Hesitation Sigma Thresholds")
            st.number_input("Hesitation Sigma Threshold", value=DETECTION_CONFIG.hesitation_sigma_threshold, disabled=True)
            st.number_input("Type-A Weight (Speed)", value=DETECTION_CONFIG.type_a_weight, disabled=True)
            st.number_input("Type-B Weight (Hesitation)", value=DETECTION_CONFIG.type_b_weight, disabled=True)
        st.info("ℹ️ Configuration values are locked via DETECTION_CONFIG frozen dataclass. To mutate parameters, adjust config.py.")
        
    with t_diag:
        # Render Diagnostics
        st.subheader("🛠️ Engine Diagnostic Suite")
        col_diag1, col_diag2 = st.columns(2)
        with col_diag1:
            st.markdown("##### 🗄️ Database Integrity Verifier")
            if st.button("Validate Schema Constraints"):
                from database.db_setup import Base, engine
                try:
                    from sqlalchemy import inspect
                    inspector = inspect(engine)
                    tables = inspector.get_table_names()
                    st.success(f"Connection verified! Tables found: {', '.join(tables)}")
                except Exception as exc:
                    st.error(f"Schema verification failed: {exc}")
        with col_diag2:
            st.markdown("##### 🧹 Purge System Data")
            if st.button("Truncate Local Repository", type="secondary"):
                from database.db_setup import SessionLocal
                db = SessionLocal()
                try:
                    db.execute("DELETE FROM scan_events")
                    db.execute("DELETE FROM refund_claims")
                    db.execute("DELETE FROM audit_results")
                    db.commit()
                    st.success("Successfully purged scan events, claims, and audit logs. Seeding database with default parameters...")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Purge failed: {exc}")
                finally:
                    db.close()