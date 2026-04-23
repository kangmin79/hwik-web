"""행정안전부 주소기반산업지원서비스 — 좌표검색 OPEN API 클라이언트.

엔드포인트: addrCoordApi.do
입력: admCd, rnMgtSn, udrtYn, buldMnnm, buldSlno, confmKey, resultType=json
출력: results.juso[].entX / entY (EPSG:5179 UTMK)

카카오 address.json 일일 한도 초과 대비 2차 지오코딩 소스.

주의: 서버 측 rate limit(E0007) 발생 시 지수 백오프로 재시도.
"""
from __future__ import annotations

import json
import time
import urllib.parse

import pyproj

from ..config import JUSO_COORD_URL, JUSO_CONFIRM_KEY, JUSO_GLOBAL_QPS
from ..http_session import get_pool
from ..rate_limiter import TokenBucket

_BUCKET = TokenBucket(rate=JUSO_GLOBAL_QPS, capacity=JUSO_GLOBAL_QPS * 2)
_TRANSFORMER = pyproj.Transformer.from_crs("epsg:5179", "epsg:4326", always_xy=True)

_RATE_LIMIT_CODES = ("E0007",)  # 서버 측 rate limit


class JusoError(RuntimeError):
    pass


def utmk_to_wgs84(ent_x: float, ent_y: float) -> tuple[float, float]:
    """UTMK(EPSG:5179) → WGS84(EPSG:4326). 반환 (lat, lng)."""
    lng, lat = _TRANSFORMER.transform(ent_x, ent_y)
    return lat, lng


def _call_once(adm_cd, rn_mgt_sn, udrt_yn, buld_mnnm, buld_slno):
    _BUCKET.acquire()
    params = {
        "confmKey": JUSO_CONFIRM_KEY,
        "resultType": "json",
        "admCd": adm_cd,
        "rnMgtSn": rn_mgt_sn,
        "udrtYn": udrt_yn,
        "buldMnnm": str(int(buld_mnnm)) if buld_mnnm else "0",
        "buldSlno": str(int(buld_slno)) if buld_slno else "0",
    }
    url = f"{JUSO_COORD_URL}?{urllib.parse.urlencode(params)}"
    resp = get_pool().request("GET", url)
    if resp.status != 200:
        raise JusoError(f"HTTP {resp.status}: {resp.data[:200]!r}")
    data = json.loads(resp.data.decode("utf-8"))
    results = data.get("results") or {}
    common = results.get("common") or {}
    code = str(common.get("errorCode") or "")
    if code != "0":
        raise JusoError(f"err {code}: {common.get('errorMessage')}")
    return results.get("juso") or []


def coord_search(adm_cd: str, rn_mgt_sn: str, udrt_yn: str,
                 buld_mnnm: str, buld_slno: str,
                 max_retry: int = 5) -> dict | None:
    """좌표검색. rate limit(E0007) 발생 시 지수 백오프 재시도.

    반환: {'lat', 'lng', 'bd_nm', 'bd_mgt_sn', 'ent_x', 'ent_y'} 또는 None
    """
    if not JUSO_CONFIRM_KEY:
        raise JusoError("JUSO_CONFIRM_KEY 환경변수 없음")

    jusos = None
    last_err = None
    for attempt in range(max_retry):
        try:
            jusos = _call_once(adm_cd, rn_mgt_sn, udrt_yn, buld_mnnm, buld_slno)
            break
        except JusoError as e:
            last_err = e
            msg = str(e)
            if any(c in msg for c in _RATE_LIMIT_CODES):
                # 지수 백오프: 1.5s, 3s, 6s, 12s, 24s
                time.sleep(1.5 * (2 ** attempt))
                continue
            raise
    if jusos is None:
        raise last_err or JusoError("unknown")

    if not jusos:
        return None
    j = jusos[0]
    try:
        ent_x = float(j.get("entX") or 0)
        ent_y = float(j.get("entY") or 0)
    except (TypeError, ValueError):
        return None
    if not (ent_x and ent_y):
        return None
    lat, lng = utmk_to_wgs84(ent_x, ent_y)
    return {
        "lat": lat,
        "lng": lng,
        "bd_nm": j.get("bdNm", ""),
        "bd_mgt_sn": j.get("bdMgtSn", ""),
        "ent_x": ent_x,
        "ent_y": ent_y,
    }
