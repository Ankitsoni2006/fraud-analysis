"""
ivc/config.py
=============
Centralised, environment-driven configuration.
All tunable parameters live here; no magic numbers anywhere else.

Environment variables override defaults at import time so the same
codebase runs in dev, staging, and production without code changes:

    IVC_MAX_HUMAN_SPEED_MS=5.5 python -m ivc.main
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Final

# ── Physical / spatial constants ─────────────────────────────────────────────

SHELF_SPACING_METERS: Final[float]  = 2.5   # metres between bins on same aisle
AISLE_SPACING_METERS: Final[float]  = 4.0   # metres between parallel aisles

AISLES: Final[list[str]]            = list("ABCDE")
SHELVES: Final[list[int]]           = list(range(1, 11))   # shelves 1–10


# ── Product catalogue ─────────────────────────────────────────────────────────

PRODUCTS: Final[list[tuple]] = [
    # (item_id, name, category, value_inr, shelf_aisle, shelf_num)
    ("SKU001", "Maggi Noodles 70g",       "FMCG_LOW",       15,   "A", 1),
    ("SKU002", "Lay's Classic Chips",     "FMCG_LOW",       20,   "A", 2),
    ("SKU003", "Parle-G Biscuits 200g",   "FMCG_LOW",       10,   "A", 3),
    ("SKU004", "Amul Butter 100g",        "DAIRY",          55,   "A", 4),
    ("SKU005", "Tata Salt 1kg",           "FMCG_LOW",       24,   "A", 5),
    ("SKU006", "Dove Shampoo 180ml",      "PERSONAL_CARE",  185,  "B", 1),
    ("SKU007", "Colgate Total 200g",      "PERSONAL_CARE",  120,  "B", 2),
    ("SKU008", "Nivea Face Wash",         "COSMETICS",      350,  "B", 3),
    ("SKU009", "Lakme Lipstick",          "COSMETICS",      499,  "B", 4),
    ("SKU010", "L'Oréal Serum 30ml",      "COSMETICS",      749,  "B", 5),
    ("SKU011", "Prestige Pressure Cooker","KITCHEN",        1799, "C", 1),
    ("SKU012", "Philips LED Bulb 9W",     "ELECTRONICS",    299,  "C", 2),
    ("SKU013", "boAt Earbuds",            "ELECTRONICS",   1299,  "C", 3),
    ("SKU014", "Mi Power Bank 10000mAh",  "ELECTRONICS",    999,  "C", 4),
    ("SKU015", "Zebronics USB Hub",       "ELECTRONICS",    449,  "C", 5),
    ("SKU016", "Tata Tea Gold 250g",      "BEVERAGES",       95,  "D", 1),
    ("SKU017", "Nescafé Classic 100g",    "BEVERAGES",      235,  "D", 2),
    ("SKU018", "Red Bull 250ml",          "BEVERAGES",      125,  "D", 3),
    ("SKU019", "Tropicana Orange 1L",     "BEVERAGES",       99,  "D", 4),
    ("SKU020", "Himalaya Neem Wash",      "PERSONAL_CARE",  180,  "D", 5),
    ("SKU021", "Dettol Handwash 200ml",   "PERSONAL_CARE",   90,  "E", 1),
    ("SKU022", "Whisper Ultra 15s",       "PERSONAL_CARE",  175,  "E", 2),
    ("SKU023", "Johnson Baby Powder",     "PERSONAL_CARE",  145,  "E", 3),
    ("SKU024", "Ferrero Rocher 16pc",     "CONFECTIONERY",  385,  "E", 4),
    ("SKU025", "Cadbury Celebrations",   "CONFECTIONERY",   299,  "E", 5),
]

PACKER_IDS: Final[list[str]] = [f"PKR{str(i).zfill(3)}" for i in range(1, 11)]


# ── Runtime-tunable detection parameters ────────────────────────────────────

@dataclass(frozen=True)
class DetectionConfig:
    """
    Immutable detection parameters.  Frozen dataclass enforces that no
    module accidentally mutates shared config at runtime.

    All float/int fields can be overridden via environment variables
    (uppercase field name prefixed with IVC_).
    """

    # Physical speed cap — anything above this is physically impossible for a human
    max_human_speed_ms: float = field(
        default_factory=lambda: float(os.getenv("IVC_MAX_HUMAN_SPEED_MS", "6.0"))
    )

    # σ multiplier for hesitation detection; 2.5 ≈ top 0.6% of normal distribution
    hesitation_sigma_threshold: float = field(
        default_factory=lambda: float(os.getenv("IVC_HESITATION_SIGMA", "2.5"))
    )

    # Items at or above this INR value are treated as high-value
    high_value_threshold_inr: float = field(
        default_factory=lambda: float(os.getenv("IVC_HIGH_VALUE_INR", "300"))
    )

    # Score weights for the packer risk leaderboard
    type_a_weight: int = field(
        default_factory=lambda: int(os.getenv("IVC_TYPE_A_WEIGHT", "3"))
    )
    type_b_weight: int = field(
        default_factory=lambda: int(os.getenv("IVC_TYPE_B_WEIGHT", "2"))
    )

    # Risk tier thresholds (score >= value → tier)
    risk_critical_threshold: int = field(
        default_factory=lambda: int(os.getenv("IVC_RISK_CRITICAL", "10"))
    )
    risk_high_threshold: int = field(
        default_factory=lambda: int(os.getenv("IVC_RISK_HIGH", "5"))
    )


# Singleton — import and use directly
DETECTION_CONFIG = DetectionConfig()


# ── Logging configuration ─────────────────────────────────────────────────────

LOG_LEVEL: Final[str]  = os.getenv("IVC_LOG_LEVEL", "INFO").upper()
LOG_FORMAT: Final[str] = os.getenv("IVC_LOG_FORMAT", "text")   # "text" | "json"
