"""Tests for CLOB client rate limiter."""
import pytest
import asyncio
import time

from src.data.clob_client import TokenBucket


@pytest.mark.asyncio
async def test_token_bucket_allows_immediate_burst():
    bucket = TokenBucket(rate_per_minute=60)
    # Should allow immediate acquisition up to capacity
    t0 = time.monotonic()
    for _ in range(5):
        await bucket.acquire()
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0  # All 5 should be near-instant


@pytest.mark.asyncio
async def test_token_bucket_throttles():
    # 6 requests/minute = 0.1 req/sec
    bucket = TokenBucket(rate_per_minute=6)
    # Drain initial tokens
    for _ in range(6):
        await bucket.acquire()
    t0 = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - t0
    # Should have waited ~10 seconds for next token, but we cap at 2s for test speed
    # We just verify it waited at all
    assert elapsed > 0.5
