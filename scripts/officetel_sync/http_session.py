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
                    timeout=urllib3.Timeout(connect=5, read=20),
                    headers={
                        "User-Agent": "curl/8.0.1",
                        "Accept": "*/*",         # 국토부 BldRgstHubService 가 없으면 빈 응답
                    },
                )
    return _POOL


def get(url: str, params: dict | None = None) -> bytes:
    """단일 GET. 타임아웃·재시도는 호출자 책임."""
    if params:
        query = urllib.parse.urlencode(params, safe="+/=")
        url = f"{url}?{query}"
    pool = get_pool()
    resp = pool.request("GET", url)
    if resp.status != 200:
        raise RuntimeError(f"HTTP {resp.status}: {resp.data[:300]!r}")
    return resp.data
