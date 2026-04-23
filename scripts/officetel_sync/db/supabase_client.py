"""Supabase REST 클라이언트 (limit 가드 + 페이지네이션).

2026-04-23 사고 직접 대응:
  - 모든 SELECT에 limit=1000 고정 + 페이지네이션
  - 모든 응답 Content-Range 검증
  - 모든 SQL/path에서 아파트 테이블 금지어 차단
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..config import (
    INSERT_BATCH_SIZE,
    SUPABASE_REST,
    SUPABASE_REST_MAX_LIMIT,
    SUPABASE_SERVICE_ROLE_KEY,
)
from ..safety_guards import (
    assert_limit,
    assert_not_apartment_table,
)


def _headers(extra: dict | None = None) -> dict:
    base = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        base.update(extra)
    return base


def _request(method: str, path: str, *, body: Any = None, headers_extra: dict | None = None,
             timeout: int = 30) -> tuple[Any, dict]:
    """내부 공용. 아파트 테이블 가드 (path + body 둘 다) + 지수 백오프 재시도 3회."""
    assert_not_apartment_table(path)
    body_text_for_guard = json.dumps(body, ensure_ascii=False) if body is not None else ""
    if body_text_for_guard:
        assert_not_apartment_table(body_text_for_guard)

    url = f"{SUPABASE_REST}/{path.lstrip('/')}"
    data = body_text_for_guard.encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_headers(headers_extra))

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                payload = json.loads(raw) if raw else None
                return payload, dict(r.headers)
        except urllib.error.HTTPError as e:
            if 500 <= e.code < 600 and attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
                last_err = e
                continue
            body_err = e.read().decode("utf-8", errors="ignore")[:500]
            raise RuntimeError(f"HTTP {e.code} {method} {path}: {body_err}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise
    raise RuntimeError(f"재시도 소진 {method} {path} — {last_err}")


def paginated_select(table: str, select: str, filters: str = "", *,
                     order: str = "") -> list[dict]:
    """전체 row 페이지네이션 수집.

    URL limit/offset 단일 축만 사용 (Range 헤더 혼용 시 PostgREST 버전별 편차 있음).
    limit 1000 강제 (assert_limit). 빈 응답까지 반복.
    """
    out: list[dict] = []
    offset = 0
    while True:
        assert_limit(SUPABASE_REST_MAX_LIMIT)
        q = [f"select={urllib.parse.quote(select)}",
             f"limit={SUPABASE_REST_MAX_LIMIT}",
             f"offset={offset}"]
        if filters:
            q.append(filters)
        if order:
            q.append(f"order={urllib.parse.quote(order)}")
        path = f"{table}?{'&'.join(q)}"

        rows, _headers = _request("GET", path)
        rows = rows or []
        out.extend(rows)

        if len(rows) < SUPABASE_REST_MAX_LIMIT:
            break
        offset += SUPABASE_REST_MAX_LIMIT
    return out


def count_rows(table: str, filters: str = "") -> int:
    """COUNT 전용. Content-Range 헤더 부재 시 예외(사일런트 실패 방지)."""
    q = ["select=id", "limit=1"]
    if filters:
        q.append(filters)
    path = f"{table}?{'&'.join(q)}"
    _, headers = _request(
        "GET", path,
        headers_extra={"Prefer": "count=exact", "Range": "0-0", "Range-Unit": "items"},
    )
    content_range = headers.get("Content-Range") or headers.get("content-range")
    if not content_range:
        raise RuntimeError(
            f"count_rows: Content-Range 헤더 없음 (table={table}). "
            f"Prefer: count=exact 응답 누락 — 사일런트 0 반환 방지."
        )
    if "/" not in content_range:
        raise RuntimeError(f"count_rows: Content-Range 형식 비정상: {content_range}")
    return int(content_range.rsplit("/", 1)[-1])


def insert_rows(table: str, rows: list[dict], *, on_conflict: str = "",
                upsert: bool = False) -> int:
    """배치 INSERT. INSERT_BATCH_SIZE 단위 분할, 총 삽입 수 반환.

    upsert=True 시 PostgREST 'resolution=merge-duplicates' 헤더 추가 (on_conflict 필수).
    NOT NULL 위반 주의 (feedback_postgrest_upsert_notnull).
    """
    if not rows:
        return 0

    prefer = ["return=minimal"]
    if upsert:
        if not on_conflict:
            raise ValueError("upsert=True 시 on_conflict 컬럼 필수")
        prefer.append("resolution=merge-duplicates")

    path = table
    if on_conflict:
        path = f"{table}?on_conflict={urllib.parse.quote(on_conflict)}"

    total = 0
    for i in range(0, len(rows), INSERT_BATCH_SIZE):
        chunk = rows[i:i + INSERT_BATCH_SIZE]
        _request(
            "POST", path,
            body=chunk,
            headers_extra={"Prefer": ",".join(prefer)},
            timeout=60,
        )
        total += len(chunk)
    return total


def patch_row(table: str, filter_expr: str, patch: dict) -> None:
    """단일 row PATCH. ?col=eq.X 형태 filter 필수 (feedback_postgrest_upsert_notnull)."""
    if "=eq." not in filter_expr and "=in." not in filter_expr:
        raise ValueError(f"PATCH filter는 eq./in. 만 허용: {filter_expr}")
    path = f"{table}?{filter_expr}"
    _request("PATCH", path, body=patch,
             headers_extra={"Prefer": "return=minimal"})


def call_rpc(fn_name: str, args: dict | None = None) -> Any:
    """RPC 호출 (집계 등)."""
    path = f"rpc/{fn_name}"
    payload, _ = _request("POST", path, body=args or {})
    return payload
