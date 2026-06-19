"""
ui_components.py
================
Unified design system, color tokens, custom CSS injector, and reusable UI components.
"""

from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

# ── Color Palette Standardisation ──
COLOR_CRITICAL = "#EF4444"  # soft crimson
COLOR_HIGH = "#F97316"      # amber-orange
COLOR_MEDIUM = "#EAB308"    # yellow-gold
COLOR_LOW = "#10B981"       # emerald green
COLOR_BLUE = "#3B82F6"      # steel blue
COLOR_ROSE = "#F43F5E"      # rose red for declining

RISK_COLORS = {
    "CRITICAL": COLOR_CRITICAL,
    "HIGH": COLOR_HIGH,
    "MEDIUM": COLOR_MEDIUM,
    "LOW": COLOR_LOW,
}

WARNING_COLORS = {
    "CRITICAL": COLOR_CRITICAL,
    "HIGH_RISK": COLOR_HIGH,
    "WATCHLIST": COLOR_MEDIUM,
    "NORMAL": COLOR_LOW,
}

HEALTH_COLORS = {
    "HEALTHY": COLOR_LOW,
    "STABLE": COLOR_BLUE,
    "DECLINING": COLOR_ROSE,
    "CRITICAL": COLOR_CRITICAL,
}

# ── CSS Injection ──
def render_custom_css() -> None:
    st.markdown("""
    <style>
        /* Google Fonts Import */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

        /* Global Theme */
        html, body, [data-testid="stAppViewContainer"] {
            font-family: 'Inter', sans-serif;
            background-color: #080D1A !important;
            color: #E2E8F0 !important;
        }

        /* Sidebar Styling */
        section[data-testid="stSidebar"] {
            background-color: #0E1629 !important;
            border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
        }
        section[data-testid="stSidebar"] hr {
            border-color: rgba(255, 255, 255, 0.08) !important;
        }

        /* Hide Default Header & Footer */
        header[data-testid="stHeader"] {
            background: rgba(8, 13, 26, 0.6) !important;
            backdrop-filter: blur(8px) !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03) !important;
        }
        footer {
            visibility: hidden !important;
            display: none !important;
        }

        /* Metric Card styling */
        .ds-metric-card {
            background: #121B2F !important;
            border: 1px solid rgba(255, 255, 255, 0.06) !important;
            border-left: 4px solid #3B82F6 !important;
            border-radius: 8px !important;
            padding: 16px 20px !important;
            box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.3) !important;
            transition: all 0.2s ease-in-out !important;
            margin-bottom: 16px;
        }
        .ds-metric-card:hover {
            border-color: rgba(59, 130, 246, 0.4) !important;
            transform: translateY(-2px) !important;
            box-shadow: 0 8px 30px -4px rgba(0, 0, 0, 0.5) !important;
        }
        .ds-metric-label {
            font-size: 11px !important;
            text-transform: uppercase !important;
            letter-spacing: 1.5px !important;
            color: #94A3B8 !important;
            font-weight: 600 !important;
            opacity: 0.9 !important;
            margin-bottom: 4px;
        }
        .ds-metric-value {
            font-family: 'JetBrains Mono', monospace !important;
            font-size: 28px !important;
            font-weight: 700 !important;
            letter-spacing: -0.5px !important;
            color: #F8FAFC !important;
            line-height: 1.2 !important;
        }
        .ds-metric-subtext {
            font-size: 11px !important;
            color: #64748B !important;
            margin-top: 6px !important;
            display: flex;
            align-items: center;
            gap: 4px;
        }

        /* Standardized Badges */
        .ds-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            border: 1px solid transparent;
            font-family: 'JetBrains Mono', monospace;
        }
        .ds-badge-critical {
            background: rgba(239, 68, 68, 0.12) !important;
            color: #FCA5A5 !important;
            border-color: rgba(239, 68, 68, 0.3) !important;
        }
        .ds-badge-high {
            background: rgba(249, 115, 22, 0.12) !important;
            color: #FDBA74 !important;
            border-color: rgba(249, 115, 22, 0.3) !important;
        }
        .ds-badge-medium {
            background: rgba(234, 179, 8, 0.12) !important;
            color: #FDE047 !important;
            border-color: rgba(234, 179, 8, 0.3) !important;
        }
        .ds-badge-low {
            background: rgba(16, 185, 129, 0.12) !important;
            color: #A7F3D0 !important;
            border-color: rgba(16, 185, 129, 0.3) !important;
        }
        .ds-badge-blue {
            background: rgba(59, 130, 246, 0.12) !important;
            color: #93C5FD !important;
            border-color: rgba(59, 130, 246, 0.3) !important;
        }

        /* Executive Banner */
        .ds-health-banner {
            background: radial-gradient(circle at top left, #162440 0%, #101930 100%) !important;
            border: 1px solid rgba(59, 130, 246, 0.15) !important;
            border-left: 6px solid #10B981 !important;
            border-radius: 12px !important;
            padding: 24px 28px !important;
            margin-bottom: 24px !important;
            box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.4) !important;
        }
        .ds-health-banner-header {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: #10B981;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .ds-health-banner-title {
            font-size: 26px;
            font-weight: 800;
            color: #FFFFFF;
            margin-bottom: 8px;
        }
        .ds-health-banner-text {
            font-size: 14px;
            color: #94A3B8;
            line-height: 1.6;
        }

        /* Executive Insight Card */
        .ds-insight-card {
            background: #111A2E !important;
            border: 1px solid rgba(255, 255, 255, 0.05) !important;
            border-radius: 10px !important;
            padding: 20px !important;
            margin-bottom: 16px !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
        }
        .ds-insight-card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            padding-bottom: 10px;
            margin-bottom: 12px;
        }
        .ds-insight-title {
            font-size: 15px;
            font-weight: 700;
            color: #F8FAFC;
        }
        .ds-insight-row {
            display: flex;
            font-size: 13px;
            margin-bottom: 6px;
        }
        .ds-insight-label {
            width: 100px;
            font-weight: 600;
            color: #64748B;
        }
        .ds-insight-value {
            flex-grow: 1;
            color: #CBD5E1;
        }
        .ds-insight-action-box {
            background: rgba(59, 130, 246, 0.08);
            border: 1px solid rgba(59, 130, 246, 0.2);
            padding: 10px 14px;
            border-radius: 6px;
            margin-top: 10px;
            font-size: 12.5px;
            color: #93C5FD;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        /* Custom Callout Box (Warning/Alert) */
        .ds-callout {
            background: #1B1824 !important;
            border: 1px solid rgba(249, 115, 22, 0.15) !important;
            border-left: 4px solid #F97316 !important;
            border-radius: 8px !important;
            padding: 16px 20px !important;
            margin-bottom: 16px !important;
        }

        /* Tabs custom override */
        div[data-baseweb="tab-list"] {
            gap: 8px;
            background-color: transparent !important;
        }
        button[data-baseweb="tab"] {
            background-color: #111A2E !important;
            border: 1px solid rgba(255, 255, 255, 0.05) !important;
            border-radius: 6px 6px 0px 0px !important;
            color: #94A3B8 !important;
            padding: 8px 16px !important;
            height: auto !important;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            background-color: #1E293B !important;
            border-bottom: 2px solid #3B82F6 !important;
            color: #FFFFFF !important;
        }

        /* General streamlit overrides */
        .stDataFrame div {
            font-size: 13px !important;
        }
    </style>
    """, unsafe_allow_html=True)

