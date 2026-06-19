"""
ivc/detectors.py
================
Fraud detection modules.

All detection is fully vectorised using pandas — no iterrows() loops.
Each detector is stateless: construct → call detect() → collect results.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

from config import DETECTION_CONFIG
from exceptions import InsufficientDataError, ValidationError
from logging_config import get_logger
from models import (
    AnomalyType,
    HesitationViolation,
    Product,
    ScanEvent,
    SpeedViolation,
)

log = get_logger(__name__)

_MIN_CATEGORY_SAMPLES = 5   # minimum records to compute a reliable baseline


# ── Utility ───────────────────────────────────────────────────────────────────

def scan_events_to_dataframe(events: list[ScanEvent]) -> pd.DataFrame:
    """
    Converts a list of ScanEvent objects into a typed DataFrame.
    Called once at pipeline start; subsequent modules operate on the frame.
    """
    if not events:
        raise ValidationError("Cannot create DataFrame from empty scan events list.")

    rows = [
        {
            "log_id":       e.log_id,
            "order_id":     e.order_id,
            "packer_id":    e.packer_id,
            "item_id":      e.item_id,
            "shelf_aisle":  e.shelf_aisle,
            "shelf_num":    e.shelf_num,
            "timestamp":    pd.Timestamp(e.timestamp),
            "speed_flag":          False,
            "hesitation_flag":     False,
            "computed_velocity_ms":  np.nan,
            "distance_from_prev_m":  np.nan,
            "gap_seconds":           np.nan,
        }
        for e in events
    ]
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


# ── Module 1: Walking Speed Validator ─────────────────────────────────────────

class WalkingSpeedValidator:
    """
    Detects physically-impossible scan velocities (Type A fraud).

    Algorithm (fully vectorised):
      1. Sort by (packer_id, order_id, timestamp).
      2. Within each (packer, order) group compute the previous-row shelf
         coordinates using groupby + shift — no iterrows.
      3. Compute Euclidean distance and time delta.
      4. Flag rows where velocity > MAX_HUMAN_SPEED_MS.

    Handles edge cases:
      - Zero / negative time delta → velocity = inf → always flagged.
      - Cross-order / cross-packer boundaries → distance = 0.
      - Missing shelf coordinates → distance = 0 (safe no-flag default).
    """

    def __init__(
        self,
        df: pd.DataFrame,
        shelf_coords: dict[tuple[str, int], tuple[float, float]],
    ) -> None:
        self._df           = df.copy()
        self._shelf_coords = shelf_coords
        self._violations:  list[SpeedViolation] = []

    def detect(self) -> pd.DataFrame:
        """
        Annotates the DataFrame with speed-related columns and returns it.
        Side effect: populates self._violations.
        """
        df = self._df
        cfg = DETECTION_CONFIG

        df = df.sort_values(["packer_id", "order_id", "timestamp"]).reset_index(drop=True)

        # Vectorised shelf coordinate lookup ──────────────────────────────────
        def _coord_x(aisle: str, shelf: int) -> float:
            return self._shelf_coords.get((aisle, shelf), (0.0, 0.0))[0]

        def _coord_y(aisle: str, shelf: int) -> float:
            return self._shelf_coords.get((aisle, shelf), (0.0, 0.0))[1]

        df["_cx"] = [_coord_x(a, s) for a, s in zip(df["shelf_aisle"], df["shelf_num"])]
        df["_cy"] = [_coord_y(a, s) for a, s in zip(df["shelf_aisle"], df["shelf_num"])]

        # Shift within (packer, order) groups ─────────────────────────────────
        grp = df.groupby(["packer_id", "order_id"], sort=False)

        df["_prev_cx"]   = grp["_cx"].shift(1)
        df["_prev_cy"]   = grp["_cy"].shift(1)
        df["_prev_ts"]   = grp["timestamp"].shift(1)
        df["_same_group"] = True   # all rows after shift are in-group by construction

        # Nulls at group boundaries — fill so arithmetic doesn't propagate NaN
        df["_prev_cx"]  = df["_prev_cx"].fillna(df["_cx"])
        df["_prev_cy"]  = df["_prev_cy"].fillna(df["_cy"])
        df["_prev_ts"]  = df["_prev_ts"].fillna(df["timestamp"])

        # Distance and velocity ───────────────────────────────────────────────
        dx = df["_cx"] - df["_prev_cx"]
        dy = df["_cy"] - df["_prev_cy"]
        df["distance_from_prev_m"] = np.sqrt(dx**2 + dy**2).round(4)

        delta_s = (df["timestamp"] - df["_prev_ts"]).dt.total_seconds()
        # Zero or negative delta → treat as inf velocity
        df["_delta_s"] = delta_s.where(delta_s > 0, other=np.nan)

        df["computed_velocity_ms"] = (
            df["distance_from_prev_m"] / df["_delta_s"]
        ).replace([np.inf, -np.inf], np.inf).round(4)

        # Flag impossibly fast scans ──────────────────────────────────────────
        # Exclude first row of each group (distance=0, delta=0) by checking distance > 0
        is_first_in_group = grp["timestamp"].transform("first") == df["timestamp"]
        df["speed_flag"] = (
            (df["computed_velocity_ms"] > cfg.max_human_speed_ms) &
            (df["distance_from_prev_m"] > 0) &
            (~is_first_in_group)
        )

        # Collect violation records ───────────────────────────────────────────
        flagged = df[df["speed_flag"]]
        for _, row in flagged.iterrows():
            vel = row["computed_velocity_ms"]
            dt  = delta_s.loc[row.name] if row.name in delta_s.index else 0.0
            self._violations.append(SpeedViolation(
                log_id      = row["log_id"],
                order_id    = row["order_id"],
                packer_id   = row["packer_id"],
                item_id     = row["item_id"],
                distance_m  = round(float(row["distance_from_prev_m"]), 2),
                delta_s     = round(float(dt), 4),
                velocity_ms = float(vel),
            ))

        # Cleanup temp columns ────────────────────────────────────────────────
        df.drop(columns=["_cx", "_cy", "_prev_cx", "_prev_cy", "_prev_ts",
                         "_same_group", "_delta_s"], inplace=True)

        log.info("Speed validation complete", flagged=len(self._violations))
        self._df = df
        return df

    @property
    def violations(self) -> list[SpeedViolation]:
        return self._violations


# ── Module 2: Time Hesitation Detector ────────────────────────────────────────

class TimeHesitationDetector:
    """
    Detects abnormal dwell times on high-value items (Type B fraud).

    Algorithm (fully vectorised):
      1. Compute per-(packer, order) inter-scan gaps using groupby + diff.
      2. Build a per-category baseline (mean, std) from CLEAN records
         (speed_flag=False) with a minimum sample guard.
      3. Categories with < _MIN_CATEGORY_SAMPLES fall back to the global
         store-wide baseline, with a warning logged.
      4. Flag high-value rows where gap > μ + σ_threshold × σ.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        product_catalogue: dict[str, Product],
    ) -> None:
        self._df       = df.copy()
        self._products = product_catalogue
        self._violations: list[HesitationViolation] = []

    def detect(self) -> pd.DataFrame:
        """
        Annotates the DataFrame with hesitation-related columns.
        Side effect: populates self._violations.
        """
        df  = self._df
        cfg = DETECTION_CONFIG

        # Attach product metadata ─────────────────────────────────────────────
        df["category"]     = df["item_id"].map(lambda i: self._products[i].category if i in self._products else "UNKNOWN")
        df["is_high_value"] = df["item_id"].map(lambda i: self._products[i].is_high_value if i in self._products else False)
        df["value_inr"]    = df["item_id"].map(lambda i: self._products[i].value_inr if i in self._products else 0.0)

        # Vectorised gap computation ──────────────────────────────────────────
        df = df.sort_values(["packer_id", "order_id", "timestamp"])
        df["gap_seconds"] = (
            df.groupby(["packer_id", "order_id"])["timestamp"]
            .diff()
            .dt.total_seconds()
            .fillna(0.0)
        )

        # Build per-category baseline from speed-clean records ────────────────
        clean = df[~df["speed_flag"]]
        global_mean = clean["gap_seconds"].mean()
        global_std  = max(clean["gap_seconds"].std(), 1.0)   # guard div-by-zero

        cat_stats: dict[str, tuple[float, float]] = {}
        for cat, grp in clean.groupby("category"):
            if len(grp) < _MIN_CATEGORY_SAMPLES:
                try:
                    raise InsufficientDataError(cat, len(grp), _MIN_CATEGORY_SAMPLES)
                except InsufficientDataError as exc:
                    log.warning(str(exc), category=cat)
                    cat_stats[cat] = (global_mean, global_std)
            else:
                cat_stats[cat] = (grp["gap_seconds"].mean(), max(grp["gap_seconds"].std(), 1.0))

        # Vectorised threshold computation ────────────────────────────────────
        df["_cat_mean"] = df["category"].map(lambda c: cat_stats.get(c, (global_mean, global_std))[0])
        df["_cat_std"]  = df["category"].map(lambda c: cat_stats.get(c, (global_mean, global_std))[1])
        df["_threshold"] = df["_cat_mean"] + cfg.hesitation_sigma_threshold * df["_cat_std"]

        df["hesitation_flag"] = (
            df["is_high_value"] &
            (df["gap_seconds"] > df["_threshold"])
        )

        # Collect violation records ───────────────────────────────────────────
        flagged = df[df["hesitation_flag"]]
        for _, row in flagged.iterrows():
            std   = row["_cat_std"]
            sigma = (row["gap_seconds"] - row["_cat_mean"]) / max(std, 1e-9)
            self._violations.append(HesitationViolation(
                log_id         = row["log_id"],
                order_id       = row["order_id"],
                packer_id      = row["packer_id"],
                item_id        = row["item_id"],
                category       = row["category"],
                gap_seconds    = round(float(row["gap_seconds"]), 2),
                cat_mean_gap   = round(float(row["_cat_mean"]), 2),
                sigma_distance = round(float(sigma), 2),
                value_inr      = float(row["value_inr"]),
            ))

        # Cleanup temp columns
        df.drop(columns=["_cat_mean", "_cat_std", "_threshold"], inplace=True)

        log.info("Hesitation detection complete", flagged=len(self._violations))
        self._df = df
        return df

    @property
    def violations(self) -> list[HesitationViolation]:
        return self._violations
