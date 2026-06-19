"""
main.py
=======
IVC Fraud Detection System — CLI entry point.

Usage:
    python main.py                         # run with defaults (200 orders)
    python main.py --orders 500            # larger simulation
    python main.py --orders 1000 --log-format json   # JSON logging (for prod)
    python main.py --no-dashboard          # suppress visual output
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# Ensure the package is importable when run directly
sys.path.insert(0, os.path.dirname(__file__))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="IVC — Inventory Velocity Collision Fraud Detection System v2.0.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--orders", type=int, default=200,
        help="Number of simulated orders to generate (default: 200)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducible simulations (default: 42)",
    )
    parser.add_argument(
        "--log-format", choices=["text", "json"], default="text",
        help="Log output format: 'text' (human) or 'json' (machine, default: text)",
    )
    parser.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO",
        help="Logging verbosity (default: INFO)",
    )
    parser.add_argument(
        "--no-dashboard", action="store_true",
        help="Suppress console dashboard (useful for piping JSON output)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    # Inject config via environment before importing (config reads env at import)
    os.environ["IVC_LOG_FORMAT"] = args.log_format
    os.environ["IVC_LOG_LEVEL"]  = args.log_level

    from exceptions import IVCError
    from logging_config import get_logger
    from orchestrator import IVCOrchestrator

    log = get_logger("ivc.main")

    log.info(
        "IVC starting",
        version="2.0.0",
        num_orders=args.orders,
        seed=args.seed,
        log_format=args.log_format,
    )

    start = time.perf_counter()

    try:
        orchestrator = IVCOrchestrator(num_orders=args.orders)
        result = orchestrator.run(render_dashboard=not args.no_dashboard)
    except IVCError as exc:
        log.error("Pipeline failed", error=str(exc))
        return 1
    except KeyboardInterrupt:
        log.warning("Interrupted by user")
        return 130

    elapsed = round((time.perf_counter() - start) * 1000)
    log.info(
        "IVC finished",
        elapsed_ms=elapsed,
        type_a_violations=len(result.speed_violations),
        type_b_violations=len(result.hesitation_violations),
        refunds_blocked=sum(
            1 for r in result.audit_results if str(r.verdict) == "REJECT_REFUND"
        ),
        type_a_precision=round(result.precision_type_a, 3),
        type_a_recall=round(result.recall_type_a, 3),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
