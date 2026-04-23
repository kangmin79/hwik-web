"""카카오 주소 검색 클라이언트 (b_code/좌표).

Stage 2 에서 bjdongCd 보강용, Stage 3 에서 단지 좌표용 공용.
"""
from __future__ import annotations

import json

from ..config import KAKAO_ADDRESS_URL, KAKAO_API_KEY, KAKAO_GLOBAL_QPS
from ..http_session import get_pool
from ..rate_limiter import TokenBucket

_BUCKET = TokenBucket(rate=KAKAO_GLOBAL_QPS, capacity=KAKAO_GLOBAL_QPS * 2)


class KakaoError(RuntimeError):
    pass


def address_search(query: str) -> dict | None:
    """카카오 주소 검색. 첫 결과 dict 반환 (없으면 None)."""
    if not query or not query.strip():
        return None
    if not KAKAO_API_KEY:
        raise KakaoError("KAKAO_REST_API_KEY 환경변수 없음")

    _BUCKET.acquire()
    pool = get_pool()
    resp = pool.request(
        "GET",
        f"{KAKAO_ADDRESS_URL}?query={query}",
        headers={"Authorization": f"KakaoAK {KAKAO_API_KEY}"},
    )
    if resp.status != 200:
        raise KakaoError(f"카카오 HTTP {resp.status}: {resp.data[:200]!r}")
    data = json.loads(resp.data)
    docs = data.get("documents", [])
    return docs[0] if docs else None


def parse_address_doc(doc: dict) -> dict:
    """카카오 응답 → 표준화 필드.

    address.b_code: 10자리 법정동 코드 (앞 5자리 = sigungu, 뒤 5자리 = bjdong)
    """
    addr = doc.get("address") or {}
    road = doc.get("road_address") or {}
    b_code = addr.get("b_code", "")
    return {
        "jibun_addr": addr.get("address_name", ""),
        "road_addr": road.get("address_name", ""),
        "sigungu_cd": b_code[:5] if b_code else "",
        "bjdong_cd": b_code[5:] if b_code else "",
        "main_no": addr.get("main_address_no", ""),
        "sub_no": addr.get("sub_address_no", "") or "0",
        "lat": float(addr.get("y") or 0) or None,
        "lng": float(addr.get("x") or 0) or None,
        "road_lat": float(road.get("y") or 0) or None if road else None,
        "road_lng": float(road.get("x") or 0) or None if road else None,
    }
