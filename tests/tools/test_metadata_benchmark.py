"""Benchmark for optimized single-query metadata retrieval."""

import os
import time

import pytest


@pytest.mark.asyncio
async def test_benchmark_metadata_retrieval():
    """Benchmark the optimized get_metadata function with single query."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")

    from hipeac_mcp.tools.metadata import get_metadata

    # Warm up
    await get_metadata()

    # Benchmark metadata retrieval
    times = []
    for _ in range(10):
        start = time.perf_counter()
        result = await get_metadata()
        times.append(time.perf_counter() - start)

        # Verify we got all data
        assert result.topics is not None and len(result.topics) > 0
        assert result.application_areas is not None and len(result.application_areas) > 0
        assert result.institution_types is not None and len(result.institution_types) > 0
        assert result.membership_types is not None and len(result.membership_types) == 4

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    print("\n\nBenchmark Results (10 runs):")
    print(f"Average: {avg_time * 1000:.2f}ms")
    print(f"Min:     {min_time * 1000:.2f}ms")
    print(f"Max:     {max_time * 1000:.2f}ms")
    print("\nOptimization: Single query with type__in filter + async for iteration")

    # This is informational, not a hard assertion
    assert avg_time > 0
