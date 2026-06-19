"""
explainability/explainability_dashboard.py
==========================================
Streamlit Explainability Center — Phase 7.

5 pages:
  1. Executive Overview
  2. Packer Explanations
  3. Customer Explanations
  4. Store Explanations
  5. Refund Decision Explanations
  6. Root Cause Analysis

This module ONLY renders. All business logic lives in explanation_engine.py.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from explainability.explanation_models import (
    ContributingFactor,
    CustomerExplanation,
    ExecutiveNarrative,
    PackerExplanation,
    RefundDecisionExplanation,
    RootCauseReport,
    ScoreBreakdown,
    StoreExplanation,
)
from explainability.explanation_engine import AllExplanations

import ui_components as uc

# ── Color palette mapping ──────────────────────────────────────────────────────
_RISK_COLOURS = uc.RISK_COLORS
_RISK_BG = {
    "CRITICAL": "rgba(239, 68, 68, 0.15)",
    "HIGH":     "rgba(249, 115, 22, 0.15)",
    "MEDIUM":   "rgba(234, 179, 8, 0.15)",
    "LOW":      "rgba(16, 185, 129, 0.15)",
}


# ── Shared UI helpers ─────────────────────────────────────────────────────────

def _risk_badge(level: str) -> str:
    return uc.render_risk_badge(level)


def _metric_card(label: str, value: str, sub: str = "", colour: str = "") -> None:
    border = colour if colour else uc.COLOR_BLUE
    uc.render_metric_card(label, value, sub, border_color=border)


def _score_bar_chart(breakdown: ScoreBreakdown, title: str = "Score breakdown") -> None:
    if not breakdown or not breakdown.components:
        return
    df = pd.DataFrame(
        [(k, v) for k, v in breakdown.components.items()],
        columns=["Component", "Points"],
    ).sort_values("Points", ascending=True)

    fig = px.bar(
        df, x="Points", y="Component", orientation="h",
        color="Component",
        color_discrete_sequence=[uc.COLOR_BLUE, uc.COLOR_LOW, uc.COLOR_HIGH, uc.COLOR_CRITICAL],
        title=title,
    )
    fig.update_layout(
        showlegend=False, height=200 + len(df) * 30,
        margin=dict(l=0, r=0, t=36, b=0),
    )
    fig = uc.apply_chart_theme(fig, title)
    st.plotly_chart(fig, use_container_width=True)


def _factor_table(factors: list[ContributingFactor]) -> None:
    if not factors:
        return
    rows = []
    for f in factors:
        marker = "🔴 Primary" if f.is_primary else "•"
        rows.append({"": marker, "Factor": f.label, "Weight": f"{f.weight:.1f}%"})
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


# ── Page 0: Executive Overview ────────────────────────────────────────────────

def render_executive_overview(exp: AllExplanations) -> None:
    n = exp.narrative
    rc = exp.root_cause

    st.markdown(f"### {n.headline}")
    st.markdown("---")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _metric_card("Total anomalies", str(rc.total_anomalies))
    with c2:
        _metric_card("Revenue at risk", f"₹{rc.total_revenue_at_risk:,.0f}",
                     colour="#E24B4A")
    with c3:
        refunds_blocked = sum(1 for r in exp.refund if r.verdict == "REJECT")
        _metric_card("Refunds blocked", str(refunds_blocked))
    with c4:
        critical_packers = sum(
            1 for e in exp.packer.values() if e.risk_level == "CRITICAL"
        )
        _metric_card("Critical packers", str(critical_packers), colour="#E24B4A")

    st.markdown("#### Key findings")
    for finding in [n.store_finding, n.packer_finding,
                    n.customer_finding, n.refund_finding, n.sku_finding]:
        st.markdown(f"- {finding}")

    if n.recommended_actions:
        st.markdown("#### Recommended actions")
        for action in n.recommended_actions:
            st.markdown(f"✅ {action}")

    st.markdown("---")
    st.markdown("#### Network risk drivers")
    for driver in rc.drivers:
        with st.expander(
            f"#{driver.rank} — {driver.category}: **{driver.entity}** "
            f"({driver.share_pct}% of anomalies)"
        ):
            st.markdown(driver.narrative)
            col1, col2 = st.columns(2)
            col1.metric("Metric", driver.metric.replace("_", " ").title())
            col2.metric("Value", f"{driver.value:,.0f}")


# ── Page 1: Packer Explanations ───────────────────────────────────────────────

def render_packer_explanations(exp: AllExplanations) -> None:
    st.markdown("### Packer risk explanations")
    st.markdown(
        "Every packer risk score is decomposed into its contributing factors. "
        "No black-box rankings."
    )

    packer_list = sorted(exp.packer.values(), key=lambda p: -p.risk_score)
    if not packer_list:
        st.info("No packer violations detected in this run.")
        return

    # Summary table
    summary_data = [
        {
            "Packer": p.packer_id,
            "Risk level": p.risk_level,
            "Score": p.risk_score,
            "Type-A": p.type_a_count,
            "Type-B": p.type_b_count,
            "Anomaly share": f"{p.anomaly_share_pct}%",
            "Refund exposure": f"₹{p.refund_exposure_inr:,.0f}",
            "Primary driver": p.primary_driver[:60] + "…"
                              if len(p.primary_driver) > 60 else p.primary_driver,
        }
        for p in packer_list
    ]
    st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### Drill into a packer")
    selected = st.selectbox(
        "Select packer",
        options=[p.packer_id for p in packer_list],
        format_func=lambda pid: f"{pid} — {exp.packer[pid].risk_level} "
                                f"(score {exp.packer[pid].risk_score})",
    )
    if not selected:
        return

    p = exp.packer[selected]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _metric_card("Current Risk Score", str(p.risk_score),
                     colour=_RISK_COLOURS.get(p.risk_level, "#888"))
    with col2:
        _metric_card("Platform Average", f"{p.platform_avg_score:.1f}")
    with col3:
        diff_val = f"+{p.difference_pct:.1f}%" if p.difference_pct >= 0 else f"{p.difference_pct:.1f}%"
        _metric_card("Difference %", diff_val, colour="#E24B4A" if p.difference_pct > 0 else "#3B6D11")
    with col4:
        _metric_card("Percentile Rank", p.percentile_rank)

    col_pack2 = st.columns(4)
    with col_pack2[0]:
        _metric_card("Type-A violations", str(p.type_a_count))
    with col_pack2[1]:
        _metric_card("Type-B violations", str(p.type_b_count))
    with col_pack2[2]:
        _metric_card("Refund exposure", f"₹{p.refund_exposure_inr:,.0f}")
    with col_pack2[3]:
        _metric_card("Recommended Action", p.recommended_action)

    st.markdown(f"**Primary driver:** {p.primary_driver}")
    st.markdown(f"**Secondary driver:** {p.secondary_driver}")
    st.markdown(f"> {p.summary}")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("##### Contribution Breakdown")
        for k, v in p.contribution_breakdown.items():
            st.write(f"- **{k}**: {v}%")
        st.markdown("##### Contributing factors")
        _factor_table(p.contributing_factors)
    with col_r:
        if p.score_breakdown:
            _score_bar_chart(p.score_breakdown, "Score breakdown")

    st.markdown("##### Evidence")
    ev_df = pd.DataFrame(
        [(k, v) for k, v in p.evidence.items()],
        columns=["Signal", "Value"],
    )
    st.dataframe(ev_df, use_container_width=True, hide_index=True)


# ── Page 2: Customer Explanations ─────────────────────────────────────────────

def render_customer_explanations(exp: AllExplanations) -> None:
    st.markdown("### Customer fraud risk explanations")
    st.markdown(
        "Every customer risk score is decomposed into refund frequency, rate, "
        "high-value claims, and cumulative value."
    )

    cust_list = sorted(exp.customer.values(), key=lambda c: -c.risk_score)
    if not cust_list:
        st.info("No customer risk profiles in this run.")
        return

    # Summary table
    summary_data = [
        {
            "Customer": c.customer_id,
            "Risk level": c.risk_level,
            "Score": round(c.risk_score, 1),
            "Refunds": c.refund_count,
            "High-value claims": c.high_value_claim_count,
            "Refund rate": f"{round(c.refund_rate * 100, 1)}%",
            "vs. baseline": f"{c.refund_rate_multiplier}x",
            "Total claimed (₹)": f"₹{c.total_claim_value_inr:,.0f}",
        }
        for c in cust_list[:50]
    ]
    st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### Drill into a customer")
    selected = st.selectbox(
        "Select customer",
        options=[c.customer_id for c in cust_list],
        format_func=lambda cid: f"{cid} — {exp.customer[cid].risk_level} "
                                f"(score {round(exp.customer[cid].risk_score, 1)})",
    )
    if not selected:
        return
    c = exp.customer[selected]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _metric_card("Refund Rate", f"{round(c.refund_rate * 100, 1)}%",
                     colour=_RISK_COLOURS.get(c.risk_level, "#888"))
    with col2:
        _metric_card("Platform Average", f"{round(c.platform_avg_refund_rate * 100, 1)}%")
    with col3:
        diff_val = f"+{c.difference_pct:.1f}%" if c.difference_pct >= 0 else f"{c.difference_pct:.1f}%"
        _metric_card("Difference %", diff_val, colour="#E24B4A" if c.difference_pct > 0 else "#3B6D11")
    with col4:
        _metric_card("Risk Percentile", c.percentile_rank)

    col_cust2 = st.columns(4)
    with col_cust2[0]:
        _metric_card("Risk Score", str(round(c.risk_score, 1)))
    with col_cust2[1]:
        _metric_card("High Value Claims", str(c.high_value_claim_count))
    with col_cust2[2]:
        _metric_card("Total Claimed", f"₹{c.total_claim_value_inr:,.0f}")
    with col_cust2[3]:
        _metric_card("Recommended Action", c.recommended_action)

    st.markdown(f"**Reason:** {c.primary_driver}")
    st.markdown(f"> {c.summary}")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("##### Contributing factors")
        _factor_table(c.contributing_factors)
    with col_r:
        if c.score_breakdown:
            _score_bar_chart(c.score_breakdown, "Score breakdown")

    # Refund rate vs platform baseline
    fig = go.Figure(go.Bar(
        x=["This customer", "Platform average"],
        y=[round(c.refund_rate * 100, 1),
           round(c.platform_avg_refund_rate * 100, 1)],
        marker_color=["#E24B4A", "#378ADD"],
    ))
    fig.update_layout(
        title="Refund rate vs platform baseline (%)",
        height=260,
        margin=dict(l=0, r=0, t=36, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Page 3: Store Explanations ────────────────────────────────────────────────

def render_store_explanations(exp: AllExplanations) -> None:
    st.markdown("### Dark store risk explanations")
    st.markdown(
        "Each store's risk score is decomposed into refund rate, anomaly rate, "
        "Type-A/B events, and revenue at risk."
    )

    store_list = sorted(exp.store.values(), key=lambda s: -s.risk_score)
    if not store_list:
        st.info("No store risk profiles available.")
        return

    summary_data = [
        {
            "Store": s.store_id,
            "Risk level": s.risk_level,
            "Score": round(s.risk_score, 1),
            "Orders": s.orders_processed,
            "Type-A": s.type_a_events,
            "Type-B": s.type_b_events,
            "Refund claims": s.refund_claims,
            "Revenue at risk": f"₹{s.revenue_at_risk_inr:,.0f}",
            "High-risk packers": s.high_risk_packer_count,
            "Anomaly share": f"{s.anomaly_share_pct}%",
        }
        for s in store_list
    ]
    st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

    # Radar / bar comparison across stores
    st.markdown("---")
    stores_df = pd.DataFrame([
        {
            "Store": s.store_id,
            "Type-A events": s.type_a_events,
            "Type-B events": s.type_b_events,
            "Refund claims": s.refund_claims,
        }
        for s in store_list
    ])
    fig = px.bar(
        stores_df.melt(id_vars="Store", var_name="Signal", value_name="Count"),
        x="Store", y="Count", color="Signal", barmode="group",
        color_discrete_sequence=["#E24B4A", "#BA7517", "#185FA5"],
        title="Anomaly signal breakdown by store",
    )
    fig.update_layout(
        height=320, margin=dict(l=0, r=0, t=36, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("#### Drill into a store")
    selected = st.selectbox(
        "Select store",
        options=[s.store_id for s in store_list],
        format_func=lambda sid: f"{sid} — {exp.store[sid].risk_level} "
                                f"(score {round(exp.store[sid].risk_score, 1)})",
    )
    if not selected:
        return
    s = exp.store[selected]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _metric_card("Current Risk Score", f"{s.risk_score:.1f}",
                     colour=_RISK_COLOURS.get(s.risk_level, "#888"))
    with col2:
        _metric_card("Platform Average", f"{s.network_avg_score:.1f}")
    with col3:
        diff_val = f"+{s.difference_pct:.1f}%" if s.difference_pct >= 0 else f"{s.difference_pct:.1f}%"
        _metric_card("Difference %", diff_val, colour="#E24B4A" if s.difference_pct > 0 else "#3B6D11")
    with col4:
        _metric_card("Percentile Rank", s.percentile_rank)

    col_store2 = st.columns(4)
    with col_store2[0]:
        _metric_card("Anomaly Share", f"{s.anomaly_share_pct:.1f}%")
    with col_store2[1]:
        _metric_card("Revenue Exposure", f"₹{s.revenue_at_risk_inr:,.0f}")
    with col_store2[2]:
        _metric_card("High-risk Packers", str(s.high_risk_packer_count))
    with col_store2[3]:
        _metric_card("Recommended Action", s.recommended_action)

    st.markdown(f"**Primary Driver:** {s.primary_driver}")
    st.markdown(f"**Secondary Driver:** {s.secondary_driver}")
    st.markdown(f"> {s.summary}")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("##### Contributing factors")
        _factor_table(s.contributing_factors)
    with col_r:
        if s.score_breakdown:
            _score_bar_chart(s.score_breakdown, "Score breakdown")


# ── Page 4: Refund Decision Explanations ──────────────────────────────────────

def render_refund_explanations(exp: AllExplanations) -> None:
    st.markdown("### Refund decision explanations")
    st.markdown(
        "Every refund verdict is explained with confidence score, "
        "contributing signals, and audit reasons."
    )

    refund_list = exp.refund
    if not refund_list:
        st.info("No refund decisions in this run.")
        return

    # Filter controls
    col1, col2 = st.columns(2)
    with col1:
        verdict_filter = st.selectbox(
            "Filter by verdict", ["All", "REJECT", "APPROVE"]
        )
    with col2:
        min_conf = st.slider("Minimum confidence %", 0, 100, 0)

    filtered = [
        r for r in refund_list
        if (verdict_filter == "All" or r.verdict == verdict_filter)
        and r.confidence_pct >= min_conf
    ]
    st.markdown(f"Showing **{len(filtered)}** of {len(refund_list)} decisions")

    summary_data = [
        {
            "Refund ID": r.refund_id[:12] + "…",
            "Order": r.order_id,
            "Item": r.item_id,
            "Value (₹)": f"₹{r.claimed_value_inr:,.0f}",
            "Verdict": r.verdict,
            "Confidence": f"{r.confidence_pct:.0f}%",
            "Primary reason": r.primary_reason[:70] + "…"
                              if len(r.primary_reason) > 70 else r.primary_reason,
            "Was fraud": "✓" if r.was_fraud else "",
        }
        for r in filtered[:100]
    ]
    st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

    # Confidence distribution
    conf_df = pd.DataFrame(
        [(r.verdict, r.confidence_pct) for r in refund_list],
        columns=["Verdict", "Confidence"],
    )
    fig = px.histogram(
        conf_df, x="Confidence", color="Verdict",
        nbins=20, barmode="overlay",
        color_discrete_map={"REJECT": "#E24B4A", "APPROVE": "#378ADD"},
        title="Confidence distribution by verdict",
    )
    fig.update_layout(
        height=280, margin=dict(l=0, r=0, t=36, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("#### Drill into a refund decision")
    if not filtered:
        return
    selected_idx = st.selectbox(
        "Select refund",
        options=list(range(len(filtered))),
        format_func=lambda i: (
            f"{filtered[i].refund_id[:16]}… — "
            f"{filtered[i].verdict} ({filtered[i].confidence_pct:.0f}%)"
        ),
    )
    r = filtered[selected_idx]
    col1, col2, col3 = st.columns(3)
    with col1:
        colour = "#E24B4A" if r.verdict == "REJECT" else "#3B6D11"
        _metric_card("Decision", r.verdict, colour=colour)
    with col2:
        _metric_card("Confidence", f"{r.confidence_pct:.0f}%")
    with col3:
        _metric_card("Claimed Value", f"₹{r.claimed_value_inr:,.0f}")

    st.markdown(f"**Reasoning:** {r.primary_reason}")
    st.markdown(f"> {r.summary}")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("##### Reasoning Chain")
        for reason in r.reasons:
            st.markdown(f"- {reason}")
    with col_r:
        st.markdown("##### Evidence")
        scan_log_status = r.risk_signals.get("Scan log", "Present")
        type_a_status = r.risk_signals.get("Packer Type-A flag", "Absent")
        type_b_status = r.risk_signals.get("Packer Type-B flag", "Absent")
        packer_risk = r.risk_signals.get("Packer risk tier", "LOW")
        cust_history = r.risk_signals.get("Customer history", "Normal")

        ev_scan = "✓ Item scan exists" if scan_log_status == "Present" else "✗ Item scan missing"
        ev_anom = "✓ No anomaly detected" if (type_a_status == "Absent" and type_b_status == "Absent") else "✗ Packer anomaly flags detected"
        ev_packer = "✓ Packer risk low" if packer_risk in ("LOW", "MEDIUM", "No profile") else "✗ Packer risk elevated"
        ev_cust = "✓ Customer history normal" if cust_history == "Normal" else "✗ Customer history suspicious"

        st.markdown(f"**{ev_scan}**")
        st.markdown(f"**{ev_anom}**")
        st.markdown(f"**{ev_packer}**")
        st.markdown(f"**{ev_cust}**")


# ── Page 5: Root Cause Analysis ───────────────────────────────────────────────

def render_root_cause(exp: AllExplanations) -> None:
    rc = exp.root_cause
    st.markdown("### Root cause analysis")
    st.markdown(f"> {rc.executive_summary}")

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        _metric_card("Total anomalies", str(rc.total_anomalies))
    with col2:
        _metric_card("Revenue at risk", f"₹{rc.total_revenue_at_risk:,.0f}",
                     colour="#E24B4A")

    st.markdown("#### Ranked risk drivers")
    for driver in rc.drivers:
        with st.expander(
            f"#{driver.rank} {driver.category} — {driver.entity} "
            f"| {driver.share_pct}% share"
        ):
            st.markdown(driver.narrative)

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("#### Top risky SKUs")
        if rc.top_risky_skus:
            sku_df = pd.DataFrame(rc.top_risky_skus, columns=["SKU", "Violations"])
            fig = px.bar(
                sku_df, x="Violations", y="SKU", orientation="h",
                color_discrete_sequence=["#E24B4A"],
                title="Violations per SKU",
            )
            fig.update_layout(
                height=300, showlegend=False,
                margin=dict(l=0, r=0, t=36, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown("#### Top risky categories")
        if rc.top_risky_categories:
            cat_df = pd.DataFrame(rc.top_risky_categories, columns=["Category", "Violations"])
            fig = px.pie(
                cat_df, names="Category", values="Violations",
                color_discrete_sequence=px.colors.qualitative.Set2,
                title="Anomaly share by category",
            )
            fig.update_layout(
                height=300, margin=dict(l=0, r=0, t=36, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Top risky stores")
    if rc.top_risky_stores:
        store_df = pd.DataFrame(rc.top_risky_stores, columns=["Store", "Risk Score"])
        fig = px.bar(
            store_df, x="Store", y="Risk Score",
            color="Risk Score",
            color_continuous_scale=["#EAF3DE", "#E24B4A"],
            title="Store risk scores",
        )
        fig.update_layout(
            height=260, showlegend=False,
            margin=dict(l=0, r=0, t=36, b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)


# ── Main entry point ──────────────────────────────────────────────────────────

def render_explainability_center(exp: AllExplanations) -> None:
    """
    Main entry point called from streamlit_dashboard.py.
    Renders the full Explainability Center with sub-page navigation.
    """
    st.title("🔍 Explainability Center")
    st.markdown(
        "Every risk score explained. Every verdict justified. "
        "No black-box rankings."
    )

    page = st.radio(
        "Section",
        options=[
            "Executive Overview",
            "Packer Explanations",
            "Customer Explanations",
            "Store Explanations",
            "Refund Decision Explanations",
            "Root Cause Analysis",
        ],
        horizontal=True,
        label_visibility="collapsed",
    )
    st.markdown("---")

    if page == "Executive Overview":
        render_executive_overview(exp)
    elif page == "Packer Explanations":
        render_packer_explanations(exp)
    elif page == "Customer Explanations":
        render_customer_explanations(exp)
    elif page == "Store Explanations":
        render_store_explanations(exp)
    elif page == "Refund Decision Explanations":
        render_refund_explanations(exp)
    elif page == "Root Cause Analysis":
        render_root_cause(exp)