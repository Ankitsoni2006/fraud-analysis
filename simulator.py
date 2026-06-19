"""
ivc/simulator.py
================
Synthetic dark-store data generator.
Extended to support 10 dark stores (Phase 2) and customer IDs on refund claims.
"""

from __future__ import annotations

import math
import random
import uuid
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from config import (
    AISLES, SHELVES, PRODUCTS, PACKER_IDS,
    SHELF_SPACING_METERS, AISLE_SPACING_METERS,
    DETECTION_CONFIG,
)
from exceptions import SimulationError
from logging_config import get_logger
from models import Product, RefundClaim, ScanEvent, ShelfLocation

log = get_logger(__name__)

# 10 dark stores across NCR
STORE_IDS = [f"STORE_{str(i).zfill(2)}" for i in range(1, 11)]

# Customer pool
CUSTOMER_IDS = [f"CUST{str(i).zfill(5)}" for i in range(1, 501)]


class DarkStoreSimulator:
    """
    Generates synthetic fulfilment scan events for a network of dark stores.

    Each order is assigned to one of 10 dark stores.
    Refund claims reference real customer IDs for cross-order analysis.
    """

    def __init__(self, num_orders: int = 200, seed: int = 42) -> None:
        if num_orders < 1:
            raise SimulationError(f"num_orders must be ≥ 1, got {num_orders}")
        self.num_orders = num_orders
        self._seed      = seed
        random.seed(seed)
        np.random.seed(seed)

        self._shelf_coords: dict[tuple[str, int], tuple[float, float]] = {}
        self._products:     dict[str, Product]                          = {}
        self._scan_events:  list[ScanEvent]                             = []
        self._refund_claims: list[RefundClaim]                          = []
        self._injected_log_ids: dict[str, list[str]]                    = {
            "A": [], "B": [], "C": []
        }
        # order_id → customer_id mapping for refund claim generation
        self._order_customers: dict[str, str] = {}
        # order_id → store_id mapping
        self._order_stores: dict[str, str] = {}

    def run(self) -> tuple[
        list[ScanEvent],
        list[RefundClaim],
        dict[str, Product],
        dict[tuple[str, int], tuple[float, float]],
        dict[str, list[str]],
    ]:
        log.info("Building shelf grid and product catalogue")
        self._build_shelf_grid()
        self._build_product_catalogue()

        log.info("Generating normal orders", num_orders=self.num_orders)
        self._generate_orders()

        log.info("Injecting Type-A anomalies (impossible speed)")
        self._inject_type_a(n=max(12, self.num_orders // 17))
        log.info("Injecting Type-B anomalies (hesitation)")
        self._inject_type_b(n=max(10, self.num_orders // 20))
        log.info("Injecting Type-C anomalies (refund fraud)")
        self._inject_type_c(n=max(15, self.num_orders // 14))

        log.info(
            "Simulation complete",
            scan_events=len(self._scan_events),
            type_a=len(self._injected_log_ids["A"]),
            type_b=len(self._injected_log_ids["B"]),
            type_c=len(self._refund_claims),
        )
        return (
            self._scan_events,
            self._refund_claims,
            self._products,
            self._shelf_coords,
            self._injected_log_ids,
        )

    def _build_shelf_grid(self) -> None:
        for a_idx, aisle in enumerate(AISLES):
            for shelf in SHELVES:
                self._shelf_coords[(aisle, shelf)] = (
                    a_idx * AISLE_SPACING_METERS,
                    shelf * SHELF_SPACING_METERS,
                )

    def _build_product_catalogue(self) -> None:
        for (item_id, name, category, value, aisle, shelf) in PRODUCTS:
            x, y = self._shelf_coords[(aisle, shelf)]
            location = ShelfLocation(
                aisle=aisle, shelf_num=shelf, coord_x=x, coord_y=y
            )
            self._products[item_id] = Product(
                item_id=item_id,
                item_name=name,
                category=category,
                value_inr=value,
                shelf=location,
            )

    @staticmethod
    def _walk_time_seconds(distance_m: float) -> float:
        walk_speed    = random.uniform(1.0, 1.8)
        scan_overhead = random.uniform(3.0, 8.0)
        return (distance_m / walk_speed) + scan_overhead

    def _generate_orders(self) -> None:
        shift_start = datetime(2024, 6, 15, 8, 0, 0)
        item_ids    = list(self._products.keys())

        for seq in range(self.num_orders):
            order_id    = f"ORD{str(seq + 1).zfill(5)}"
            packer_id   = random.choice(PACKER_IDS)
            store_id    = random.choice(STORE_IDS)
            customer_id = random.choice(CUSTOMER_IDS)
            num_items   = random.randint(3, 7)
            picked      = random.sample(item_ids, k=min(num_items, len(item_ids)))

            self._order_customers[order_id] = customer_id
            self._order_stores[order_id]    = store_id

            order_start = shift_start + timedelta(seconds=random.uniform(0, 28_800))
            current_ts  = order_start
            prev_coords: Optional[tuple[float, float]] = None

            for item_id in picked:
                product = self._products[item_id]
                cx = product.shelf.coord_x
                cy = product.shelf.coord_y

                if prev_coords is None:
                    gap = random.uniform(3.0, 8.0)
                else:
                    dist = math.sqrt(
                        (cx - prev_coords[0]) ** 2 + (cy - prev_coords[1]) ** 2
                    )
                    gap = self._walk_time_seconds(dist)

                current_ts += timedelta(seconds=gap)
                self._scan_events.append(ScanEvent(
                    log_id      = ScanEvent.new_id(),
                    order_id    = order_id,
                    packer_id   = packer_id,
                    item_id     = item_id,
                    shelf_aisle = product.shelf.aisle,
                    shelf_num   = product.shelf.shelf_num,
                    timestamp   = current_ts,
                    store_id    = store_id,
                ))
                prev_coords = (cx, cy)

    def _inject_type_a(self, n: int) -> None:
        remote_shelves = [
            s for s in self._shelf_coords if s[0] in ("C", "D", "E")
        ]
        injected = 0
        attempts = 0
        max_attempts = n * 10

        while injected < n and attempts < max_attempts:
            attempts += 1
            base = random.choice(self._scan_events)
            far  = random.choice(remote_shelves)

            x1, y1 = self._shelf_coords[(base.shelf_aisle, base.shelf_num)]
            x2, y2 = self._shelf_coords[far]
            distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

            if distance < 5.0:
                continue

            delta_ms = random.randint(100, 500)
            fake_ts  = base.timestamp + timedelta(milliseconds=delta_ms)

            candidates = [
                p for p in self._products.values()
                if p.shelf.aisle == far[0] and p.shelf.shelf_num == far[1]
            ]
            if not candidates:
                continue

            item   = candidates[0]
            log_id = ScanEvent.new_id()
            self._scan_events.append(ScanEvent(
                log_id      = log_id,
                order_id    = base.order_id,
                packer_id   = base.packer_id,
                item_id     = item.item_id,
                shelf_aisle = item.shelf.aisle,
                shelf_num   = item.shelf.shelf_num,
                timestamp   = fake_ts,
                store_id    = base.store_id,
                anomaly_detail = f"Injected TypeA: {distance:.1f}m in {delta_ms}ms",
            ))
            self._injected_log_ids["A"].append(log_id)
            injected += 1

        log.debug("Type-A injection complete", injected=injected, attempts=attempts)

    def _inject_type_b(self, n: int) -> None:
        hv_events = [
            e for e in self._scan_events
            if self._products[e.item_id].is_high_value
            and e.anomaly_detail is None
        ]
        sample = random.sample(hv_events, k=min(n, len(hv_events)))

        for event in sample:
            hesitation_s       = random.randint(120, 300)
            event.timestamp    += timedelta(seconds=hesitation_s)
            event.anomaly_detail = f"Injected TypeB: hesitation {hesitation_s}s"
            self._injected_log_ids["B"].append(event.log_id)

        log.debug("Type-B injection complete", injected=len(sample))

    def _inject_type_c(self, n: int) -> None:
        anomalous_orders = {
            e.order_id for e in self._scan_events if e.anomaly_detail
        }
        hv_clean = [
            e for e in self._scan_events
            if self._products[e.item_id].is_high_value
            and e.order_id not in anomalous_orders
        ]
        sample = random.sample(hv_clean, k=min(n, len(hv_clean)))

        for event in sample:
            product     = self._products[event.item_id]
            customer_id = self._order_customers.get(event.order_id, f"CUST{random.randint(1000, 9999)}")
            self._refund_claims.append(RefundClaim(
                refund_id         = str(uuid.uuid4()),
                order_id          = event.order_id,
                customer_id       = customer_id,
                item_id           = event.item_id,
                claimed_value_inr = product.value_inr,
                claim_reason      = "Item missing from bag",
                request_ts        = event.timestamp + timedelta(minutes=random.randint(30, 180)),
                injected_fraud    = True,
            ))
            self._injected_log_ids["C"].append(event.log_id)

        log.debug("Type-C injection complete", injected=len(sample))