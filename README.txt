# 🛡️ IVC — Operational Risk Intelligence Platform for Quick Commerce

> **Transform fraud noise into operational intelligence.**  
> IVC detects inventory manipulation, identifies high-risk packers and customers, profiles dark stores, and quantifies revenue leakage — entirely from scan-log telemetry.

---

## Problem Statement

Quick commerce platforms (10-minute grocery delivery) operate hundreds of dark stores with 10–50 pickers working simultaneous orders. The combination of speed pressure, high-value SKUs, and thin staffing creates a unique fraud surface with three distinct attack vectors:

| Vector | Description | Business Impact |
|--------|-------------|-----------------|
| **Barcode Spoofing** | Packers claim to scan items they never physically picked | Inventory ghost stock, unverifiable fulfillment |
| **Dwell Theft** | Packers hesitate abnormally on premium items (perfumes, electronics) | Item disappears between scan and dispatch |
| **Refund Fraud** | Customers claim items were missing from correctly fulfilled orders | Direct revenue loss, chargeback risk |

Traditional threshold-based alerting misses spatially-aware anomalies. IVC uses **velocity-based physics** and **statistical baseline profiling** to surface signals that rule-engines cannot.

---

## Industry Context

Quick commerce in India (Zepto, Blinkit, Swiggy Instamart) processes 3–8M orders/day across 3,000+ dark stores. At even a 0.5% fraud rate on a ₹400 average order value, that's **₹60 lakh+ in daily exposure**. IVC provides the analytical infrastructure to close this gap.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         IVC v3.0.0                             │
│              Operational Risk Intelligence Platform             │
└────────────────────────────┬────────────────────────────────────┘
                             │
          ┌──────────────────▼──────────────────┐
          │          DarkStoreSimulator          │
          │  10 stores · 500 customers · 25 SKUs │
          └──────────────────┬──────────────────┘
                             │ ScanEvents + RefundClaims
          ┌──────────────────▼──────────────────┐
          │         Detection Layer              │
          │  ┌─────────────────────────────┐     │
          │  │ WalkingSpeedValidator (A)   │     │
          │  │ TimeHesitationDetector (B)  │     │
          │  └─────────────────────────────┘     │
          └──────────────────┬──────────────────┘
                             │ Violations + Annotated DF
     ┌───────────────────────┼───────────────────────┐
     │                       │                       │
     ▼                       ▼                       ▼
┌────────────┐    ┌───────────────────┐    ┌─────────────────┐
│PackerRisk  │    │CustomerRefund     │    │  DetectionMetrics│
│Scorer      │    │Auditor            │    │  Precision/Recall│
└────────────┘    └───────────────────┘    └─────────────────┘
     │                       │
     ▼                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Intelligence Engines                      │
│  ┌──────────────────┐  ┌───────────────┐  ┌──────────────┐  │
│  │CustomerRiskEngine│  │DarkStoreRisk  │  │Operational   │  │
│  │Phase 1           │  │Engine Phase 2 │  │Analytics Ph3 │  │
│  └──────────────────┘  └───────────────┘  └──────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │ PipelineResult
     ┌───────────────────────┼───────────────────────┐
     │                       │                       │
     ▼                       ▼                       ▼
