"""국토부 API 공용 클라이언트 (urllib3 풀 + 전역 QPS + 회로차단기)."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET

from ..config import (
    CIRCUIT_BREAKER_CONSEC_FAIL,
    CIRCUIT_BREAKER_COOL_SEC,
    GOV_SERVICE_KEY,
    MOLIT_GLOBAL_QPS,
    MOLIT_MAX_RETRY,
    MOLIT_NUM_OF_ROWS,
    MOLIT_PAGE_CAP,
)
from ..http_session import get as http_get
from ..rate_limiter import CircuitBreaker, TokenBucket

_BUCKET = TokenBucket(rate=MOLIT_GLOBAL_QPS, capacity=MOLIT_GLOBAL_QPS * 2)
_BREAKER = CircuitBreaker("molit", CIRCUIT_BREAKER_CONSEC_FAIL, CIRCUIT_BREAKER_COOL_SEC)


class MolitError(RuntimeError):
    pass


def _parse_xml(xml_text: str) -> tuple[list[dict], int]:
    root = ET.fromstring(xml_text)
    header = root.find("header")
    if header is not None:
        code = (header.findtext("resultCode") or "").strip()
        if code and code not in ("00", "000"):
            msg = header.findtext("resultMsg") or ""
            raise MolitError(f"국토부 오류 {code}: {msg}")

    body = root.find("body")
    if body is None:
        return [], 0
    total = int((body.findtext("totalCount") or "0").strip() or 0)
    items_el = body.find("items")
    if items_el is None:
        return [], total

    rows = []
    for item in items_el.findall("item"):
        row = {child.tag: (child.text.strip() if child.text else "") for child in item}
        rows.append(row)
    return rows, total


def fetch_page(url: str, params: dict) -> tuple[list[dict], int]:
    """단일 페이지. 토큰 버킷 + 회로차단기 + 3회 지수백오프."""
    full_params = {"serviceKey": GOV_SERVICE_KEY, **params}

    last_err: Exception | None = None
    for attempt in range(MOLIT_MAX_RETRY):
        _BREAKER.before_call()
        _BUCKET.acquire()
        try:
            data = http_get(url, full_params)
            text = data.decode("utf-8")
            rows, total = _parse_xml(text)
            _BREAKER.on_success()
            return rows, total
        except (RuntimeError, ET.ParseError, MolitError, OSError) as e:
            last_err = e
            _BREAKER.on_failure()
            time.sleep((2 ** attempt) * 0.5)
    raise MolitError(f"재시도 소진: {url} {params} — {last_err}")


def fetch_all_pages(url: str, params: dict, *, num_of_rows: int = MOLIT_NUM_OF_ROWS,
                    max_pages: int = MOLIT_PAGE_CAP) -> list[dict]:
    """totalCount 기반 전 페이지 수집. 빈 페이지 연속 3회 시 중단."""
    base = {**params, "numOfRows": str(num_of_rows), "pageNo": "1"}
    first, total = fetch_page(url, base)
    if total == 0:
        return []

    import math
    pages = min(math.ceil(total / num_of_rows), max_pages)
    all_rows = list(first)
    consec_empty = 0
    for p in range(2, pages + 1):
        rows, _ = fetch_page(url, {**params, "numOfRows": str(num_of_rows), "pageNo": str(p)})
        if not rows:
            consec_empty += 1
            if consec_empty >= 3:
                break
            continue
        consec_empty = 0
        all_rows.extend(rows)
    return all_rows