# ── Primitives ──

def render_metric_card(
    label: str,
    value: str,
    subtext: str | None = None,
    border_color: str = COLOR_BLUE,
    trend_val: float | None = None,
    trend_direction: str = "up"
) -> None:
    """Renders a beautifully styled KPI Metric Card."""
    trend_html = ""
    if trend_val is not None:
        color = COLOR_LOW if (trend_direction == "up" and trend_val >= 0) or (trend_direction == "down" and trend_val <= 0) else COLOR_CRITICAL
        arrow = "↑" if trend_val >= 0 else "↓"
        trend_html = f'<span style="color:{color}; font-weight:600; margin-left:4px;">{arrow} {abs(trend_val):+.1f}%</span>'

    subtext_html = ""
    if subtext:
        subtext_html = f'<div class="ds-metric-subtext">{subtext} {trend_html}</div>'

    st.markdown(
        f"""
        <div class="ds-metric-card" style="border-left-color: {border_color} !important;">
            <div class="ds-metric-label">{label}</div>
            <div class="ds-metric-value">{value}</div>
            {subtext_html}
        </div>
        """,
        unsafe_allow_html=True
    )

def render_risk_badge(level: str) -> str:
    """Returns the HTML string for a standardized risk badge."""
    level_upper = level.upper()
    if level_upper == "CRITICAL":
        return f'<span class="ds-badge ds-badge-critical">{level_upper}</span>'
    elif level_upper in ("HIGH", "HIGH_RISK"):
        return f'<span class="ds-badge ds-badge-high">{level_upper}</span>'
    elif level_upper in ("MEDIUM", "WATCHLIST"):
        return f'<span class="ds-badge ds-badge-medium">{level_upper}</span>'
    else:
        return f'<span class="ds-badge ds-badge-low">{level_upper}</span>'