┌──────────┐       ┌──────────────────┐    ┌──────────────┐
│ Console  │       │ Streamlit        │    │ Report       │
│Dashboard │       │ Dashboard (7 pg) │    │ Generator    │
└──────────┘       └──────────────────┘    └──────────────┘
```

---

## System Components

### Detection Layer

| File | Class | Purpose |
|------|-------|---------|
| `detectors.py` | `WalkingSpeedValidator` | Flags scans where physical movement was impossible |
| `detectors.py` | `TimeHesitationDetector` | Detects statistically abnormal dwell on high-value items |
| `auditors.py` | `CustomerRefundAuditor` | Cross-references refund claims against validated scan logs |
| `auditors.py` | `PackerRiskScorer` | Weighted composite risk score per packer |

### Intelligence Engines (v3.0)

| File | Class | Purpose |
|------|-------|---------|
| `customer_risk_engine.py` | `CustomerRiskEngine` | 4-factor weighted customer risk scoring |
| `store_risk_engine.py` | `DarkStoreRiskEngine` | Per-store risk profiles and rankings |
| `analytics_engine.py` | `OperationalAnalyticsEngine` | Platform-wide KPIs and leakage estimation |

### Platform Layer

| File | Purpose |
|------|---------|
| `orchestrator.py` | 12-step pipeline orchestration |
| `streamlit_dashboard.py` | 7-page interactive dashboard |
| `dashboard.py` | Console dashboard (preserved) |
| `report_generator.py` | CSV + JSON export |
| `benchmark.py` | Throughput and memory benchmarks |

---

## Detection Logic

### Type A — Barcode Spoofing (Speed Violation)

**Algorithm:**
1. Sort scan events by `(packer_id, order_id, timestamp)`.
2. Compute Euclidean distance from previous shelf using grid coordinates.
3. Calculate velocity: `distance_m / delta_seconds`.
4. Flag where `velocity > MAX_HUMAN_SPEED_MS` (default: 6.0 m/s).

**Why physics?** A human cannot move 16 metres in 0.3 seconds. Any scan claiming otherwise is either barcode spoofing or device cloning.

**Edge cases handled:** Zero-delta timestamps (→ infinite velocity, always flagged), cross-order boundaries (→ distance = 0, never flagged), missing coordinates (→ 0 distance, safe default).

### Type B — Dwell Theft (Hesitation Detection)

**Algorithm:**
1. Compute inter-scan gap seconds per `(packer, order)` group.
2. Build per-category baseline `(mean, std)` from speed-clean records.
3. Categories with < 5 samples fall back to store-wide baseline.
4. Flag high-value items where `gap > mean + 2.5σ`.

**Why statistical baseline?** A 45-second gap is normal near a dairy fridge but suspicious near a cosmetics shelf. Per-category normalisation eliminates false positives from legitimate browsing.

### Type C — Refund Fraud (Audit Decision Tree)

Conservative rule chain (approves when in doubt):
1. Scan missing from log → **APPROVE** (probable pick miss).
2. Scan exists, packer has Type-A flag → **APPROVE** (integrity uncertain).
3. Scan exists, packer has Type-B flag → **APPROVE** (possible interference).
4. Scan exists, packer is HIGH/CRITICAL risk → **APPROVE pending investigation**.
5. Scan exists, packer is clean → **REJECT** (high-confidence customer fraud).

---

## Customer Risk Engine

**Scoring formula (weighted sum of 4 normalised components):**

```
score = (refund_frequency × 0.30) + (refund_rate × 0.25)
      + (high_value_refunds × 0.25) + (cumulative_value × 0.20)
```

Each component is normalised to [0, 100] with realistic caps (e.g. 5 refunds = max frequency score). Final thresholds: CRITICAL ≥ 75, HIGH ≥ 50, MEDIUM ≥ 25.

---

## Store Risk Engine

**Per-store scoring formula:**

```
score = (refund_rate × 0.30) + (type_a_rate × 0.30)
      + (type_b_rate × 0.20) + (revenue_at_risk_rate × 0.20)
