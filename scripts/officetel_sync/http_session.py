"""커넥션 풀 공유 HTTP 세션.

urllib.request 매 호출마다 새 소켓 → Windows TCP 고갈 위험.
urllib3.PoolManager 로 28 worker 가 풀 공유.
"""
from __future__ import annotations

import threading
import urllib.parse

try:
    import urllib3
    from urllib3.util.retry import Retry
except ImportError as e:
    raise SystemExit(
        "urllib3 가 필요합니다. `pip install urllib3` 실행 후 다시 시도하세요."
    ) from e

_POOL: urllib3.PoolManager | None = None
_POOL_LOCK = threading.Lock()


def get_pool() -> urllib3.PoolManager:
    global _POOL
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                # 28 worker × 약간 여유
                retry = Retry(
                    total=0,                # 재시도는 상위 레이어에서
                    connect=1, read=1,
                    backoff_factor=0,
                    status_forcelist=(),
                )
                _POOL = urllib3.PoolManager(
                    num_pools=8,
                    maxsize=64,
                    retries=retry,
                    timeout=urllib3.Timeout(connect=10, read=60),  # 2026-04-27: 5/20→10/60 (아파트와 동일)
                    headers={
                        # 2026-04-26: 국토부 WAF 가 'curl/*' UA 차단 시작 → 400 Request Blocked
                        # 표준 브라우저 UA 로 회피. Accept: */* 는 BldRgstHubService 빈 응답 방지.
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                                      "Chrome/124.0.0.0 Safari/537.36",
                        "Accept": "*/*",
                    },
                )
    return _POOL


def get(url: str, params: dict | None = None) -> bytes:
    """단일 GET. 타임아웃·재시도는 호출자 책임.

    safe="" — 국토부 service key 의 '+', '/', '=' 도 모두 percent-encoding.
    (이전 safe="+/=" 가 키를 raw 로 전송 → '+' 가 space 로 해석돼 400 Request Blocked)
    """
    if params:
        query = urllib.parse.urlencode(params, safe="")
        url = f"{url}?{query}"
    pool = get_pool()
    resp = pool.request("GET", url)
    if resp.status != 200:
        raise RuntimeError(f"HTTP {resp.status}: {resp.data[:300]!r}")
    return resp.data
