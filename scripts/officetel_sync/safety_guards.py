"""재수집 파이프라인 최상위 안전 가드.

2026-04-23 사고 교훈:
  1. limit=10000 하드코딩 → Supabase 1000 클램프 → 첫 페이지만 처리 → 2,447 단지 오삭제
  2. 아파트 테이블 무관한 코드 경로에서 접근 가능성
  3. 대량 DELETE 전 샘플링 프리플라이트 부재

이 모듈은 위 3종 사고를 import 레벨에서 강제 차단.
"""
from __future__ import annotations

import re
import urllib.request
from typing import Iterable

from .config import (
    SUPABASE_REST,
    SUPABASE_REST_MAX_LIMIT,
    SUPABASE_SERVICE_ROLE_KEY,
)

APARTMENT_COUNT_MIN = 30000            # apartments baseline (사고 시 30,999 확인)

APARTMENT_TABLES_FORBIDDEN = frozenset({
    "apartments",
    "trade_cache",
    "danji_pages",
})


class SafetyViolation(RuntimeError):
    """안전 가드 위반. 이 예외가 raise되면 즉시 전체 파이프라인 abort."""


def assert_limit(limit: int) -> None:
    """Supabase REST limit 초과 방지.

    2026-04-23 사고의 직접 원인 차단. limit=10000 등 과도한 값 전달 시 실패.
    """
    if limit > SUPABASE_REST_MAX_LIMIT:
        raise SafetyViolation(
            f"Supabase limit {limit} > {SUPABASE_REST_MAX_LIMIT}. "
            f"페이지네이션 루프가 첫 페이지에서 break 하는 사고 재발 위험 (2026-04-23)."
        )


def assert_not_apartment_table(sql_or_path: str) -> None:
    """아파트 테이블 접근 차단.

    워드 바운더리 기반 매칭 — 'officetel_trades' 는 'trades' 와 별개로 취급.
    식별자 경계: 영숫자/밑줄이 아닌 문자 (공백, 구두점, 쿼리 구분자).
    """
    lowered = sql_or_path.lower()
    for tbl in APARTMENT_TABLES_FORBIDDEN:
        # 앞뒤가 identifier 문자가 아니어야 매치 (officetel_trades 의 _trades 오탐 방지)
        pattern = rf"(?<![a-z0-9_]){re.escape(tbl)}(?![a-z0-9_])"
        if re.search(pattern, lowered):
            raise SafetyViolation(
                f"금지 테이블 '{tbl}' 접근 시도: {sql_or_path[:200]}. "
                f"오피스텔 재수집은 아파트 테이블 불가침."
            )


def _fetch_table_count(table: str) -> int:
    """단일 테이블 count 실측. Content-Range 부재 시 예외."""
    req = urllib.request.Request(
        f"{SUPABASE_REST}/{table}?select=id&limit=1",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Prefer": "count=exact",
            "Range": "0-0",
            "Range-Unit": "items",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        content_range = r.headers.get("Content-Range") or r.headers.get("content-range")
    if not content_range or "/" not in content_range:
        raise SafetyViolation(f"{table} count 응답 파싱 실패: {content_range!r}")
    return int(content_range.rsplit("/", 1)[-1])


def fetch_apartment_count() -> int:
    """apartments 테이블 row 수 실측 (하위 호환)."""
    return _fetch_table_count("apartments")


def snapshot_apartment_baseline() -> dict[str, int]:
    """아파트 관련 전체 테이블 baseline. TRUNCATE 전후 비교용."""
    return {tbl: _fetch_table_count(tbl) for tbl in APARTMENT_TABLES_FORBIDDEN}


def assert_baseline_unchanged(before: dict[str, int]) -> dict[str, int]:
    """after 측정 후 before 와 완전 일치해야 통과."""
    after = snapshot_apartment_baseline()
    for tbl, count_before in before.items():
        count_after = after.get(tbl)
        if count_after != count_before:
            raise SafetyViolation(
                f"아파트 테이블 {tbl} 변동 감지: {count_before} → {count_after}. 즉시 중단."
            )
    return after


def preflight(baseline_apartment_count: int | None = None) -> int:
    """수집 전 실행. apartments count 읽고 baseline 대비 급감 시 abort."""
    now_count = fetch_apartment_count()
    if now_count < APARTMENT_COUNT_MIN:
        raise SafetyViolation(
            f"apartments count {now_count} < {APARTMENT_COUNT_MIN}. "
            f"아파트 테이블 오염/삭제 의심. 즉시 중단."
        )
    if baseline_apartment_count is not None and now_count != baseline_apartment_count:
        raise SafetyViolation(
            f"apartments count 변동 감지: {baseline_apartment_count} → {now_count}. "
            f"오피스텔 재수집 중 아파트 테이블이 영향받음. 즉시 중단."
        )
    return now_count


def assert_whitelist_present(whitelist_names: Iterable[str], existing_names: Iterable[str]) -> None:
    """활발한 단지 화이트리스트 모두 존재하는지 검증.

    재수집 결과 DB 에 아래 단지가 빠져있으면 abort (집계/매칭 버그 조기 감지):
      - 역삼센트럴푸르지오시티
      - 강남지웰홈스
      - (추후 10개 확정)
    """
    existing = {n.replace(" ", "") for n in existing_names}
    missing = [n for n in whitelist_names if n.replace(" ", "") not in existing]
    if missing:
        raise SafetyViolation(
            f"화이트리스트 {len(missing)}개 단지 누락: {missing[:5]}. "
            f"10건 게이트/매칭 로직 재검토 필요."
        )


def assert_umd_is_dong(officetels: Iterable[dict]) -> None:
    """umd 컬럼은 진짜 동/면/읍/리/가만 허용.

    2026-04-25 사고 교훈: 자치구(*구)가 umd 자리에 들어가서 dong 페이지 슬러그가 깨졌음.
    한국 법정동/행정동 명칭은 동·면·읍·리·가 외 끝맺음이 사실상 없음.
    *구로 끝나는 umd는 무조건 자치구 잘못 들어간 것 → 적재 거부.
    """
    bad: list[tuple[str, str, str]] = []
    for d in officetels:
        umd = (d.get("umd") or "").strip()
        if not umd:
            continue
        if umd.endswith("구"):
            bad.append((d.get("id") or "?", d.get("sgg") or "?", umd))
    if bad:
        raise SafetyViolation(
            f"umd 자리에 자치구가 들어간 단지 {len(bad):,}건 — 적재 거부.\n"
            f"올바른 처리: sgg=시+자치구 결합(예: '고양덕양구'), umd=진짜 동(예: '원흥동').\n"
            f"샘플: {bad[:5]}"
        )


def assert_content_range_complete(content_range: str, received_len: int) -> None:
    """Content-Range 헤더로 페이지네이션 완주 검증.

    '0-999/12345' 형태에서 범위 끝과 전체 일치 여부 확인.
    첫 페이지만 받고 빠져나가는 사고 감지.
    """
    if "/" not in content_range or "-" not in content_range:
        return  # 빈 결과셋 등은 패스
    range_part, total = content_range.split("/", 1)
    start, end = range_part.split("-", 1)
    start_i, end_i = int(start), int(end)
    if received_len != (end_i - start_i + 1):
        raise SafetyViolation(
            f"Content-Range 불일치: 헤더 {content_range}, 받은 row {received_len}"
        )