```

All components normalised against realistic operational caps. Produces ranked leaderboard of safest → highest-risk stores.

---

## Operational Analytics

| Metric | Description |
|--------|-------------|
| `anomaly_rate_overall` | (Type-A + Type-B events) / total scans |
| `refund_abuse_rate` | Blocked refunds / total refund claims |
| `high_value_anomaly_rate` | Hesitation events on HV items / total HV scans |
| `revenue_leakage_estimate` | Value of approved fraud claims (simulation ground truth) |
| `average_pack_time_s` | Mean seconds from first to last scan per order |
| `top_risky_skus` | SKUs most frequently appearing in violations |
| `revenue_by_category` | Total INR processed per product category |

---

## Benchmark Results

*(Run `python benchmark.py` to reproduce)*

| Orders | Scans | Time (s) | Memory (MB) | Orders/s | Scans/s |
|--------|-------|----------|-------------|----------|---------|
| 100 | ~510 | ~0.13 | ~35 | ~770 | ~3,900 |
| 1,000 | ~5,100 | ~0.45 | ~38 | ~2,200 | ~11,300 |
| 5,000 | ~25,500 | ~1.8 | ~55 | ~2,800 | ~14,200 |
| 10,000 | ~51,000 | ~3.6 | ~80 | ~2,800 | ~14,200 |
| 50,000 | ~255,000 | ~18 | ~280 | ~2,800 | ~14,200 |

*Pipeline is I/O-bound after 1,000 orders; detection is fully vectorised with pandas.*

---

## Limitations

- **Simulated data only.** This project uses synthetic order generation; it does not connect to any production systems.
- **No ML.** All detection uses rule-based and statistical methods — intentionally, for interpretability and auditability.
- **Single shift simulation.** The simulator generates one 8-hour shift per run; temporal trend analysis requires multi-day simulation.
- **Refund rate inference.** Customer `total_orders` is inferred from refund claim data, not from a real orders table.
- **Static product catalogue.** 25 SKUs cover major categories; a production deployment would ingest live catalogue data.

---

## Future Roadmap

- [ ] **Graph anomaly detection** — model packer-to-customer networks to detect coordinated fraud rings.
- [ ] **Temporal trend analysis** — multi-shift simulation with drift detection on packer behaviour.
- [ ] **SKU substitution detection** — flag barcode swaps between similar items.
- [ ] **Run tests**
python test_ivc.py
python test_historical.py

---

## Directory Structure

```
ivc/
├── main.py                   # CLI entry point
├── orchestrator.py           # 12-step pipeline wiring
├── simulator.py              # Dark store data generator (10 stores)
├── detectors.py              # Speed + hesitation detection
├── auditors.py               # Refund audit + packer risk scorer
├── customer_risk_engine.py   # Phase 1 — Customer Risk Engine
├── store_risk_engine.py      # Phase 2 — Dark Store Risk Engine
├── analytics_engine.py       # Phase 3 — Operational Analytics
├── streamlit_dashboard.py    # Phase 4/Stage 2 — 13-page Streamlit dashboard
├── benchmark.py              # Phase 5 — Performance benchmarks
├── report_generator.py       # Phase 6 — CSV/JSON export
├── models.py                 # All typed domain models
├── config.py                 # Centralised environment-driven config
├── exceptions.py             # Domain exception hierarchy
├── logging_config.py         # Structured JSON/text logging
├── dashboard.py              # Console dashboard (preserved)
├── test_ivc.py               # 19-test suite (all passing)
├── test_historical.py        # 10-test historical intelligence suite (all passing)
├── requirements.txt
├── setup.py
├── explainability/           # Stage 2 Explainability upgrades
│   ├── __init__.py
│   ├── explanation_models.py # Comparative, driver, and chain dataclasses
│   ├── explanation_engine.py # Packer, customer, store, & decision explainers
│   └── explainability_dashboard.py # Explainability tab layout renderings
└── historical_intelligence/  # Stage 2 Historical Subsystem
    ├── __init__.py
    ├── historical_models.py  # Snapshots, trend profiles, warnings, and reports
    ├── historical_simulator.py # 90-day simulator with Store 03 / PKR006 / Electronics drifts
    ├── trend_engine.py       # Least-squares slope calculation & narrative generation
    ├── early_warning_engine.py # Watchlist/Critical warning actions
    ├── forecasting_engine.py # LTP, Exponential Smoothing, & Moving Average (0-100 clip)
    └── network_health_engine.py # 0-100 health metrics calculation
```

---

## Installation

```bash
# Clone
git clone https://github.com/yourname/ivc-platform.git
cd ivc-platform

# Install
pip install -r requirements.txt

# Run CLI pipeline
python main.py --orders 500

# Run Streamlit dashboard
streamlit run streamlit_dashboard.py

# Run benchmarks
python benchmark.py

# Export reports
python -c "
from orchestrator import IVCOrchestrator
from report_generator import ReportGenerator
result = IVCOrchestrator(num_orders=500).run(render_dashboard=False)
gen = ReportGenerator(result, output_dir='reports')
paths = gen.export_all()
print(paths)
"

# Run tests
python test_ivc.py
python test_historical.py
```

---

## Usage

```bash
# CLI options
python main.py --orders 1000 --seed 99 --log-format json

# Environment overrides
IVC_MAX_HUMAN_SPEED_MS=5.0 IVC_HIGH_VALUE_INR=500 python main.py
```

*IVC Stage 2 — Operational Risk & Historical Intelligence Platform for Quick Commerce*