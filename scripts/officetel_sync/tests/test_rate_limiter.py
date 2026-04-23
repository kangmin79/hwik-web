"""TokenBucket 단위 테스트."""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.officetel_sync.rate_limiter import CircuitBreaker, TokenBucket


class TestTokenBucket(unittest.TestCase):
    def test_burst_then_rate_limit(self):
        # 10 QPS, capacity 10 → 첫 10건 즉시, 11번째부터 대기
        bucket = TokenBucket(rate=10, capacity=10)
        start = time.monotonic()
        for _ in range(10):
            bucket.acquire()
        burst = time.monotonic() - start
        self.assertLess(burst, 0.05)  # 거의 즉시

        # 11번째: 약 100ms 대기
        start = time.monotonic()
        bucket.acquire()
        wait = time.monotonic() - start
        self.assertGreater(wait, 0.05)


class TestCircuitBreaker(unittest.TestCase):
    def test_opens_after_n_failures(self):
        cb = CircuitBreaker("test", fail_threshold=3, cool_sec=0)
        for _ in range(3):
            cb.before_call()
            cb.on_failure()
        self.assertEqual(cb._state, CircuitBreaker.STATE_OPEN)

    def test_recovers_on_success(self):
        cb = CircuitBreaker("test", fail_threshold=3, cool_sec=0)
        cb.before_call(); cb.on_failure()
        cb.before_call(); cb.on_success()
        self.assertEqual(cb._state, CircuitBreaker.STATE_CLOSED)
        self.assertEqual(cb._consec_fail, 0)


if __name__ == "__main__":
    unittest.main()
