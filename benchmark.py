"""
ivc/benchmark.py
================
Phase 5 — Performance Benchmarking.

Benchmarks the IVC pipeline at 100 / 1000 / 5000 / 10000 / 50000 orders.
Measures execution time, memory usage, and throughput.

Run:
    python benchmark.py
"""

from __future__ import annotations

import gc
import sys
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path

# Ensure package is importable when run directly
sys.path.insert(0, str(Path(__file__).parent))


@dataclass
class BenchmarkRun:
    num_orders:        int
    elapsed_s:         float
    peak_memory_mb:    float
    orders_per_second: float
    scans_per_second:  float
    total_scans:       int


def _run_once(num_orders: int) -> BenchmarkRun:
    gc.collect()
    tracemalloc.start()

    t_start = time.perf_counter()

    from orchestrator import IVCOrchestrator
    orch   = IVCOrchestrator(num_orders=num_orders)
    result = orch.run(render_dashboard=False)

    elapsed = time.perf_counter() - t_start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    total_scans = len(result.validated_logs)

    return BenchmarkRun(
        num_orders        = num_orders,
        elapsed_s         = round(elapsed, 3),
        peak_memory_mb    = round(peak / 1024 / 1024, 2),
        orders_per_second = round(num_orders / elapsed, 1),
        scans_per_second  = round(total_scans / elapsed, 1),
        total_scans       = total_scans,
    )


def run_benchmark(
    sizes: list[int] | None = None,
    output_path: str | None = None,
) -> list[BenchmarkRun]:
    """
    Run benchmarks for the given order sizes.

    Args:
        sizes:       List of order counts to benchmark.  Defaults to standard suite.
        output_path: Optional path to write the text report.

    Returns:
        List of BenchmarkRun results.
    """
    if sizes is None:
        sizes = [100, 1000, 5000, 10_000, 50_000]

    results: list[BenchmarkRun] = []

    sep = "═" * 72
    print(f"\n{sep}")
    print("  IVC PERFORMANCE BENCHMARK SUITE".center(72))
    print(sep)
    print(f"  {'Orders':>8}  {'Scans':>8}  {'Time (s)':>10}  {'Memory (MB)':>12}  {'Orders/s':>10}  {'Scans/s':>10}")
    print("  " + "─" * 68)

    for n in sizes:
        print(f"  Running {n:,} orders...", end="\r", flush=True)
        run = _run_once(n)
        results.append(run)
        print(
            f"  {run.num_orders:>8,}  {run.total_scans:>8,}  "
            f"{run.elapsed_s:>10.3f}  {run.peak_memory_mb:>12.1f}  "
            f"{run.orders_per_second:>10,.0f}  {run.scans_per_second:>10,.0f}"
        )

    print("  " + "─" * 68)
    print(f"\n  Fastest throughput: {max(r.orders_per_second for r in results):,.0f} orders/s")
    print(f"  Peak memory (largest run): {results[-1].peak_memory_mb:.1f} MB")
    print(f"{sep}\n")

    if output_path:
        _write_report(results, output_path)

    return results


def _write_report(results: list[BenchmarkRun], path: str) -> None:
    lines = [
        "IVC Benchmark Report",
        "=" * 72,
        f"{'Orders':>8}  {'Scans':>8}  {'Time (s)':>10}  {'Memory (MB)':>12}  {'Orders/s':>10}",
        "-" * 72,
    ]
    for r in results:
        lines.append(
            f"{r.num_orders:>8,}  {r.total_scans:>8,}  {r.elapsed_s:>10.3f}  "
            f"{r.peak_memory_mb:>12.1f}  {r.orders_per_second:>10,.0f}"
        )
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Report written to: {path}")


if __name__ == "__main__":
    run_benchmark()