def render_executive_insight_card(
    title: str,
    context: str,
    reason: str,
    impact: str,
    action: str,
    risk_level: str = "MEDIUM"
) -> None:
    """Renders an action-oriented Operational Risk Insight Card (Phase 5)."""
    badge_html = render_risk_badge(risk_level)
    
    st.markdown(
        f"""
        <div class="ds-insight-card">
            <div class="ds-insight-card-header">
                <span class="ds-insight-title">{title}</span>
                {badge_html}
            </div>
            <div class="ds-insight-row">
                <div class="ds-insight-label">Context</div>
                <div class="ds-insight-value">{context}</div>
            </div>
            <div class="ds-insight-row">
                <div class="ds-insight-label">Reason</div>
                <div class="ds-insight-value">{reason}</div>
            </div>
            <div class="ds-insight-row">
                <div class="ds-insight-label">Impact</div>
                <div class="ds-insight-value" style="color: {COLOR_CRITICAL}; font-weight:600;">{impact}</div>
            </div>
            <div class="ds-insight-action-box">
                🛡️ <strong>Action Required:</strong> {action}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_warning_card(message: str, warning_level: str) -> None:
    """Renders an Early Warning System alert card."""
    color = WARNING_COLORS.get(warning_level, COLOR_BLUE)
    badge_html = render_risk_badge(warning_level)
    
    st.markdown(
        f"""
        <div class="ds-callout" style="border-left-color: {color} !important;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <strong style="color:{COLOR_HIGH}; font-size:13px; text-transform:uppercase; letter-spacing:1px;">Early Warning Signal</strong>
                {badge_html}
            </div>
            <div style="font-size:13.5px; color:#E2E8F0; line-height:1.5;">{message}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_forecast_card(
    title: str,
    prediction: str,
    confidence: str,
    risk_level: str,
    expected_change: str,
    narrative: str
) -> None:
    """Renders a forecast summary card (Phase 7)."""
    badge_html = render_risk_badge(risk_level)
    conf_color = COLOR_LOW if confidence.upper() == "HIGH" else (COLOR_MEDIUM if confidence.upper() == "MEDIUM" else COLOR_HIGH)
    
    st.markdown(
        f"""
        <div class="ds-insight-card" style="border-left: 4px solid #8B5CF6 !important;">
            <div class="ds-insight-card-header">
                <span class="ds-insight-title">🔮 Risk Forecast: {title}</span>
                {badge_html}
            </div>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 12px; background: rgba(0,0,0,0.15); padding: 12px; border-radius: 6px;">
                <div style="text-align:center;">
                    <div style="font-size:10px; color:#64748B; text-transform:uppercase; font-weight:600;">Prediction</div>
                    <div style="font-family:'JetBrains Mono', monospace; font-size:18px; font-weight:700; color:#F8FAFC;">{prediction}</div>
                </div>
                <div style="text-align:center;">
                    <div style="font-size:10px; color:#64748B; text-transform:uppercase; font-weight:600;">Confidence</div>
                    <div style="font-size:14px; font-weight:700; color:{conf_color}; margin-top:3px;">{confidence}</div>
                </div>
                <div style="text-align:center;">
                    <div style="font-size:10px; color:#64748B; text-transform:uppercase; font-weight:600;">Change</div>
                    <div style="font-family:'JetBrains Mono', monospace; font-size:16px; font-weight:700; color:{COLOR_CRITICAL if '+' in expected_change else COLOR_LOW};">{expected_change}</div>
                </div>
            </div>
            <div style="font-size:13px; color:#94A3B8; line-height:1.5;">{narrative}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_health_card(
    score: float,
    previous_score: float,
    change: float,
    status: str,
    summary: str
) -> None:
    """Renders the Network Health Scorecard (Phase 8)."""
    status_color = HEALTH_COLORS.get(status.upper(), COLOR_BLUE)
    change_color = COLOR_LOW if change >= 0 else COLOR_CRITICAL
    change_arrow = "↑" if change >= 0 else "↓"
    
    st.markdown(
        f"""
        <div class="ds-health-banner" style="border-left-color: {status_color} !important;">
            <div class="ds-health-banner-header">Network Health Scorecard</div>
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; margin-bottom:12px;">
                <div style="font-size:48px; font-family:'JetBrains Mono', monospace; font-weight:800; color:#FFFFFF; margin-right:20px;">
                    {score:.1f} <span style="font-size:16px; color:#64748B; font-weight:500;">/ 100</span>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:11px; color:#64748B; text-transform:uppercase; font-weight:600;">WoW Shift</div>
                    <div style="font-family:'JetBrains Mono', monospace; font-size:18px; font-weight:700; color:{change_color};">
                        {change_arrow} {abs(change):+.1f} pts
                    </div>
                </div>
            </div>
            <div class="ds-health-banner-text">{summary}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ── Chart Styling Helper ──
def apply_chart_theme(fig: go.Figure, title: str = "", show_legend: bool = True) -> go.Figure:
    """Applies a consistent dark enterprise design system theme to a Plotly figure."""
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(color="#F8FAFC", size=15, family="Inter"),
            pad=dict(b=10)
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94A3B8", family="Inter"),
        legend=dict(
            bgcolor="rgba(13, 21, 39, 0.8)",
            font=dict(color="#CBD5E1", size=11),
            bordercolor="rgba(255, 255, 255, 0.05)",
            borderwidth=1,
        ) if show_legend else dict(visible=False),
        margin=dict(t=45, b=30, l=40, r=20),
        hoverlabel=dict(
            bgcolor="#1E293B",
            font_size=12,
            font_family="Inter",
            font_color="#F8FAFC"
        )
    )
    fig.update_xaxes(
        gridcolor="rgba(255, 255, 255, 0.05)",
        zerolinecolor="rgba(255, 255, 255, 0.08)",
        tickfont=dict(size=11, color="#64748B"),
        title_font=dict(size=12, color="#94A3B8")
    )
    fig.update_yaxes(
        gridcolor="rgba(255, 255, 255, 0.05)",
        zerolinecolor="rgba(255, 255, 255, 0.08)",
        tickfont=dict(size=11, color="#64748B"),
        title_font=dict(size=12, color="#94A3B8")
    )
    return fig

# ── Reusable Layouts ─────────────────────────────────────────────────────────

def render_workspace_layout(title: str, subtitle: str) -> None:
    """Renders a standard workspace hero header with premium typography."""
    st.markdown(
        f"""
        <div style="margin-bottom: 24px; padding-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.06);">
            <h1 style="margin: 0; font-size: 30px; font-weight: 800; letter-spacing: -0.5px; color: #F8FAFC;">{title}</h1>
            <p style="margin: 4px 0 0 0; font-size: 13.5px; color: #94A3B8;">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_grid_layout(cols: int, render_fns: list[callable]) -> None:
    """Arranges layout callbacks into N equal columns dynamically."""
    columns = st.columns(cols)
    for idx, fn in enumerate(render_fns):
        col_idx = idx % cols
        with columns[col_idx]:
            fn()

# ── Reusable Component Aliases & New Additions ───────────────────────────────

def render_narrative_card(title: str, content: str, time_info: str | None = None) -> None:
    """Renders executive operational narratives in a high-contrast container."""
    time_html = f'<span style="font-size:11px; color:#64748B;">{time_info}</span>' if time_info else ""
    st.markdown(
        f"""
        <div class="ds-insight-card" style="border-left: 4px solid #10B981 !important;">
            <div class="ds-insight-card-header">
                <span class="ds-insight-title">📖 {title}</span>
                {time_html}
            </div>
            <div style="font-size: 13.5px; color: #CBD5E1; line-height: 1.6; white-space: pre-line;">
                {content}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_action_card(title: str, entity_id: str, action_required: str, severity: str = "HIGH") -> None:
    """Renders action queue cards flagging required manual overrides."""
    badge = render_risk_badge(severity)
    st.markdown(
        f"""
        <div class="ds-insight-card" style="border-left: 4px solid #EF4444 !important; background: #1B1220 !important;">
            <div class="ds-insight-card-header">
                <span class="ds-insight-title">⚡ {title} ({entity_id})</span>
                {badge}
            </div>
            <div style="font-size:13px; color:#E2E8F0; margin-bottom:12px; line-height:1.5;">🚨 {action_required}</div>
            <div style="font-size:11px; color:#94A3B8; font-weight:600; text-transform:uppercase; letter-spacing:0.5px;">Status: PENDING REVIEW</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_recommendation_card(title: str, description: str, priority: str = "MEDIUM") -> None:
    """Renders warning callouts for operations guidance."""
    badge = render_risk_badge(priority)
    st.markdown(
        f"""
        <div class="ds-insight-card" style="border-left: 4px solid #F97316 !important;">
            <div class="ds-insight-card-header">
                <span class="ds-insight-title">💡 Action Item: {title}</span>
                {badge}
            </div>
            <div style="font-size:13px; color:#CBD5E1; line-height:1.5;">{description}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_health_indicator(score: float) -> None:
    """Renders a simple visual SLA indicator badge for network health."""
    color = COLOR_LOW if score >= 85 else (COLOR_MEDIUM if score >= 70 else COLOR_CRITICAL)
    st.markdown(
        f"""
        <div style="text-align: center; padding: 16px; background: #121B2F; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); margin-bottom:16px;">
            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: #94A3B8; font-weight:600; margin-bottom: 6px;">Network SLA Status</div>
            <div style="font-size: 36px; font-family: 'JetBrains Mono', monospace; font-weight: 800; color: {color};">{score:.1f}%</div>
            <div style="font-size: 12px; color: #64748B; margin-top: 4px;">SLA Status: {"OPERATIONAL" if score >= 80 else "DEGRADED"}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

