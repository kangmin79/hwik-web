"""전역 토큰 버킷 + 회로 차단기.

쓰임:
  - 28 worker × 호출 → 전역 QPS 상한 보장
  - 연속 실패 N회 → 회로 차단 → cool 기간 대기
"""
from __future__ import annotations

import threading
import time


class TokenBucket:
    """간단 토큰 버킷.

    rate: 초당 토큰 생성 수 (= 평균 QPS)
    capacity: 버킷 상한 (버스트 허용량)
    """

    def __init__(self, rate: float, capacity: float | None = None):
        self.rate = float(rate)
        self.capacity = float(capacity if capacity is not None else rate)
        self._tokens = self.capacity
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> None:
        """토큰 1개 확보될 때까지 sleep (블로킹)."""
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                self._last_refill = now
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                wait = (tokens - self._tokens) / self.rate
            time.sleep(max(wait, 0.001))


class CircuitBreaker:
    """연속 실패 N회 → 회로 OPEN → cool 기간 후 HALF_OPEN.

    HALF_OPEN 상태에서 다음 호출 성공 시 CLOSED, 실패 시 다시 OPEN.
    """

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(self, name: str, fail_threshold: int, cool_sec: int):
        self.name = name
        self.fail_threshold = fail_threshold
        self.cool_sec = cool_sec
        self._consec_fail = 0
        self._state = self.STATE_CLOSED
        self._opened_at = 0.0
        self._lock = threading.Lock()

    def before_call(self) -> None:
        """호출 직전. OPEN 상태면 cool 기간 대기 + HALF_OPEN 전환."""
        with self._lock:
            if self._state == self.STATE_OPEN:
                elapsed = time.monotonic() - self._opened_at
                wait = self.cool_sec - elapsed
                if wait > 0:
                    print(f"[circuit:{self.name}] OPEN — {wait:.0f}s 대기 후 재개", flush=True)
                    time.sleep(wait)
                self._state = self.STATE_HALF_OPEN
                print(f"[circuit:{self.name}] HALF_OPEN — 1회 시도", flush=True)

    def on_success(self) -> None:
        with self._lock:
            self._consec_fail = 0
            if self._state in (self.STATE_HALF_OPEN, self.STATE_OPEN):
                print(f"[circuit:{self.name}] CLOSED 복구", flush=True)
            self._state = self.STATE_CLOSED

    def on_failure(self) -> None:
        with self._lock:
            self._consec_fail += 1
            if self._state == self.STATE_HALF_OPEN:
                self._state = self.STATE_OPEN
                self._opened_at = time.monotonic()
                print(f"[circuit:{self.name}] HALF_OPEN 시도 실패 → OPEN 재진입", flush=True)
                return
            if self._consec_fail >= self.fail_threshold and self._state == self.STATE_CLOSED:
                self._state = self.STATE_OPEN
                self._opened_at = time.monotonic()
                print(f"[circuit:{self.name}] 연속 실패 {self._consec_fail}회 → OPEN", flush=True)
